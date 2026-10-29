"""Data cleaning: detects common problems in raw survey/experiment data and applies cleaning steps.

Steps run on a copy of the data, in order, and every step reports what it changed in plain language, so the
cleaning log can go straight into the methodology chapter. The stored version is never modified; the API saves
the result as a new version. Outliers are never removed automatically: that is a methodological decision.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import polars as pl

ROW = "__row"  # original row number, carried through every step to show what changed
MISSING_TOKENS = {"", "na", "n/a", "n.a.", "n.a", "none", "null", "nil", "-", "--", "---", "?", ".", "missing",
                  "no answer", "#n/a", "nan", "not applicable"}
NUMBER_JUNK = re.compile(r"[,\s%₱$€£¥]|php|usd|pesos?", re.I)
SENTINELS = (9, 99, 999, 9999, -1, -9, -99, -999)
OPS = ("trim_text", "change_case", "recode", "to_number", "missing_codes", "drop_duplicates", "drop_missing",
       "fill_missing", "out_of_range", "outliers", "rename", "drop_columns")


class CleaningError(ValueError):
    """A step that cannot run as written (unknown column, bad value). The message is shown to the user."""


# --------------------------------------------------------------------------- helpers


def _data_cols(df: pl.DataFrame) -> list[str]:
    return [c for c in df.columns if c != ROW]


def _text_cols(df: pl.DataFrame) -> list[str]:
    return [c for c in _data_cols(df) if df.schema[c] == pl.String]


def _cols(df: pl.DataFrame, step: dict[str, Any], *, default_all: bool = False, text_only: bool = False) -> list[str]:
    cols = step.get("columns") or ([step["column"]] if step.get("column") else [])
    if not cols:
        if default_all:
            return _text_cols(df) if text_only else _data_cols(df)
        raise CleaningError("Choose a column for this step.")
    unknown = [c for c in cols if c not in df.columns or c == ROW]
    if unknown:
        raise CleaningError(f"Column not found: {', '.join(unknown)}. It may have been renamed or removed by an earlier step.")
    return list(dict.fromkeys(cols))


def _changed(a: pl.Series, b: pl.Series) -> int:
    return int(a.cast(pl.String).ne_missing(b.cast(pl.String)).sum())


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if v == v else "missing"
    return "missing" if v is None else str(v)


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def _list(cols: list[str], limit: int = 4) -> str:
    return ", ".join(cols[:limit]) + (f" and {len(cols) - limit} more" if len(cols) > limit else "")


def _parse_number(s: pl.Expr) -> pl.Expr:
    cleaned = s.str.strip_chars().str.to_lowercase()
    cleaned = pl.when(cleaned.is_in(list(MISSING_TOKENS))).then(None).otherwise(cleaned)
    return cleaned.str.replace_all(NUMBER_JUNK.pattern, "").str.replace(r"^\((.*)\)$", "-$1").cast(pl.Float64, strict=False)


def _typed(df: pl.DataFrame, col: str, value: Any) -> Any:
    """A user-typed value converted to the column's type (so '5' matches the number 5)."""
    if value is None or value == "":
        return None
    dtype = df.schema[col]
    if dtype.is_numeric():
        try:
            f = float(value)
        except (TypeError, ValueError) as exc:
            raise CleaningError(f"'{value}' is not a number, but {col} holds numbers.") from exc
        return int(f) if dtype.is_integer() and f.is_integer() else f
    return str(value)


# --------------------------------------------------------------------------- steps


def _trim_text(df, step):
    cols = _cols(df, step, default_all=True, text_only=True)
    cols = [c for c in cols if df.schema[c] == pl.String]
    n = 0
    for c in cols:
        new = df[c].str.strip_chars().str.replace_all(r"\s{2,}", " ")
        n += _changed(df[c], new)
        df = df.with_columns(new.alias(c))
    return df, f"Removed extra spaces in {_plural(n, 'cell')} ({_list(cols)})." if n else "No extra spaces found."


