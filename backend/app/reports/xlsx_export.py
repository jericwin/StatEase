"""Excel workbook generation with openpyxl. Numbers are stored as numeric cells with number formats."""

from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.comments import Comment
from openpyxl.drawing.image import Image as XLImage
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import charts
from .options import ReportOptions, chosen_charts, filter_table, interpretation_text

SHEET_FOR_CATEGORY = {"descriptives": "Descriptive Statistics", "compare": "T-Test Results", "anova": "ANOVA Results",
                      "correlation": "Correlations", "regression": "Regression", "nonparametric": "Nonparametric Tests",
                      "categorical": "Categorical Tests", "reliability": "Reliability", "assumptions": "Assumption Checks"}
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=12, color="1F3A5F")
THIN = Side(style="thin", color="BFC7D5")
SIG_FILL = PatternFill("solid", fgColor="E8F0FA")


def _number_format(fmt: str, decimals: int, style: str) -> str | None:
    zero = "0." + "0" * decimals if decimals else "0"
    if fmt == "int":
        return "#,##0"
    if fmt == "p":
        return '[<0.001]"<.001";.000' if style == "apa" else '[<0.001]"<0.001";0.000'
    if fmt == "pct":
        return "0.0"
    if fmt in {"num", "stat"}:
        return "#,##0." + "0" * decimals if decimals else "#,##0"
    if fmt == "r":
        return zero
    return None


