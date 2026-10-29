"""Report blocks and the presentation edits users make to tables and charts.

A block references a computed result (run + table/chart id) and stores *edits* separately, so values can
always be traced back to the computation. The same rules are implemented in the frontend
(src/lib/blocks.ts) for the live preview; exports call these functions.

Table edits: column order/labels/visibility, hidden rows, manual cell overrides, manual rows and columns.
Manually entered values are flagged (``_manual``) and marked in the UI and in exported documents.
Chart edits: type (where convertible), labels, hidden/reordered groups or series, renamed legend entries.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

MANUAL_NOTE = "† Value entered manually; not computed by StatEase."
DETAIL_GROUPS = {"statistic", "df", "ci", "effect"}


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def resolve_table(source: dict[str, Any], edits: dict[str, Any] | None, *, hide_details: bool = False) -> dict[str, Any]:
    edits = edits or {}
    src_cols = {c["key"]: c for c in source["columns"]}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in edits.get("columns") or []:
        key = e.get("key")
        if key in src_cols:
            c = dict(src_cols[key])
        elif e.get("manual"):
            c = {"key": key, "label": e.get("label") or "New column", "fmt": "text", "manual": True}
        else:
            continue  # column no longer produced by the analysis (e.g. after recomputation)
        if e.get("label"):
            c["label"] = e["label"]
        c["hidden"] = bool(e.get("hidden"))
        ordered.append(c)
        seen.add(key)
    ordered += [dict(c, hidden=False) for k, c in src_cols.items() if k not in seen]
    cols = [c for c in ordered if not c["hidden"] and not (hide_details and c.get("group") in DETAIL_GROUPS)]
    for c in cols:
        c.pop("hidden", None)

    hidden_rows = set(edits.get("hidden_rows") or [])
    cells: dict[str, Any] = edits.get("cells") or {}
    rows = []
    any_manual = False
    for i, r in enumerate(source["rows"]):
        if i in hidden_rows:
            continue
        row = dict(r)
        manual = []
        for c in cols:
            k = f"{i}:{c['key']}"
            if k in cells:
                row[c["key"]] = cells[k]
                manual.append(c["key"])
            elif c.get("manual"):
                row[c["key"]] = None
        if manual:
            row["_manual"] = manual
            any_manual = True
        rows.append(row)
    for extra in edits.get("extra_rows") or []:
        rows.append({**{c["key"]: extra.get(c["key"]) for c in cols}, "_manual": [c["key"] for c in cols]})
        any_manual = True
    if any(c.get("manual") for c in cols) and any(r.get(c["key"]) not in (None, "") for r in rows for c in cols if c.get("manual")):
        any_manual = True
    notes = list(source.get("notes") or []) if edits.get("notes") is None else [edits["notes"]] if edits["notes"] else []
    if any_manual:
        notes.append(MANUAL_NOTE)
    return {"id": source.get("id"), "kind": source.get("kind", "main"), "title": source.get("title", ""),
            "columns": cols, "rows": rows, "notes": notes}


def _convert(spec: dict[str, Any], target: str) -> dict[str, Any]:
    """meanci (one series of group means) <-> means (grouped bars with CIs)."""
    d = spec["data"]
    if spec["type"] == "meanci" and target == "means":
        groups = [g for g in d.get("groups", []) if g.get("mean") is not None]
        return {**spec, "type": "means", "data": {"categories": [g["name"] for g in groups], "series": [
            {"name": spec.get("y_label") or "Mean", "values": [g["mean"] for g in groups],
             "lower": [g.get("lower") for g in groups], "upper": [g.get("upper") for g in groups]}]}}
    if spec["type"] == "means" and target == "meanci" and len(d.get("series", [])) == 1:
        s = d["series"][0]
        return {**spec, "type": "meanci", "data": {"groups": [
            {"name": c, "mean": s["values"][i], "lower": (s.get("lower") or [None] * 999)[i],
             "upper": (s.get("upper") or [None] * 999)[i]} for i, c in enumerate(d.get("categories", []))]}}
    if spec["type"] == "means" and target == "bar":
        return {**spec, "type": "bar", "data": {"categories": d.get("categories", []),
                                                "series": [{"name": s["name"], "values": s["values"]} for s in d.get("series", [])]}}
    return spec


CATEGORY_CHARTS = ("means", "bar", "interaction", "meanci")


def chart_styles(spec: dict[str, Any]) -> list[str]:
    """How a category chart may be drawn. Stacked and pie only make sense for counts/percentages, never for means."""
    if spec["type"] not in CATEGORY_CHARTS:
        return []
    styles = ["bar", "hbar", "line", "dot"]
    if spec["type"] == "bar":
        series = spec["data"].get("series", [])
        if len(series) > 1:
            styles.append("stacked")
        if len(series) == 1 and all((v or 0) >= 0 for v in series[0].get("values", [])):
            styles.append("pie")
    return styles


def with_style(spec: dict[str, Any], style: str | None) -> dict[str, Any]:
    """Applies a drawing style; a means-with-CI point chart becomes grouped data first when drawn another way."""
    if not style or style not in chart_styles(spec):
        return spec
    if spec["type"] == "meanci":
        if style == "dot":
            return spec
        spec = _convert(spec, "means")
    return {**spec, "style": style}


def chart_types(spec: dict[str, Any]) -> list[str]:
    t = spec["type"]
    if t == "meanci":
        return ["meanci", "means"]
    if t == "means":
        return ["means", "bar"] + (["meanci"] if len(spec["data"].get("series", [])) == 1 else [])
    return [t]


def resolve_chart(source: dict[str, Any], edits: dict[str, Any] | None, title: str | None = None) -> dict[str, Any]:
    edits = edits or {}
    spec = copy.deepcopy(source)
    if edits.get("type") and edits["type"] in chart_types(spec):
        spec = _convert(spec, edits["type"])
    for k in ("x_label", "y_label", "caption"):
        if edits.get(k) is not None:
            spec[k] = edits[k]
    if title:
        spec["title"] = title
    hidden = set(edits.get("hidden") or [])
    order = edits.get("order") or []
    labels = edits.get("labels") or {}

    def rank(name: str) -> int:
        return order.index(name) if name in order else len(order) + 1

    d = spec["data"]
    if spec["type"] in ("box", "meanci"):
        groups = [g for g in d.get("groups", []) if g.get("name") not in hidden]
        groups.sort(key=lambda g: rank(g.get("name")))
        for g in groups:
            g["name"] = labels.get(g["name"], g["name"])
        d["groups"] = groups
    elif spec["type"] in ("means", "bar", "interaction"):
        cats = d.get("categories", [])
        keep = sorted([i for i, c in enumerate(cats) if c not in hidden], key=lambda i: rank(cats[i]))
        d["categories"] = [labels.get(cats[i], cats[i]) for i in keep]
        series = []
        for s in d.get("series", []):
            if s.get("name") in hidden:
                continue
            s2 = {**s, "name": labels.get(s["name"], s["name"])}
            for key in ("values", "lower", "upper"):
                if isinstance(s.get(key), list):
                    s2[key] = [s[key][i] for i in keep]
            series.append(s2)
        series.sort(key=lambda s: rank(s["name"]))
        d["series"] = series
    return with_style(spec, edits.get("style"))


def chart_names(spec: dict[str, Any]) -> list[str]:
    """Group/category/series names a user can hide, reorder or rename."""
    d = spec.get("data", {})
    if spec["type"] in ("box", "meanci"):
        return [g.get("name") for g in d.get("groups", [])]
    if spec["type"] in ("means", "bar", "interaction"):
        return list(d.get("categories", [])) + [s["name"] for s in d.get("series", [])]
    return []