def _change_case(df, step):
    (c,) = _cols(df, step)[:1]
    case = step.get("case", "title")
    if df.schema[c] != pl.String:
        raise CleaningError(f"{c} is not a text column.")
    s = df[c]
    new = {"lower": s.str.to_lowercase(), "upper": s.str.to_uppercase(), "title": s.str.to_titlecase(),
           "sentence": s.str.slice(0, 1).str.to_uppercase() + s.str.slice(1).str.to_lowercase()}.get(case)
    if new is None:
        raise CleaningError("Choose lower case, upper case, title case or sentence case.")
    n = _changed(s, new)
    return df.with_columns(new.alias(c)), f"{c}: changed {_plural(n, 'value')} to {case} case."


def _recode(df, step):
    (c,) = _cols(df, step)[:1]
    mapping = step.get("mapping") or {}
    if not mapping:
        raise CleaningError("Add at least one value to recode.")
    e = pl.col(c)
    dtype = df.schema[c]
    # Text is matched ignoring surrounding and repeated spaces, so the step works with or without trimming first.
    key = pl.col(c).str.strip_chars().str.replace_all(r"\s{2,}", " ") if dtype == pl.String else pl.col(c)
    for old, new in mapping.items():
        target = re.sub(r"\s+", " ", str(old).strip()) if dtype == pl.String else _typed(df, c, old)
        e = pl.when(key == target).then(pl.lit(_typed(df, c, new), dtype=dtype)).otherwise(e)
    new_s = df.select(e.alias(c))[c]
    n = _changed(df[c], new_s)
    groups: dict[str, list[str]] = {}
    for old, new in mapping.items():
        groups.setdefault(_fmt(_typed(df, c, new)), []).append(f"“{old}”")
    detail = "; ".join(f"{', '.join(olds)} → “{new}”" if new != "missing" else f"{', '.join(olds)} → missing"
                       for new, olds in groups.items())
    return df.with_columns(new_s), f"{c}: recoded {_plural(n, 'value')} ({detail})."


def _to_number(df, step):
    cols = _cols(df, step)
    parts = []
    for c in cols:
        if df.schema[c].is_numeric():
            continue
        raw = df[c].cast(pl.String)
        num = df.select(_parse_number(pl.col(c).cast(pl.String)).alias(c))[c]
        blank = raw.str.strip_chars().str.to_lowercase().is_in(list(MISSING_TOKENS)) | raw.is_null()
        bad = raw.filter(num.is_null() & ~blank)
        if num.drop_nulls().len() and (num.drop_nulls() % 1 == 0).all():
            num = num.cast(pl.Int64)
        df = df.with_columns(num.alias(c))
        msg = f"{c} converted to numbers"
        if bad.len():
            ex = ", ".join(f"“{x}”" for x in bad.unique(maintain_order=True).head(3).to_list())
            msg += f"; {_plural(bad.len(), 'value')} could not be read and became missing (e.g. {ex})"
        parts.append(msg)
    return df, (". ".join(parts) + ".") if parts else "Columns were already numeric."


def _missing_codes(df, step):
    cols = _cols(df, step)
    codes = [str(x).strip() for x in step.get("codes") or []]
    if not codes:
        raise CleaningError("List the codes that mean “no answer”, for example 99 or N/A.")
    total, touched = 0, []
    for c in cols:
        if df.schema[c].is_numeric():
            nums = []
            for x in codes:
                try:
                    nums.append(float(x))
                except ValueError:
                    continue
            if not nums:
                continue
            hit = pl.col(c).cast(pl.Float64).is_in(nums)
        else:
            hit = pl.col(c).str.strip_chars().str.to_lowercase().is_in([x.lower() for x in codes])
        n = int(df.select(hit.fill_null(False).sum()).item())
        if n:
            df = df.with_columns(pl.when(hit).then(None).otherwise(pl.col(c)).alias(c))
            total += n
            touched.append(c)
    shown = ", ".join(f"“{x}”" if x else "blank" for x in codes[:5])
    if not total:
        return df, f"No cells contained the codes {shown}."
    return df, f"Treated {shown} as missing: {_plural(total, 'cell')} in {_list(touched)}."