def _cell_value(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


class Book:
    def __init__(self, opts: ReportOptions):
        self.opts = opts
        self.wb = Workbook()
        self.cursor: dict[str, int] = {}
        self.overview = self.wb.active
        self.overview.title = "Overview"

    def sheet(self, name: str):
        name = name[:31]
        if name not in self.wb.sheetnames:
            ws = self.wb.create_sheet(name)
            self.cursor[name] = 1
            ws.sheet_view.showGridLines = False
        return self.wb[name]

    def write_table(self, sheet_name: str, t: dict[str, Any], source: str, alpha: float) -> None:
        ws = self.sheet(sheet_name)
        r = self.cursor[ws.title]
        cols = t["columns"]
        ws.cell(r, 1, t["title"]).font = TITLE_FONT
        ws.cell(r + 1, 1, source).font = Font(italic=True, size=9, color="6B7280")
        r += 2
        first_table = r == 3
        for j, c in enumerate(cols, start=1):
            cell = ws.cell(r, j, c["label"])
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
            cell.alignment = Alignment(horizontal="center" if c["fmt"] != "text" else "left", vertical="center",
                                       wrap_text=True)
        header_row = r
        for row in t["rows"]:
            r += 1
            for j, c in enumerate(cols, start=1):
                v = _cell_value(row.get(c["key"]))
                cell = ws.cell(r, j, v)
                if c["key"] in (row.get("_manual") or []):
                    cell.comment = Comment("Entered manually; not computed by StatEase.", "StatEase")
                nf = _number_format(c["fmt"], self.opts.decimals, self.opts.style)
                if nf and isinstance(v, (int, float)):
                    cell.number_format = nf
                cell.border = Border(bottom=THIN)
                if row.get("_style") == "total":
                    cell.font = Font(bold=True)
                elif row.get("_style") == "muted":
                    cell.font = Font(italic=True, color="6B7280")
        p_cols = [j for j, c in enumerate(cols, start=1) if c["fmt"] == "p"]
        if r > header_row:
            for j in p_cols:
                letter = get_column_letter(j)
                ws.conditional_formatting.add(f"{letter}{header_row + 1}:{letter}{r}",
                                              CellIsRule(operator="lessThan", formula=[str(alpha)], fill=SIG_FILL,
                                                         font=Font(bold=True)))
        for note in [n for n in t.get("notes") or [] if n]:
            r += 1
            ws.cell(r, 1, "Note. " + note).font = Font(italic=True, size=9)
        if first_table:
            ws.freeze_panes = ws.cell(header_row + 1, 1)
        for j, c in enumerate(cols, start=1):
            letter = get_column_letter(j)
            width = max(len(str(c["label"])), *(len(str(row.get(c["key"]) or ""))
                                                 if c["fmt"] == "text" else 10 for row in t["rows"]), 8)
            ws.column_dimensions[letter].width = max(ws.column_dimensions[letter].width or 0, min(width + 2, 50))
        self.cursor[ws.title] = r + 3

    def image(self, sheet_name: str, spec: dict[str, Any], label: str) -> bool:
        try:
            png = charts.render(spec, width=6.4, height=3.8)
        except Exception:  # noqa: BLE001
            return False
        ws = self.sheet(sheet_name)
        r = self.cursor[ws.title]
        ws.cell(r, 1, label).font = TITLE_FONT
        if spec.get("caption"):
            ws.cell(r + 1, 1, spec["caption"]).font = Font(italic=True, size=9)
        img = XLImage(io.BytesIO(png))
        img.width, img.height = 640, 380
        ws.add_image(img, f"A{r + 2}")
        self.cursor[ws.title] = r + 23
        return True


def build_xlsx(path: Path, opts: ReportOptions, info: dict[str, Any], items: list[dict[str, Any]],
               data_rows: tuple[list[str], list[list[Any]]] | None = None) -> dict[str, Any]:
    book = Book(opts)
    ov = book.overview
    ov.sheet_view.showGridLines = False
    ov["A1"] = opts.title
    ov["A1"].font = Font(bold=True, size=14, color="1F3A5F")
    meta = [("Project", info.get("project")), ("Dataset", info["dataset"]), ("Source file", info.get("source")),
            ("Rows", info["rows"]), ("Columns", info["columns"]), ("Significance level (α)", info["alpha"]),
            ("Exported", datetime.now().strftime("%Y-%m-%d %H:%M")), ("Generated by", "StatEase Analytics")]
    if info.get("lineage"):
        meta.insert(3, ("Derived by", info["lineage"]))
    r = 3
    for k, v in meta:
        ov.cell(r, 1, k).font = Font(bold=True)
        ov.cell(r, 2, v)
        r += 1
    r += 1
    for j, h in enumerate(["#", "Analysis", "Variables", "N", "Key statistic", "p", "Effect size", "Result sheet"], 1):
        c = ov.cell(r, j, h)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
    ov.freeze_panes = ov.cell(r + 1, 1)
    header_row = r
    tables = figures = failed = 0
    interp_rows = []
    for i, it in enumerate(items, start=1):
        res = it["result"]
        main_sheet = SHEET_FOR_CATEGORY.get(res.get("category"), "Results")
        s = res.get("summary") or {}
        r += 1
        vals = [i, res.get("title"), res.get("heading") or res.get("plain_title"), res.get("n"), s.get("statistic"), s.get("p"),
                s.get("effect"), main_sheet]
        for j, v in enumerate(vals, 1):
            c = ov.cell(r, j, _cell_value(v))
            if j in (5, 7) and isinstance(v, (int, float)):
                c.number_format = "0.000"
            if j == 6 and isinstance(v, (int, float)):
                c.number_format = _number_format("p", 3, opts.style)
        source = f"Analysis {i}: {res.get('title')}" + (f" — {res['heading']}" if res.get("heading") else "")
        for t in res.get("tables") or []:
            ft = filter_table(t, opts)
            if not ft or not ft["rows"]:
                continue
            sheet = {"descriptives": "Descriptive Statistics", "frequencies": "Descriptive Statistics",
                     "posthoc": "Post Hoc Comparisons", "assumptions": "Assumption Checks"}.get(t["kind"], main_sheet)
            book.write_table(sheet, ft, source, info["alpha"])
            tables += 1
        if opts.on("assumptions") and res.get("assumptions"):
            book.write_table("Assumption Checks", {
                "title": f"Assumptions — {res.get('title')}", "kind": "assumptions", "notes": [],
                "columns": [{"key": "name", "label": "Check", "fmt": "text"}, {"key": "status", "label": "Status", "fmt": "text"},
                            {"key": "statistic", "label": "Statistic", "fmt": "stat"}, {"key": "p", "label": "p", "fmt": "p"},
                            {"key": "message", "label": "Details", "fmt": "text"}],
                "rows": [{**a, "status": {"ok": "Met", "warning": "Caution", "violated": "Not met",
                                          "info": "Note"}.get(a["status"])} for a in res["assumptions"]]},
                source, info["alpha"])
        for spec in chosen_charts(res, it["run_id"], opts):
            if book.image("Charts", spec, f"{source} — {spec['title']}"):
                figures += 1
            else:
                failed += 1
        if opts.on("interpretation"):
            text = interpretation_text(res, it["run_id"], opts, it.get("edited_interpretation"))
            if text:
                interp_rows.append({"analysis": res.get("title"), "text": text, "warnings": " ".join(res.get("warnings") or [])})
    if interp_rows:
        book.write_table("Interpretations", {"title": "Interpretations", "kind": "main", "notes": [],
                                             "columns": [{"key": "analysis", "label": "Analysis", "fmt": "text"},
                                                         {"key": "text", "label": "Interpretation", "fmt": "text"},
                                                         {"key": "warnings", "label": "Warnings", "fmt": "text"}],
                                             "rows": interp_rows}, "", info["alpha"])
        ws = book.wb["Interpretations"]
        ws.column_dimensions["B"].width = 100
        for row in ws.iter_rows(min_row=4):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    if opts.include_variable_dictionary and info.get("variables"):
        ws = book.sheet("Variable Dictionary")
        heads = ["Variable", "Label", "Measurement level", "Storage type", "Missing-value codes", "Category labels", "Unit"]
        for j, h in enumerate(heads, 1):
            c = ws.cell(1, j, h)
            c.fill, c.font = HEADER_FILL, HEADER_FONT
        for i, v in enumerate(info["variables"], start=2):
            vals = [v["name"], v.get("label"), v["level"], v.get("data_type"),
                    ", ".join(map(str, v.get("missing_codes") or [])),
                    "; ".join(f"{k} = {lbl}" for k, lbl in (v.get("category_labels") or {}).items()), v.get("unit")]
            for j, val in enumerate(vals, 1):
                ws.cell(i, j, val)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:G{len(info['variables']) + 1}"
        for j, w in enumerate([24, 30, 18, 14, 18, 40, 10], 1):
            ws.column_dimensions[get_column_letter(j)].width = w
    if data_rows is not None:
        cols, rows = data_rows
        ws = book.wb.create_sheet("Data")
        ws.append(cols)
        for c in ws[1]:
            c.fill, c.font = HEADER_FILL, HEADER_FONT
        for row in rows:
            ws.append([_cell_value(v) for v in row])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(max(len(cols), 1))}{len(rows) + 1}"
    for j, w in enumerate([5, 34, 44, 8, 14, 10, 12, 24], 1):
        ov.column_dimensions[get_column_letter(j)].width = w
    ov.column_dimensions["A"].width = 24
    if r > header_row:
        ov.auto_filter.ref = f"A{header_row}:H{r}"
    book.wb.save(path)
    return {"tables": tables, "figures": figures, "figures_failed": failed, "sheets": book.wb.sheetnames}


