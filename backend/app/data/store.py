"""Reading persisted datasets: column-selective loading, paged previews and profiling.

Data never travels to the browser in bulk: previews are paged server-side through DuckDB,
and analyses load only the columns they use.
"""

from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import pandas as pd
import polars as pl

from ..errors import AppError
from ..models import DatasetVersion, Variable
from ..storage import resolve
from .importer import _jsonable

FILTER_OPS = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<=", "contains": "ILIKE",
              "is_null": "IS NULL", "not_null": "IS NOT NULL"}


def parquet_path(version: DatasetVersion) -> str:
    return resolve(version.data_path).as_posix()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _missing_codes(var: Variable | None) -> list[Any]:
    return list(var.missing_value_codes_json or []) if var else []


def load_frame(version: DatasetVersion, columns: list[str], max_rows: int | None = None) -> pd.DataFrame:
    """Load selected columns as pandas, with user-declared missing-value codes set to NaN."""
    vars_by_name = {v.column_name: v for v in version.variables}
    unknown = [c for c in columns if c not in vars_by_name]
    if unknown:
        raise AppError("unknown_variable", f"Variable(s) not found in the dataset: {', '.join(unknown)}.", 422)
    cols = list(dict.fromkeys(columns))
    lf = pl.scan_parquet(parquet_path(version)).select(cols)
    exprs = []
    for c in cols:
        codes = _missing_codes(vars_by_name[c])
        if not codes:
            continue
        dtype = lf.collect_schema()[c]
        typed = []
        for code in codes:
            try:
                typed.append(float(code) if dtype.is_numeric() else str(code))
            except (TypeError, ValueError):
                continue
        if typed:
            target = pl.col(c).cast(pl.Float64) if dtype.is_numeric() else pl.col(c).cast(pl.String)
            exprs.append(pl.when(target.is_in(typed)).then(None).otherwise(pl.col(c)).alias(c))
    if exprs:
        lf = lf.with_columns(exprs)
    if max_rows:
        lf = lf.head(max_rows + 1)
    df = lf.collect().to_pandas()
    if max_rows and len(df) > max_rows:
        raise AppError("dataset_too_large",
                       f"This analysis is limited to {max_rows:,} rows. Filter the data (for example with the SQL "
                       "Workbench) or raise STATEASE_ANALYSIS_MAX_ROWS.", 422)
    return df


def page(version: DatasetVersion, *, offset: int = 0, limit: int = 100, sort: str | None = None,
         descending: bool = False, search: str | None = None, filters: list[dict[str, Any]] | None = None,
         columns: list[str] | None = None) -> dict[str, Any]:
    names = [v.column_name for v in version.variables]
    cols = [c for c in (columns or names) if c in names] or names
    where, params = [], []
    for f in filters or []:
        col, op = f.get("column"), f.get("op", "eq")
        if col not in names or op not in FILTER_OPS:
            raise AppError("invalid_filter", f"Invalid filter on '{col}'.", 422)
        if op in {"is_null", "not_null"}:
            where.append(f"{_quote(col)} {FILTER_OPS[op]}")
        elif op == "contains":
            where.append(f"CAST({_quote(col)} AS VARCHAR) ILIKE ?")
            params.append(f"%{f.get('value', '')}%")
        else:
            where.append(f"{_quote(col)} {FILTER_OPS[op]} ?")
            params.append(f.get("value"))
    if search:
        where.append("(" + " OR ".join(f"CAST({_quote(c)} AS VARCHAR) ILIKE ?" for c in cols) + ")")
        params += [f"%{search}%"] * len(cols)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = ""
    if sort:
        if sort not in names:
            raise AppError("invalid_sort", f"Cannot sort by '{sort}'.", 422)
        order = f" ORDER BY {_quote(sort)} {'DESC' if descending else 'ASC'} NULLS LAST"
    src = f"read_parquet('{parquet_path(version)}')"
    con = duckdb.connect()
    try:
        total = con.execute(f"SELECT COUNT(*) FROM {src}{clause}", params).fetchone()[0]
        sel = ", ".join(_quote(c) for c in cols)
        fetched = con.execute(f"SELECT {sel} FROM {src}{clause}{order} LIMIT ? OFFSET ?",
                              params + [int(limit), int(offset)]).fetchall()
    except duckdb.Error as exc:
        raise AppError("query_failed", f"Could not read the data: {str(exc).splitlines()[0]}", 422) from exc
    finally:
        con.close()
    rows = [[_jsonable(v) for v in r] for r in fetched]
    return {"columns": cols, "rows": rows, "total": total, "offset": offset, "limit": limit}