def _drop_duplicates(df, step):
    subset = _cols(df, step, default_all=True)
    before = df.height
    df = df.unique(subset=subset, keep="first", maintain_order=True)
    n = before - df.height
    scope = "identical rows" if len(subset) == len(_data_cols(df)) else f"rows with the same {_list(subset)}"
    return df, f"Removed {_plural(n, 'duplicate row')} ({scope}; the first copy of each was kept)." if n else "No duplicate rows found."


def _drop_missing(df, step):
    cols = _cols(df, step, default_all=True)
    how = step.get("how", "any")
    nulls = [pl.col(c).is_null() for c in cols]
    cond = pl.all_horizontal(nulls) if how == "all" else pl.any_horizontal(nulls)
    before = df.height
    df = df.filter(~cond)
    n = before - df.height
    if len(cols) == len(_data_cols(df)) and how == "all":
        return df, f"Removed {_plural(n, 'empty row')}." if n else "No empty rows found."
    which = "all of" if how == "all" else "any of"
    return df, f"Removed {_plural(n, 'row')} with a missing value in {which} {_list(cols)}." if n else f"No rows were missing {_list(cols)}."


def _fill_missing(df, step):
    (c,) = _cols(df, step)[:1]
    method = step.get("method", "median")
    s = df[c]
    if method in ("mean", "median"):
        if not s.dtype.is_numeric():
            raise CleaningError(f"{c} is not numeric, so it has no {method}. Use the most common value or a fixed value.")
        value = s.mean() if method == "mean" else s.median()
        if s.dtype.is_integer() and value is not None:
            if float(value).is_integer():
                value = int(value)
            else:
                s = s.cast(pl.Float64)
    elif method == "mode":
        modes = s.drop_nulls().mode()
        value = modes.sort()[0] if modes.len() else None
    elif method == "value":
        value = _typed(df, c, step.get("value"))
    else:
        raise CleaningError("Choose mean, median, most common value or a fixed value.")
    if value is None:
        return df, f"{c}: nothing to fill with (the column has no values)."
    n = int(s.null_count())
    label = {"mean": "the mean", "median": "the median", "mode": "the most common value", "value": "the value"}[method]
    return df.with_columns(s.fill_null(value).alias(c)), f"{c}: filled {_plural(n, 'missing value')} with {label}, {_fmt(value)}."


def _out_of_range(df, step):
    (c,) = _cols(df, step)[:1]
    if not df.schema[c].is_numeric():
        raise CleaningError(f"{c} is not numeric. Convert it to numbers first.")
    lo, hi = step.get("min"), step.get("max")
    if lo is None and hi is None:
        raise CleaningError("Give the lowest and/or highest valid value.")
    bad = pl.lit(False)
    if lo is not None:
        bad = bad | (pl.col(c) < float(lo))
    if hi is not None:
        bad = bad | (pl.col(c) > float(hi))
    bad = bad.fill_null(False)
    n = int(df.select(bad.sum()).item())
    rng = f"{_fmt(lo) if lo is not None else '−∞'}–{_fmt(hi) if hi is not None else '∞'}"
    if step.get("action") == "drop":
        return df.filter(~bad), f"{c}: removed {_plural(n, 'row')} with values outside {rng}."
    return df.with_columns(pl.when(bad).then(None).otherwise(pl.col(c)).alias(c)), \
        f"{c}: {_plural(n, 'value')} outside the valid range {rng} set to missing."