def verify_xlsx(path: Path) -> dict[str, Any]:
    wb = load_workbook(str(path))
    return {"sheets": wb.sheetnames}


COMPARISON_TYPES = ("compare", "independent", "paired", "one_way", "welch", "mann", "kruskal", "wilcoxon", "friedman",
                    "factorial", "rm_", "mixed", "ancova", "one_sample")


def _native_chart(ws, spec: dict[str, Any], anchor_row: int) -> int | None:
    """Writes the chart's data and an editable Excel column chart; returns the next free row (None if unsupported)."""
    d = spec["data"]
    if spec["type"] in ("means", "bar", "interaction"):
        cats, series = d.get("categories", []), d.get("series", [])
    elif spec["type"] == "meanci":
        groups = [g for g in d.get("groups", []) if g.get("mean") is not None]
        cats = [g["name"] for g in groups]
        series = [{"name": spec.get("y_label") or "Mean", "values": [g["mean"] for g in groups]}]
    else:
        return None
    if not cats or not series:
        return None
    r0 = anchor_row
    ws.cell(r0, 1, spec.get("title")).font = TITLE_FONT
    ws.cell(r0 + 1, 1, spec.get("x_label") or "Category").font = Font(bold=True)
    for j, s in enumerate(series, start=2):
        ws.cell(r0 + 1, j, s["name"]).font = Font(bold=True)
    for i, c in enumerate(cats):
        ws.cell(r0 + 2 + i, 1, c)
        for j, s in enumerate(series, start=2):
            ws.cell(r0 + 2 + i, j, _cell_value(s["values"][i])).number_format = "0.00"
    last = r0 + 1 + len(cats)
    style = spec.get("style") or {"interaction": "line", "meanci": "dot"}.get(spec["type"], "stacked" if d.get("stacked") else "bar")
    if style == "pie":
        chart = PieChart()
    elif style in ("line", "dot"):
        chart = LineChart()
    else:
        chart = BarChart()
        chart.type = "bar" if style == "hbar" else "col"
        if style == "stacked":
            chart.grouping, chart.overlap = "stacked", 100
    chart.title = spec.get("title")
    if style != "pie":
        chart.y_axis.title = spec.get("y_label") or ""
        chart.x_axis.title = spec.get("x_label") or ""
    chart.height, chart.width = 7.5, 15
    chart.add_data(Reference(ws, min_col=2, max_col=1 + len(series), min_row=r0 + 1, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=r0 + 2, max_row=last))
    if style in ("line", "dot"):
        for s in chart.series:
            s.marker.symbol = "circle"
            s.smooth = False
            if style == "dot":
                s.graphicalProperties.line.noFill = True
    ws.add_chart(chart, f"{get_column_letter(len(series) + 3)}{r0}")
    return max(last + 3, r0 + 18)


