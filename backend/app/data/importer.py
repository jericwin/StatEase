"""File import: staging, format-specific readers, validation and conversion to Parquet.

The original upload is never modified. Every import produces a Parquet file that later
analyses and queries read lazily (only the columns they need).
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from ..config import get_settings
from ..errors import AppError
from ..storage import new_relative_path, resolve, safe_filename

SUPPORTED = {"csv", "tsv", "txt", "xlsx", "xlsm", "xls", "json", "ndjson", "jsonl", "parquet"}
DEFAULT_NULLS = ["", "NA", "N/A", "n/a", "NaN", "nan", "NULL", "null", "None", "#N/A", "-"]
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
_NUMERIC_TEXT = re.compile(r"^\s*[-+]?(\d+([.,]\d*)?|[.,]\d+)([eE][-+]?\d+)?\s*$")
_SLASH_DATE = re.compile(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\s*$")


@dataclass
class ImportOptions:
    sheet: str | None = None
    delimiter: str | None = None  # None -> auto
    has_header: bool = True
    encoding: str = "utf-8"
    null_values: list[str] = field(default_factory=lambda: list(DEFAULT_NULLS))
    skip_rows: int = 0
    decimal_comma: bool = False
    ragged_lines: str = "error"  # error | truncate
    renames: dict[str, str] = field(default_factory=dict)
    exclude_columns: list[str] = field(default_factory=list)
    date_formats: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> ImportOptions:
        d = dict(d or {})
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__ and v is not None}
        return cls(**known)


# --------------------------------------------------------------------------- staging


def stage_upload(filename: str, stream) -> dict[str, Any]:
    """Store an uploaded file under uploads/<id>/ and return its staging metadata."""
    s = get_settings()
    name = safe_filename(filename, "upload")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in SUPPORTED:
        raise AppError("unsupported_format",
                       f"'.{ext or '?'}' files are not supported. Use CSV, TSV, Excel (.xlsx/.xls), JSON or Parquet.",
                       415)
    upload_id = uuid.uuid4().hex
    folder = s.uploads_dir / upload_id
    folder.mkdir(parents=True)
    target = folder / name
    limit = s.max_upload_mb * 1024 * 1024
    size = 0
    sha = hashlib.sha256()
    with target.open("wb") as out:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                shutil.rmtree(folder, ignore_errors=True)
                raise AppError("file_too_large", f"The file exceeds the {s.max_upload_mb} MB upload limit.", 413)
            sha.update(chunk)
            out.write(chunk)
    if size == 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise AppError("empty_file", "The uploaded file is empty.", 400)
    fmt = {"txt": "csv", "xlsm": "xlsx", "jsonl": "ndjson"}.get(ext, ext)
    if fmt in {"xlsx", "xls"} and size > s.max_excel_mb * 1024 * 1024:
        shutil.rmtree(folder, ignore_errors=True)
        raise AppError("file_too_large",
                       f"Excel files are limited to {s.max_excel_mb} MB because they must be read into memory. "
                       "Save the sheet as CSV for larger data.", 413)
    meta = {"upload_id": upload_id, "filename": name, "format": fmt, "size_bytes": size, "sha256": sha.hexdigest()}
    (folder / "meta.json").write_text(json.dumps(meta))
    return meta


def staged(upload_id: str) -> tuple[dict[str, Any], Path]:
    if not _UPLOAD_ID.match(upload_id or ""):
        raise AppError("invalid_upload", "Invalid upload id.", 400)
    folder = get_settings().uploads_dir / upload_id
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        raise AppError("upload_expired", "The uploaded file is no longer available. Upload it again.", 404)
    meta = json.loads(meta_path.read_text())
    return meta, folder / meta["filename"]


def discard_upload(upload_id: str) -> None:
    if _UPLOAD_ID.match(upload_id or ""):
        shutil.rmtree(get_settings().uploads_dir / upload_id, ignore_errors=True)


# --------------------------------------------------------------------------- readers


def excel_sheets(path: Path) -> list[str]:
    import fastexcel

    try:
        return list(fastexcel.read_excel(str(path)).sheet_names)
    except Exception as exc:  # noqa: BLE001 - parser raises many types
        raise AppError("malformed_file", f"The Excel workbook could not be read: {exc}", 400) from exc


def _sniff_delimiter(sample: str, fmt: str) -> str:
    if fmt == "tsv":
        return "\t"
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _read_text_sample(path: Path, encoding: str, size: int = 256 * 1024) -> str:
    with path.open("rb") as f:
        raw = f.read(size)
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        # The sample may end mid-character; retry after trimming a few bytes.
        try:
            text = raw[:-4].decode(encoding)
        except UnicodeDecodeError as exc:
            raise AppError("invalid_encoding",
                           f"The file is not valid {encoding}. Choose another encoding (for example Windows-1252 "
                           "or Latin-1).", 400) from exc
    return text.lstrip("﻿")


def _utf8_source(path: Path, encoding: str) -> Path:
    """Polars reads UTF-8 only; transcode other encodings to a sibling UTF-8 file (streamed)."""
    enc = codecs.lookup(encoding).name
    if enc in {"utf-8", "utf-8-sig"}:
        return path
    target = path.with_suffix(path.suffix + f".{enc}.utf8")
    if not target.exists():
        with path.open("r", encoding=enc, newline="") as src, target.open("w", encoding="utf-8", newline="") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
    return target


def _clean_headers(raw: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    names: list[str] = []
    issues: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for i, h in enumerate(raw):
        original = h
        h = (h or "").strip()
        if not h:
            h = f"column_{i + 1}"
            issues.append({"code": "empty_column_name", "column": h,
                           "message": f"Column {i + 1} has no name; it was named '{h}'."})
        key = h.lower()
        if key in seen:
            seen[key] += 1
            new = f"{h}_{seen[key]}"
            while new.lower() in seen:
                seen[key] += 1
                new = f"{h}_{seen[key]}"
            issues.append({"code": "duplicate_column_name", "column": new,
                           "message": f"Column name '{original}' appears more than once; the repeat was renamed '{new}'."})
            h = new
        seen.setdefault(h.lower(), 1)
        names.append(h)
    return names, issues


def _csv_layout(path: Path, opts: ImportOptions, fmt: str) -> dict[str, Any]:
    sample = _read_text_sample(path, opts.encoding)
    delimiter = opts.delimiter or _sniff_delimiter(sample, fmt)
    if delimiter == "\\t":
        delimiter = "\t"
    lines = sample.splitlines()[opts.skip_rows:]
    if not lines or not "".join(lines).strip():
        raise AppError("empty_dataset", "The file contains no data rows.", 400)
    rows = list(csv.reader(lines[:5000], delimiter=delimiter))
    rows = [r for r in rows if r]
    width = len(rows[0]) if rows else 0
    if opts.has_header:
        headers, issues = _clean_headers(rows[0] if rows else [])
    else:
        headers, issues = [f"column_{i + 1}" for i in range(width)], []
    # The last sampled line may be cut off, so ignore it when checking row widths.
    body = rows[1:-1] if opts.has_header else rows[:-1]
    bad = [i for i, r in enumerate(body) if len(r) != width]
    if bad:
        first = bad[0] + (2 if opts.has_header else 1) + opts.skip_rows
        issues.append({"code": "inconsistent_rows", "severity": "error" if opts.ragged_lines == "error" else "warning",
                       "message": f"{len(bad)} of the first {len(body)} rows have a different number of fields than "
                                  f"the header (first at line {first}). Check the delimiter, or choose to truncate "
                                  "extra fields."})
    return {"delimiter": delimiter, "headers": headers, "issues": issues}


def _csv_kwargs(opts: ImportOptions, layout: dict[str, Any]) -> dict[str, Any]:
    return dict(
        separator=layout["delimiter"],
        has_header=opts.has_header,
        new_columns=layout["headers"],
        null_values=opts.null_values,
        skip_rows=opts.skip_rows,
        infer_schema_length=20000,
        decimal_comma=opts.decimal_comma,
        truncate_ragged_lines=opts.ragged_lines == "truncate",
        try_parse_dates=True,
        quote_char='"',
    )


def _flatten_nested(df: pl.DataFrame | pl.LazyFrame, issues: list[dict[str, Any]]):
    schema = df.collect_schema() if isinstance(df, pl.LazyFrame) else df.schema
    exprs = []
    for name, dtype in schema.items():
        if isinstance(dtype, pl.Struct):
            issues.append({"code": "nested_structure", "column": name,
                           "message": f"'{name}' contains nested objects; its fields were expanded into "
                                      f"separate columns ({name}.<field>)."})
            exprs.extend(pl.col(name).struct.field(f.name).alias(f"{name}.{f.name}") for f in dtype.fields)
        elif isinstance(dtype, (pl.List, pl.Array)):
            issues.append({"code": "nested_structure", "column": name,
                           "message": f"'{name}' contains lists; it was stored as text so no values are lost."})
            exprs.append(pl.col(name).cast(pl.List(pl.String)).list.join("; ").alias(name))
        else:
            exprs.append(pl.col(name))
    return df.select(exprs)


def _lazy_frame(path: Path, fmt: str, opts: ImportOptions) -> tuple[pl.LazyFrame, list[dict[str, Any]], dict]:
    """Return a LazyFrame for the whole file, import issues, and detected settings."""
    detected: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    try:
        if fmt in {"csv", "tsv"}:
            layout = _csv_layout(path, opts, fmt)
            issues += layout["issues"]
            detected["delimiter"] = layout["delimiter"]
            if any(i.get("severity") == "error" for i in issues):
                return pl.LazyFrame(), issues, detected
            src = _utf8_source(path, opts.encoding)
            lf = pl.scan_csv(src, **_csv_kwargs(opts, layout), encoding="utf8")
        elif fmt in {"xlsx", "xls"}:
            sheets = excel_sheets(path)
            detected["sheets"] = sheets
            sheet = opts.sheet or (sheets[0] if sheets else None)
            if sheet not in sheets:
                raise AppError("sheet_not_found", f"Worksheet '{opts.sheet}' was not found in the workbook.", 400)
            detected["sheet"] = sheet
            raw = pl.read_excel(path, sheet_name=sheet, engine="calamine", has_header=False,
                                read_options={"skip_rows": opts.skip_rows}, raise_if_empty=False,
                                infer_schema_length=0)
            if raw.height == 0:
                raise AppError("empty_dataset", f"Worksheet '{sheet}' is empty.", 400)
            if opts.has_header:
                header_vals = [("" if v is None else str(v)) for v in raw.row(0)]
                headers, h_issues = _clean_headers(header_vals)
                issues += h_issues
                skip = opts.skip_rows + 1
            else:
                headers = [f"column_{i + 1}" for i in range(raw.width)]
                skip = opts.skip_rows
            df = pl.read_excel(path, sheet_name=sheet, engine="calamine", has_header=False,
                               read_options={"skip_rows": skip}, raise_if_empty=False,
                               infer_schema_length=20000)
            df.columns = headers[: df.width] + [f"column_{i + 1}" for i in range(len(headers), df.width)]
            # Excel exports often carry trailing fully-empty rows/columns.
            df = df.filter(~pl.all_horizontal(pl.all().is_null()))
            if opts.null_values:
                str_cols = [c for c, t in df.schema.items() if t == pl.String]
                df = df.with_columns(
                    pl.when(pl.col(c).str.strip_chars().is_in(opts.null_values)).then(None).otherwise(pl.col(c))
                    .alias(c) for c in str_cols)
            lf = df.lazy()
        elif fmt == "json":
            text = _read_text_sample(path, "utf-8", 64)
            if text.lstrip().startswith("{") and "\n{" in path.read_text(encoding="utf-8")[:100000]:
                lf = pl.scan_ndjson(path, infer_schema_length=20000)
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    lists = [k for k, v in data.items() if isinstance(v, list)]
                    if len(lists) == 1:
                        data = data[lists[0]]
                        issues.append({"code": "json_wrapper", "message": f"Rows were read from the '{lists[0]}' key."})
                    elif data and all(isinstance(v, list) for v in data.values()):
                        data = [dict(zip(data.keys(), vals, strict=False)) for vals in zip(*data.values(), strict=False)]
                    else:
                        raise AppError("unsupported_structure",
                                       "The JSON must be a list of records (objects) or an object of equal-length "
                                       "column arrays.", 400)
                if not isinstance(data, list) or (data and not isinstance(data[0], dict)):
                    raise AppError("unsupported_structure", "The JSON must be a list of records (objects).", 400)
                lf = pl.DataFrame(data, infer_schema_length=20000).lazy()
            lf = _flatten_nested(lf, issues)
        elif fmt == "ndjson":
            lf = _flatten_nested(pl.scan_ndjson(path, infer_schema_length=20000), issues)
        elif fmt == "parquet":
            lf = _flatten_nested(pl.scan_parquet(path), issues)
        else:
            raise AppError("unsupported_format", f"Unsupported format '{fmt}'.", 415)
        schema = lf.collect_schema()
    except AppError:
        raise
    except pl.exceptions.ComputeError as exc:
        msg = str(exc).split("\n")[0]
        raise AppError("malformed_file", f"The file could not be parsed: {msg}", 400) from exc
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).split("\n")[0]
        raise AppError("malformed_file", f"The file could not be read: {msg}", 400) from exc

    if fmt not in {"csv", "tsv", "xlsx", "xls"}:
        names, h_issues = _clean_headers(list(schema.names()))
        if names != list(schema.names()):
            lf = lf.rename(dict(zip(schema.names(), names, strict=True)))
            issues += h_issues
    # User-specified exclusions, renames and explicit date formats.
    if opts.exclude_columns:
        lf = lf.drop([c for c in opts.exclude_columns if c in lf.collect_schema().names()])
    if opts.date_formats:
        cols = lf.collect_schema()
        lf = lf.with_columns(
            pl.col(c).str.strptime(pl.Datetime if ("%H" in f) else pl.Date, f, strict=False).alias(c)
            for c, f in opts.date_formats.items() if c in cols and cols[c] == pl.String)
    if opts.renames:
        current = lf.collect_schema().names()
        mapping = {k: v.strip() for k, v in opts.renames.items() if k in current and v and v.strip() and v != k}
        final = [mapping.get(c, c) for c in current]
        lowered = [c.lower() for c in final]
        dupes = sorted({c for c in final if lowered.count(c.lower()) > 1})
        if dupes:
            raise AppError("duplicate_column_name", f"Renaming would create duplicate column names: {', '.join(dupes)}.",
                           400)
        lf = lf.rename(mapping)
    return lf, issues, detected


def _value_issues(df: pl.DataFrame, opts: ImportOptions) -> list[dict[str, Any]]:
    """Mixed-type and ambiguous-date checks on a preview sample."""
    issues: list[dict[str, Any]] = []
    for name in df.columns:
        s = df[name]
        if s.dtype != pl.String:
            continue
        vals = s.drop_nulls()
        if vals.len() == 0:
            continue
        sample = vals.head(5000).to_list()
        numeric = [v for v in sample if _NUMERIC_TEXT.match(v)]
        if 0.8 <= len(numeric) / len(sample) < 1:
            bad = sorted({v for v in sample if not _NUMERIC_TEXT.match(v)})[:5]
            issues.append({"code": "mixed_types", "column": name, "severity": "warning", "values": bad,
                           "message": f"'{name}' is mostly numeric but contains text values such as "
                                      f"{', '.join(repr(b) for b in bad)}. It was kept as text. If these values mean "
                                      "'missing', add them to the missing-value list to read the column as numbers."})
        dates = [_SLASH_DATE.match(v) for v in sample[:2000]]
        if dates and sum(1 for d in dates if d) / len(dates) > 0.9 and name not in opts.date_formats:
            parts = [(int(d.group(1)), int(d.group(2)), d.group(3)) for d in dates if d]
            day_first = any(a > 12 for a, _, _ in parts)
            month_first = any(b > 12 for _, b, _ in parts)
            year = "%Y" if all(len(y) == 4 for *_, y in parts) else "%y"
            sep = re.search(r"[/.-]", sample[0]).group(0)  # type: ignore[union-attr]
            if day_first and not month_first:
                fmt, note = f"%d{sep}%m{sep}{year}", "Values look day-first."
            elif month_first and not day_first:
                fmt, note = f"%m{sep}%d{sep}{year}", "Values look month-first."
            else:
                fmt, note = None, "Day-first or month-first cannot be determined from the values."
            issues.append({"code": "ambiguous_date", "column": name, "severity": "warning", "suggested_format": fmt,
                           "message": f"'{name}' looks like dates but was kept as text. {note} Choose a date format "
                                      "to convert it."})
    return issues


def preview(upload_id: str, options: dict[str, Any] | None, n: int = 100) -> dict[str, Any]:
    from .inference import infer_variables

    meta, path = staged(upload_id)
    opts = ImportOptions.from_dict(options)
    lf, issues, detected = _lazy_frame(path, meta["format"], opts)
    if any(i.get("severity") == "error" for i in issues):
        return {"upload": meta, "detected": detected, "issues": issues, "columns": [], "rows": [], "variables": []}
    try:
        sample = lf.head(20000).collect()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).split("\n")[0]
        raise AppError("malformed_file", f"The file could not be parsed: {msg}", 400) from exc
    if sample.width == 0:
        raise AppError("empty_dataset", "No columns were found in the file.", 400)
    if sample.height == 0:
        issues.append({"code": "empty_dataset", "severity": "error", "message": "The file has a header but no data rows."})
    issues += _value_issues(sample, opts)
    variables = infer_variables(sample)
    rows = sample.head(n)
    return {
        "upload": meta,
        "detected": detected,
        "issues": issues,
        "columns": rows.columns,
        "rows": jsonable_rows(rows),
        "sample_rows": sample.height,
        "variables": variables,
    }


def jsonable_rows(df: pl.DataFrame) -> list[list[Any]]:
    out = []
    for row in df.iter_rows():
        out.append([_jsonable(v) for v in row])
    return out


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return None if v != v or v in (float("inf"), float("-inf")) else v
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def materialize(upload_id: str, options: dict[str, Any] | None) -> dict[str, Any]:
    """Convert the staged upload into a Parquet file; keep the original upload unchanged."""
    meta, path = staged(upload_id)
    opts = ImportOptions.from_dict(options)
    lf, issues, detected = _lazy_frame(path, meta["format"], opts)
    errors = [i for i in issues if i.get("severity") == "error"]
    if errors:
        raise AppError("import_failed", errors[0]["message"], 400, {"issues": issues})

    rel = new_relative_path("datasets", ".parquet")
    target = resolve(rel)
    try:
        lf.sink_parquet(target, compression="zstd")
    except Exception:  # noqa: BLE001 - some plans cannot stream; fall back to in-memory
        try:
            lf.collect().write_parquet(target, compression="zstd")
        except Exception as exc:  # noqa: BLE001
            target.unlink(missing_ok=True)
            msg = str(exc).split("\n")[0]
            raise AppError("malformed_file", f"The file could not be converted: {msg}. Check the delimiter, "
                                             "encoding and missing-value settings.", 400) from exc
    height = pl.scan_parquet(target).select(pl.len()).collect().item()
    if height == 0:
        target.unlink(missing_ok=True)
        raise AppError("empty_dataset", "The file contains no data rows.", 400)

    # Keep the untouched original next to the datasets.
    orig_rel = new_relative_path("originals", "." + meta["filename"].rsplit(".", 1)[-1])
    orig = resolve(orig_rel)
    orig.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, orig)
    discard_upload(upload_id)
    return {"data_path": rel, "original_path": orig_rel, "row_count": height, "issues": issues,
            "detected": detected, "meta": meta, "content_hash": file_hash(target)}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()