def _outliers(df, step):
    (c,) = _cols(df, step)[:1]
    if not df.schema[c].is_numeric():
        raise CleaningError(f"{c} is not numeric.")
    s = df[c].drop_nulls().cast(pl.Float64)
    if s.len() < 4:
        return df, f"{c}: too few values to judge outliers."
    if step.get("method", "iqr") == "z":
        k = float(step.get("k") or 3)
        m, sd = s.mean(), s.std()
        lo, hi = m - k * sd, m + k * sd
        rule = f"more than {_fmt(k)} SD from the mean"
    else:
        k = float(step.get("k") or 1.5)
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        lo, hi = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
        rule = f"beyond {_fmt(k)} × IQR from the quartiles"
    bad = ((pl.col(c) < lo) | (pl.col(c) > hi)).fill_null(False)
    n = int(df.select(bad.sum()).item())
    bounds = f"below {_fmt(lo)} or above {_fmt(hi)}"
    if step.get("action") == "drop":
        return df.filter(~bad), f"{c}: removed {_plural(n, 'row')} with outliers ({rule}: {bounds})."
    return df.with_columns(pl.when(bad).then(None).otherwise(pl.col(c)).alias(c)), \
        f"{c}: {_plural(n, 'outlier')} ({rule}: {bounds}) set to missing."


def _rename(df, step):
    (c,) = _cols(df, step)[:1]
    to = str(step.get("to") or "").strip()
    if not to:
        raise CleaningError("Type the new column name.")
    if to in df.columns and to != c:
        raise CleaningError(f"A column named {to} already exists.")
    return df.rename({c: to}), f"Renamed {c} to {to}."


def _drop_columns(df, step):
    cols = _cols(df, step)
    if len(cols) >= len(_data_cols(df)):
        raise CleaningError("At least one column must remain.")
    return df.drop(cols), f"Removed {_plural(len(cols), 'column')}: {_list(cols, 6)}."


STEPS = {"trim_text": _trim_text, "change_case": _change_case, "recode": _recode, "to_number": _to_number,
         "missing_codes": _missing_codes, "drop_duplicates": _drop_duplicates, "drop_missing": _drop_missing,
         "fill_missing": _fill_missing, "out_of_range": _out_of_range, "outliers": _outliers, "rename": _rename,
         "drop_columns": _drop_columns}


def summary(df: pl.DataFrame) -> dict[str, int]:
    cols = _data_cols(df)
    d = df.select(cols)
    return {"rows": d.height, "columns": len(cols),
            "missing_cells": int(sum(d.null_count().row(0))) if cols else 0,
            "duplicate_rows": d.height - d.unique().height if cols else 0,
            "empty_rows": int(d.select(pl.all_horizontal(pl.all().is_null()).sum()).item()) if cols and d.height else 0}


def apply(df: pl.DataFrame, steps: list[dict[str, Any]]) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
    """Runs the steps in order on a copy (with a hidden row number). Returns the data and one log entry per step."""
    if ROW not in df.columns:
        df = df.with_row_index(ROW)
    log = []
    for i, step in enumerate(steps, start=1):
        fn = STEPS.get(step.get("op"))
        if fn is None:
            raise CleaningError(f"Step {i}: unknown cleaning operation '{step.get('op')}'.")
        before = df.height
        try:
            df, message = fn(df, step)
        except CleaningError as exc:
            raise CleaningError(f"Step {i}: {exc}") from exc
        log.append({"step": i, "op": step["op"], "message": message, "rows_before": before, "rows_after": df.height})
    return df, log


def preview(raw: pl.DataFrame, steps: list[dict[str, Any]], limit: int = 100) -> dict[str, Any]:
    """Before/after summary, the log, and the first rows after cleaning with changed cells marked."""
    base = raw.with_row_index(ROW)
    out, log = apply(base, steps)
    origin = {c: c for c in raw.columns}
    for s in steps:
        if s.get("op") == "rename" and s.get("column") in origin.values():
            src = next(k for k, v in origin.items() if v == s["column"])
            origin[src] = str(s.get("to") or "").strip()
    current_to_raw = {v: k for k, v in origin.items()}
    head = out.head(limit)
    rows = head.select(_data_cols(head)).rows()
    changed: list[list[Any]] = []
    raw_rows = base.filter(pl.col(ROW).is_in(head[ROW].to_list()))
    lookup = {r[ROW]: r for r in raw_rows.iter_rows(named=True)}
    cols = _data_cols(head)
    for i, rec in enumerate(head.iter_rows(named=True)):
        src = lookup.get(rec[ROW], {})
        for c in cols:
            rc = current_to_raw.get(c)
            if rc is None or rc not in src:
                continue
            a, b = src[rc], rec[c]
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
                differs = float(a) != float(b)
            else:
                differs = (a is None) != (b is None) or (a is not None and str(a) != str(b))
            if differs:
                changed.append([i, c])
    return {"before": summary(raw), "after": summary(out), "log": log, "columns": cols,
            "rows": [[None if v is None else v for v in r] for r in rows], "changed": changed}