def build_report_xlsx(path: Path, report: dict[str, Any], info: dict[str, Any],
                      data_rows: tuple[list[str], list[list[Any]]] | None = None) -> dict[str, Any]:
    o = report["options"]
    opts = ReportOptions(title=report["title"], style=o.get("style", "apa"), decimals=int(o.get("decimals", 2)))
    book = Book(opts)
    ov = book.overview
    ov.title = "Summary"
    ov.sheet_view.showGridLines = False
    ov["A1"] = report["title"]
    ov["A1"].font = Font(bold=True, size=14, color="1F3A5F")
    meta = [("Project", info.get("project")), ("Dataset", info.get("dataset")),
            ("Significance level (\u03b1)", info.get("alpha")), ("Exported", datetime.now().strftime("%Y-%m-%d %H:%M"))]
    if info.get("synthetic"):
        meta.append(("Note", "Fictional sample data for demonstration"))
    r = 3
    for k, v in meta:
        ov.cell(r, 1, k).font = Font(bold=True)
        ov.cell(r, 2, v)
        r += 1
    objectives = [x for x in report.get("objectives") or [] if x.get("text")]
    if objectives:
        r += 1
        ov.cell(r, 1, "Objectives").font = TITLE_FONT
        for i, ob in enumerate(objectives, start=1):
            r += 1
            ov.cell(r, 1, i)
            ov.cell(r, 2, ob["text"])
    r += 2
    for j, h in enumerate(["#", "Component", "Title", "Sheet"], 1):
        c = ov.cell(r, j, h)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
    tables = figures = failed = 0
    texts = []
    section = ""
    n = 0
    chart_row = 1
    for b in report["blocks"]:
        if not b.get("include") or b.get("missing"):
            continue
        n += 1
        sheet = ""
        if b["type"] == "heading":
            section = b.get("resolved_text") or ""
        elif b["type"] == "table":
            t = b["resolved"]
            atype = (b.get("analysis") or {}).get("analysis_type") or ""
            if t.get("kind") in ("descriptives", "frequencies"):
                sheet = "Descriptive Statistics"
            elif t.get("kind") == "posthoc" or atype.startswith(COMPARISON_TYPES):
                sheet = "Comparisons"
            else:
                sheet = "Other Analyses"
            book.write_table(sheet, t, section, info.get("alpha", 0.05))
            tables += 1
        elif b["type"] == "chart":
            sheet = "Charts"
            ws = book.sheet("Charts")
            nxt = _native_chart(ws, b["resolved"], chart_row)
            if nxt is None:
                book.cursor["Charts"] = chart_row
                if book.image("Charts", b["resolved"], b["resolved"].get("title", "")):
                    nxt = book.cursor["Charts"]
                    figures += 1
                else:
                    nxt = chart_row
                    failed += 1
                    sheet = "(chart could not be rendered)"
            else:
                figures += 1
            chart_row = nxt
        else:
            sheet = "Interpretations"
            texts.append({"section": section, "text": b.get("resolved_text") or ""})
        r += 1
        ov.cell(r, 1, n)
        ov.cell(r, 2, b["type"].title())
        ov.cell(r, 3, (b.get("resolved") or {}).get("title") or b.get("title") or b.get("resolved_text") or "")
        ov.cell(r, 4, sheet)
    if texts:
        book.write_table("Interpretations", {"title": "Interpretations", "kind": "main", "notes": [],
                                             "columns": [{"key": "section", "label": "Section", "fmt": "text"},
                                                         {"key": "text", "label": "Text", "fmt": "text"}],
                                             "rows": texts}, "", info.get("alpha", 0.05))
        ws = book.wb["Interpretations"]
        ws.column_dimensions["B"].width = 110
        for row in ws.iter_rows(min_row=4):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    if data_rows is not None:
        cols, rows = data_rows
        ws = book.wb.create_sheet("Data")
        ws.append(cols)
        for c in ws[1]:
            c.fill, c.font = HEADER_FILL, HEADER_FONT
        for row in rows:
            ws.append([_cell_value(v) for v in row])
        ws.freeze_panes = "A2"
    for j, w in enumerate([8, 14, 70, 26], 1):
        ov.column_dimensions[get_column_letter(j)].width = w
    book.wb.save(path)
    return {"tables": tables, "figures": figures, "figures_failed": failed, "sheets": book.wb.sheetnames}