def _num(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return None if not np.isfinite(f) else f
    if isinstance(v, (int, np.integer)):
        return int(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def profile(version: DatasetVersion) -> dict[str, Any]:
    """Whole-dataset profile computed lazily (streaming) from Parquet."""
    variables = list(version.variables)
    names = [v.column_name for v in variables]
    lf = pl.scan_parquet(parquet_path(version))
    schema = lf.collect_schema()
    df_cols = load_frame_lazy(version, lf)
    aggs: list[pl.Expr] = [pl.len().alias("__rows"),
                           pl.all_horizontal([pl.col(c).is_not_null() for c in names]).sum().alias("__complete")]
    for v in variables:
        c = v.column_name
        aggs += [pl.col(c).null_count().alias(f"{c}__missing"), pl.col(c).n_unique().alias(f"{c}__unique")]
        if schema[c].is_numeric():
            x = pl.col(c).cast(pl.Float64)
            aggs += [x.mean().alias(f"{c}__mean"), x.std().alias(f"{c}__sd"), x.min().alias(f"{c}__min"),
                     x.max().alias(f"{c}__max"), x.median().alias(f"{c}__median")]
        elif schema[c].is_temporal():
            aggs += [pl.col(c).min().alias(f"{c}__min"), pl.col(c).max().alias(f"{c}__max")]
    stats = df_cols.select(aggs).collect(engine="streaming").row(0, named=True)
    rows = int(stats["__rows"])

    # Duplicate rows (DuckDB spills to disk for large data).
    con = duckdb.connect()
    try:
        distinct = con.execute(f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM read_parquet('{parquet_path(version)}'))"
                               ).fetchone()[0]
    finally:
        con.close()

    columns = []
    total_missing = 0
    warnings: list[dict[str, Any]] = []
    for v in variables:
        c = v.column_name
        missing = int(stats[f"{c}__missing"])
        unique = int(stats[f"{c}__unique"]) - (1 if missing else 0)
        total_missing += missing
        col: dict[str, Any] = {"name": c, "missing": missing, "unique": unique,
                               "missing_pct": (missing / rows * 100) if rows else 0}
        for k in ("mean", "sd", "min", "max", "median"):
            if f"{c}__{k}" in stats:
                col[k] = _num(stats[f"{c}__{k}"])
        if unique <= 50 and v.measurement_level in {"nominal", "ordinal", "binary"}:
            counts = (df_cols.group_by(c).agg(pl.len().alias("n")).sort("n", descending=True).head(50)
                      .collect(engine="streaming"))
            col["categories"] = [{"value": _num(r[c]), "count": int(r["n"])} for r in counts.iter_rows(named=True)
                                 if r[c] is not None]
        columns.append(col)
        if rows and missing / rows > 0.2:
            warnings.append({"code": "high_missing", "column": c,
                             "message": f"'{c}' is missing for {missing / rows:.0%} of rows."})
        if unique == 1:
            warnings.append({"code": "constant", "column": c,
                             "message": f"'{c}' has the same value in every row and cannot be analysed."})
        if unique == 0:
            warnings.append({"code": "all_missing", "column": c, "message": f"'{c}' has no values."})
        if v.measurement_level == "nominal" and unique > 30:
            warnings.append({"code": "many_categories", "column": c,
                             "message": f"'{c}' has {unique} categories; group comparisons may be impractical."})
    duplicates = rows - int(distinct)
    if duplicates:
        warnings.insert(0, {"code": "duplicate_rows",
                            "message": f"{duplicates:,} row(s) are exact duplicates of another row. Check whether "
                                       "records were entered twice."})
    return {"rows": rows, "columns": len(names), "total_missing": total_missing, "duplicate_rows": duplicates,
            "complete_rows": int(stats["__complete"]), "variables": columns, "warnings": warnings}


def load_frame_lazy(version: DatasetVersion, lf: pl.LazyFrame) -> pl.LazyFrame:
    """Apply declared missing-value codes lazily (used for profiling)."""
    schema = lf.collect_schema()
    exprs = []
    for v in version.variables:
        codes = _missing_codes(v)
        if not codes:
            continue
        c = v.column_name
        numeric = schema[c].is_numeric()
        typed = []
        for code in codes:
            try:
                typed.append(float(code) if numeric else str(code))
            except (TypeError, ValueError):
                pass
        target = pl.col(c).cast(pl.Float64) if numeric else pl.col(c).cast(pl.String)
        if typed:
            exprs.append(pl.when(target.is_in(typed)).then(None).otherwise(pl.col(c)).alias(c))
    return lf.with_columns(exprs) if exprs else lf


def column_values(version: DatasetVersion, column: str, limit: int = 200) -> list[dict[str, Any]]:
    lf = load_frame_lazy(version, pl.scan_parquet(parquet_path(version)).select(column))
    counts = (lf.group_by(column).agg(pl.len().alias("n")).sort("n", descending=True).head(limit)
              .collect(engine="streaming"))
    return [{"value": _num(r[column]), "count": int(r["n"])} for r in counts.iter_rows(named=True)]