# --------------------------------------------------------------------------- suggestions


def _variants(values: list[str]) -> dict[str, str]:
    """Spellings of the same category ('male', 'Male ', 'MALE', 'M') mapped to the most common spelling."""
    counts = Counter(v for v in values if v is not None)
    groups: dict[str, list[str]] = {}
    for v in counts:
        key = re.sub(r"\s+", " ", v.strip().lower())
        if key.lower() in MISSING_TOKENS:
            continue
        groups.setdefault(key, []).append(v)
    mapping: dict[str, str] = {}
    canon: dict[str, str] = {}
    for key, forms in groups.items():
        best = max(forms, key=lambda f: (counts[f], f.strip() == f, f[:1].isupper()))
        canon[key] = re.sub(r"\s+", " ", best.strip())
        for f in forms:
            tidy = re.sub(r"\s+", " ", f.strip())
            if tidy != canon[key]:
                mapping[tidy] = canon[key]
    # Single-letter codes next to full words: M -> Male, F -> Female (only when unambiguous).
    full = [k for k in canon if len(k) > 1]
    for key in [k for k in canon if len(k) == 1]:
        matches = [k for k in full if k.startswith(key)]
        if len(matches) == 1:
            for f in groups[key]:
                mapping[re.sub(r"\s+", " ", f.strip())] = canon[matches[0]]
    return mapping


