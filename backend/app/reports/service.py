"""Report construction, resolution and recomputation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import AppError
from ..jobs import submit
from ..models import AnalysisConfiguration, AnalysisResult, AnalysisRun, Dataset, DatasetVersion, Project, Report
from ..services import latest_version
from ..stats.base import REGISTRY
from .blocks import chart_names, chart_types, new_id, resolve_chart, resolve_table

AUTO_TABLE_KINDS = {"descriptives", "frequencies", "main", "posthoc", "effect"}


def run_analysis(db: Session, project: Project, version: DatasetVersion, analysis_type: str, variables: dict,
                 options: dict | None = None, filter_: dict | None = None, name: str | None = None,
                 source: str = "report") -> AnalysisRun:
    if analysis_type not in REGISTRY:
        raise AppError("unknown_analysis", f"Unknown analysis '{analysis_type}'.", 422)
    cfg = {"variables": variables, "options": options or {}}
    if filter_ and filter_.get("column") and filter_.get("values"):
        cfg["filter"] = filter_
    pos = (db.scalar(select(AnalysisConfiguration.position).where(AnalysisConfiguration.project_id == project.id)
                     .order_by(AnalysisConfiguration.position.desc())) or 0) + 1
    c = AnalysisConfiguration(project_id=project.id, dataset_version_id=version.id, analysis_type=analysis_type,
                              name=name, configuration_json=cfg, source="recommended" if source == "report" else source,
                              position=pos)
    db.add(c)
    db.flush()
    run = AnalysisRun(configuration_id=c.id, dataset_version_id=version.id, status="queued", parameters_json=cfg)
    db.add(run)
    db.commit()
    submit(run.id, sync=True)
    db.refresh(run)
    return run


def _result(db: Session, run_id: int) -> dict[str, Any] | None:
    r = db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id == run_id))
    return r.result_json if r else None


def scoped_title(title: str, result: dict[str, Any]) -> str:
    """Name the subset in the title (e.g. 'Descriptive Statistics: Formulation 1') so tables are self-explanatory."""
    f = result.get("filter") or {}
    values = [str(v) for v in f.get("values") or []]
    if values and not any(v in title for v in values):
        return f"{title}: {', '.join(values)}"
    return title


def blocks_for_result(result: dict[str, Any], run_id: int, objective_id: str | None = None,
                      all_tables: bool = False) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for t in result.get("tables", []):
        if all_tables or t["kind"] in AUTO_TABLE_KINDS:
            blocks.append({"id": new_id(), "type": "table", "include": True, "objective_id": objective_id,
                           "title": scoped_title(t["title"], result), "source": {"run_id": run_id, "table_id": t["id"]},
                           "edits": {}})
    charts = result.get("charts", [])
    preferred = next((c for c in charts if c["type"] in ("means", "meanci", "bar")), charts[0] if charts else None)
    for c in charts:
        blocks.append({"id": new_id(), "type": "chart", "include": c is preferred, "objective_id": objective_id,
                       "title": scoped_title(c["title"], result), "source": {"run_id": run_id, "chart_id": c["id"]},
                       "edits": {}})
    blocks.append({"id": new_id(), "type": "text", "include": True, "objective_id": objective_id,
                   "title": "Interpretation", "source": {"run_id": run_id, "field": "interpretation"}, "text": None})
    return blocks


def build_report(db: Session, project: Project, dataset: Dataset | None, title: str,
                 objectives: list[dict[str, Any]] | None) -> Report:
    blocks: list[dict[str, Any]] = []
    stored_objectives = []
    if objectives:
        if dataset is None:
            raise AppError("no_dataset", "Choose the dataset the objectives refer to.", 422)
        version = latest_version(dataset)
        for i, o in enumerate(objectives, start=1):
            oid = o.get("id") or f"o{i}"
            text = o.get("full_text") or o["text"]
            analyses = o.get("analyses") or ([{k: o.get(k) for k in ("analysis_type", "variables", "options", "filter",
                                                                       "title")}] if o.get("analysis_type") else [])
            entry = {"id": oid, "text": text, "status": o.get("status", "ready"),
                     "analysis_type": analyses[0]["analysis_type"] if analyses else None,
                     "run_id": None, "run_ids": [], "error": None}
            blocks.append({"id": new_id(), "type": "heading", "include": True, "objective_id": oid,
                           "text": f"Objective {i}: {o['text']}"})
            ready = [a for a in analyses if a.get("analysis_type") and a.get("status", "ready") == "ready"]
            if o.get("status") != "ready" or not ready:
                entry["error"] = o.get("question") or "This objective has no analysis yet."
                stored_objectives.append(entry)
                continue
            for a in ready:
                run = run_analysis(db, project, version, a["analysis_type"], a.get("variables") or {}, a.get("options"),
                                   a.get("filter"), name=a.get("title"))
                entry["run_ids"].append(run.id)
                entry["run_id"] = entry["run_id"] or run.id
                if run.status != "completed":
                    entry["error"] = run.error_message
                    blocks.append({"id": new_id(), "type": "text", "include": True, "objective_id": oid, "title": "Note",
                                   "text": f"This part of the objective could not be analysed: {run.error_message}"})
                else:
                    blocks += blocks_for_result(_result(db, run.id), run.id, oid)
            stored_objectives.append(entry)
    else:
        configs = db.scalars(select(AnalysisConfiguration).where(AnalysisConfiguration.project_id == project.id)
                             .order_by(AnalysisConfiguration.position, AnalysisConfiguration.id)).all()
        for c in configs:
            run = db.scalar(select(AnalysisRun).where(AnalysisRun.configuration_id == c.id, AnalysisRun.status == "completed")
                            .order_by(AnalysisRun.id.desc()))
            res = _result(db, run.id) if run else None
            if res:
                heading = res.get("heading") or res.get("plain_title")
                blocks.append({"id": new_id(), "type": "heading", "include": True, "objective_id": None,
                               "text": f"{res.get('title')}: {heading}" if heading else res.get("title")})
                blocks += blocks_for_result(res, run.id)
        if not blocks:
            raise AppError("nothing_to_report", "Run at least one analysis, or enter study objectives.", 422)
    report = Report(project_id=project.id, dataset_id=dataset.id if dataset else None, title=title,
                    objectives_json=stored_objectives, blocks_json=blocks,
                    options_json={"style": "apa", "decimals": project.settings_json.get("decimals", 2) if project.settings_json else 2,
                                  "include_details": True, "include_methods": True})
    db.add(report)
    db.commit()
    return report


def resolve(db: Session, report: Report, *, for_export: bool = False) -> dict[str, Any]:
    """Attach the computed source (table/chart/interpretation) to each block, with edits applied."""
    cache: dict[int, dict[str, Any] | None] = {}
    configs: dict[int, AnalysisConfiguration] = {}
    hide = not report.options_json.get("include_details", True)
    out = []
    for b in report.blocks_json:
        rb = dict(b)
        src = b.get("source") or {}
        rid = src.get("run_id")
        if rid:
            if rid not in cache:
                cache[rid] = _result(db, rid)
                run = db.get(AnalysisRun, rid)
                if run:
                    configs[rid] = db.get(AnalysisConfiguration, run.configuration_id)
            res = cache[rid]
            if res is None:
                rb["missing"] = True
                out.append(rb)
                continue
            cfg = configs.get(rid)
            rb["analysis"] = {"analysis_type": res.get("analysis_type"), "title": res.get("title"),
                              "heading": res.get("heading"), "variables": res.get("variables"),
                              "options": res.get("options"), "filter": res.get("filter"),
                              "dataset_version_id": res.get("dataset_version_id"),
                              "configuration_id": cfg.id if cfg else None, "method": res.get("method"),
                              "settings": res.get("settings"), "warnings": res.get("warnings")}
            if b["type"] == "table":
                table = next((t for t in res.get("tables", []) if t["id"] == src.get("table_id")), None)
                if table is None:
                    rb["missing"] = True
                else:
                    rb["source_table"] = table
                    rb["resolved"] = resolve_table(table, b.get("edits"), hide_details=hide and for_export)
                    rb["resolved"]["title"] = b.get("title") or table["title"]
            elif b["type"] == "chart":
                chart = next((c for c in res.get("charts", []) if c["id"] == src.get("chart_id")), None)
                if chart is None:
                    rb["missing"] = True
                else:
                    rb["source_chart"] = chart
                    rb["chart_types"] = chart_types(chart)
                    rb["chart_names"] = chart_names(chart)
                    rb["resolved"] = resolve_chart(chart, b.get("edits"), b.get("title"))
                    rb["alternatives"] = [{"id": c["id"], "title": c["title"], "type": c["type"]} for c in res.get("charts", [])]
            elif b["type"] == "text":
                interp = res.get("interpretation") or {}
                rb["generated"] = interp
                if b.get("text") is None:
                    edited = db.scalar(select(AnalysisResult.edited_interpretation)
                                       .where(AnalysisResult.analysis_run_id == rid))
                    rb["resolved_text"] = edited or interp.get(report.options_json.get("interpretation", "technical"),
                                                                interp.get("technical", ""))
                else:
                    rb["resolved_text"] = b["text"]
        else:
            rb["resolved_text"] = b.get("text") or ""
        out.append(rb)
    return {"id": report.id, "project_id": report.project_id, "dataset_id": report.dataset_id, "title": report.title,
            "objectives": report.objectives_json, "options": report.options_json, "blocks": out,
            "created_at": report.created_at.isoformat(), "updated_at": report.updated_at.isoformat()}


def rebind(db: Session, project: Project, report: Report, block_id: str, body: dict[str, Any]) -> None:
    """Point a table/chart/text block at a new computation (recomputed from the dataset) or an existing run."""
    blocks = list(report.blocks_json)
    idx = next((i for i, b in enumerate(blocks) if b["id"] == block_id), None)
    if idx is None:
        raise AppError("not_found", "Block not found.", 404)
    block = dict(blocks[idx])
    src = dict(block.get("source") or {})
    if body.get("run_id"):
        run = db.get(AnalysisRun, body["run_id"])
        if run is None or db.get(AnalysisConfiguration, run.configuration_id).project_id != project.id:
            raise AppError("invalid_run", "That result does not belong to this project.", 422)
        new_run = run
    else:
        old = db.get(AnalysisRun, src.get("run_id"))
        if old is None:
            raise AppError("invalid_block", "This block is not linked to an analysis.", 422)
        cfg = db.get(AnalysisConfiguration, old.configuration_id)
        params = cfg.configuration_json or {}
        version = latest_version(db.get(Dataset, db.get(DatasetVersion, old.dataset_version_id).dataset_id))
        variables = body.get("variables", params.get("variables", {}))
        options = body.get("options", params.get("options", {}))
        filter_ = body.get("filter", params.get("filter"))
        new_run = run_analysis(db, project, version, cfg.analysis_type, variables, options, filter_)
        if new_run.status != "completed":
            raise AppError("analysis_failed", new_run.error_message or "The analysis could not be recomputed.", 422)
    res = _result(db, new_run.id) or {}
    src["run_id"] = new_run.id
    if block["type"] == "table":
        ids = [t["id"] for t in res.get("tables", [])]
        want = body.get("table_id") or src.get("table_id")
        src["table_id"] = want if want in ids else next((t["id"] for t in res.get("tables", []) if t["kind"] == "main"),
                                                        ids[0] if ids else None)
        e = dict(block.get("edits") or {})
        # Row-level manual edits refer to the old rows; they are dropped so no stale value survives.
        for k in ("cells", "hidden_rows"):
            e.pop(k, None)
        block["edits"] = e
        if body.get("table_id") or not block.get("title_edited"):
            t = next((t for t in res.get("tables", []) if t["id"] == src["table_id"]), None)
            if t:
                block["title"] = scoped_title(t["title"], res)
    elif block["type"] == "chart":
        ids = [c["id"] for c in res.get("charts", [])]
        want = body.get("chart_id") or src.get("chart_id")
        src["chart_id"] = want if want in ids else (ids[0] if ids else None)
        e = dict(block.get("edits") or {})
        e.pop("hidden", None)
        e.pop("order", None)
        block["edits"] = e
        if not block.get("title_edited"):
            c = next((c for c in res.get("charts", []) if c["id"] == src["chart_id"]), None)
            if c:
                block["title"] = scoped_title(c["title"], res)
    elif block["type"] == "text":
        block["text"] = None
    block["source"] = src
    blocks[idx] = block
    report.blocks_json = blocks
    db.commit()