def suggest(raw: pl.DataFrame, levels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    levels = levels or {}
    df = raw
    out: list[dict[str, Any]] = []

    def add(kind, title, detail, step, default=True, examples=None):
        out.append({"id": f"s{len(out) + 1}", "kind": kind, "title": title, "detail": detail, "step": step,
                    "default": default, "examples": examples or []})

    if not df.height:
        return out
    empty_cols = [c for c in df.columns if df[c].null_count() == df.height]
    if empty_cols:
        add("empty_columns", f"Remove {_plural(len(empty_cols), 'empty column')}", f"{_list(empty_cols)} contain no values.",
            {"op": "drop_columns", "columns": empty_cols})
    n_empty = int(df.select(pl.all_horizontal(pl.all().is_null()).sum()).item())
    if n_empty:
        add("empty_rows", f"Remove {_plural(n_empty, 'empty row')}", "Rows where every cell is blank, often left at the end of a spreadsheet.",
            {"op": "drop_missing", "how": "all"})

    text = _text_cols(df)
    spaced = [c for c in text if _changed(df[c], df[c].str.strip_chars().str.replace_all(r"\s{2,}", " "))]
    if spaced:
        add("whitespace", "Remove extra spaces", f"Leading, trailing or double spaces in {_list(spaced)}. “Male ” and “Male” would otherwise count as different answers.",
            {"op": "trim_text", "columns": spaced})

    for c in text:
        s = df[c].drop_nulls()
        if not s.len():
            continue
        tokens = s.filter(s.str.strip_chars().str.to_lowercase().is_in(list(MISSING_TOKENS)))
        nums = df.select(_parse_number(pl.col(c)).alias(c))[c]
        non_blank = s.len() - tokens.len()
        parsed = int(nums.drop_nulls().len())
        if tokens.len():
            found = sorted({x.strip() for x in tokens.to_list()}, key=str.lower)
            shown = ", ".join(f"“{x}”" if x else "blank" for x in found[:4])
            add("missing_tokens", f"{c}: treat {shown} as missing", f"{_plural(tokens.len(), 'cell')} use a placeholder instead of being left empty.",
                {"op": "missing_codes", "columns": [c], "codes": found})
        if non_blank and parsed / non_blank >= 0.8 and levels.get(c) != "identifier":
            col = df[c]
            bad = col.filter(col.is_not_null() & nums.is_null()
                             & ~col.str.strip_chars().str.to_lowercase().is_in(list(MISSING_TOKENS)))
            add("numbers_as_text", f"{c}: convert to numbers",
                f"{parsed / non_blank:.0%} of the values are numbers written as text (with commas, units or symbols)."
                + (f" {_plural(bad.len(), 'value')} cannot be read and will become missing." if bad.len() else ""),
                {"op": "to_number", "columns": [c]}, examples=bad.unique(maintain_order=True).head(5).to_list())
            continue
        uniq = s.unique()
        if 2 <= uniq.len() <= 40 and levels.get(c) not in ("identifier", "text"):
            mapping = _variants(s.to_list())
            # Spaces are handled by the whitespace step; only suggest real spelling differences.
            if mapping:
                pairs = "; ".join(f"“{k}” → “{v}”" for k, v in list(mapping.items())[:4])
                add("categories", f"{c}: merge spellings of the same answer", f"{pairs}{' …' if len(mapping) > 4 else ''}",
                    {"op": "recode", "column": c, "mapping": mapping})

    for c in _data_cols(df):
        dtype = df.schema[c]
        if not dtype.is_numeric() or levels.get(c) == "identifier":
            continue
        s = df[c].drop_nulls().cast(pl.Float64)
        if s.len() < 5:
            continue
        if dtype.is_integer() or (s % 1 == 0).all():
            likert = False
            for k in (4, 5, 7, 10):
                inside = s.is_between(1, k)
                outside = s.filter(~inside)
                # Only values that cannot be a typo-free answer on a 1–k scale: above 2k (55, 99) or below 1.
                if inside.mean() >= 0.75 and s.filter(inside).n_unique() >= 3 and outside.len()                         and ((outside > 2 * k) | (outside < 1)).all():
                    bad = outside.unique().sort().to_list()
                    add("likert_range", f"{c}: values outside the 1–{k} scale",
                        f"{_plural(outside.len(), 'answer')} ({', '.join(_fmt(v) for v in bad[:5])}) cannot be on a 1–{k} scale and will be set to missing.",
                        {"op": "out_of_range", "column": c, "min": 1, "max": k, "action": "missing"})
                    likert = True
                    break
                if inside.mean() == 1:
                    likert = True
                    break
            if likert:
                continue
        sentinels = [v for v in SENTINELS if (s == v).any()]
        rest = s.filter(~s.is_in([float(v) for v in sentinels]))
        if sentinels and rest.len():
            lo, hi = rest.min(), rest.max()
            span = max(hi - lo, 1)
            flagged = [v for v in sentinels if v > hi + 3 * span or v < lo - 3 * span]
            if flagged:
                n = int(s.is_in([float(v) for v in flagged]).sum())
                add("sentinel", f"{c}: treat {', '.join(str(v) for v in flagged)} as missing",
                    f"{_plural(n, 'value')} far outside the other answers ({_fmt(lo)}–{_fmt(hi)}); codes like 99 usually mean “no answer”.",
                    {"op": "missing_codes", "columns": [c], "codes": [str(v) for v in flagged]})

    dupes = df.height - df.unique().height
    if dupes:
        add("duplicates", f"Remove {_plural(dupes, 'duplicate row')}", "Rows that are identical in every column, usually a response submitted or pasted twice. The first copy is kept.",
            {"op": "drop_duplicates"})
    ids = [c for c, lv in levels.items() if lv == "identifier" and c in df.columns]
    for c in ids:
        rep = df[c].drop_nulls()
        n = rep.len() - rep.n_unique()
        if n:
            add("duplicate_ids", f"{c}: {_plural(n, 'repeated ID')}", f"Some {c} values appear more than once. Check them first; removing keeps only the first row for each ID.",
                {"op": "drop_duplicates", "columns": [c]}, default=False,
                examples=[str(x) for x in rep.filter(rep.is_duplicated()).unique(maintain_order=True).head(5).to_list()])
    return out
