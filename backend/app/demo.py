"""Three demo projects with fictional sample data. They are labelled as such everywhere they appear
and are never added to a user's own projects."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import polars as pl
from sqlalchemy.orm import Session

from .models import Project, User
from .services import create_dataset, latest_version
from .storage import new_relative_path, resolve


def _fertilizer(seed: int = 7) -> pl.DataFrame:
    """Pechay grown under three fertilizer treatments; growth measured 30 days after transplanting."""
    rng = np.random.default_rng(seed)
    n = 15
    rows = []
    for t, vigour in (("Control", 0.0), ("Vermicompost", 1.0), ("Inorganic", 0.7)):
        plant = rng.normal(0, 0.6, n)  # plant-to-plant vigour shared by all measures
        height = 17.5 + 4.2 * vigour + 1.6 * plant + rng.normal(0, 1.1, n)
        leaves = np.clip(np.round(7 + 2.4 * vigour + 0.9 * plant + rng.normal(0, 0.8, n)), 4, None).astype(int)
        width = 6.1 + 1.3 * vigour + 0.5 * plant + rng.normal(0, 0.45, n)
        weight = 38 + 22 * vigour + 7 * plant + rng.normal(0, 5, n)
        for i in range(n):
            rows.append({"Plant": f"{t[0]}{i + 1:02d}", "Treatment": t,
                         "Plant Height (cm)": round(float(height[i]), 1), "Number of Leaves": int(leaves[i]),
                         "Leaf Width (cm)": round(float(width[i]), 1), "Fresh Weight (g)": round(float(weight[i]), 1)})
    return pl.DataFrame(rows)


def _experiment(seed: int = 5) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    n = 24
    rows = []
    for g, gain in (("Control", 3.0), ("Treatment", 9.0)):
        pre = np.clip(rng.normal(58, 9, n), 25, 95)
        post = np.clip(pre + gain + rng.normal(0, 6, n), 25, 100)
        for i in range(n):
            rows.append({"Participant": f"S{len(rows) + 1:03d}", "Group": g, "Pretest": round(float(pre[i]), 1),
                         "Posttest": round(float(post[i]), 1)})
    df = pl.DataFrame(rows)
    return df.with_columns(pl.when(pl.int_range(pl.len()) == 7).then(None).otherwise(pl.col("Posttest")).alias("Posttest"))


def _survey(n: int = 240, seed: int = 2026) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    gender = rng.choice(["Female", "Male"], n, p=[0.55, 0.45])
    program = rng.choice(["Business", "Education", "Engineering", "Nursing"], n, p=[0.3, 0.25, 0.25, 0.2])
    year = rng.choice(["1st year", "2nd year", "3rd year", "4th year"], n)
    quality = rng.normal(0, 1, n) + (program == "Nursing") * 0.4
    satisfaction = 0.6 * quality + rng.normal(0, 0.8, n) + (gender == "Female") * 0.25
    intention = 0.5 * satisfaction + 0.2 * quality + rng.normal(0, 0.9, n)

    def items(latent, k, prefix):
        return {f"{prefix}{i}": np.clip(np.round(3.2 + 0.9 * latent + rng.normal(0, 0.8, n)), 1, 5).astype(int)
                for i in range(1, k + 1)}

    data = {"Respondent": np.arange(1001, 1001 + n), "Gender": gender, "Program": program, "Year Level": year}
    data |= items(quality, 4, "SQ")
    data |= items(satisfaction, 4, "CS")
    data |= items(intention, 3, "PI")
    df = pl.DataFrame(data)
    return df.with_columns(pl.mean_horizontal([f"SQ{i}" for i in range(1, 5)]).round(2).alias("Service Quality"),
                           pl.mean_horizontal([f"CS{i}" for i in range(1, 5)]).round(2).alias("Customer Satisfaction"),
                           pl.mean_horizontal([f"PI{i}" for i in range(1, 4)]).round(2).alias("Purchase Intention"))


def synthetic_survey() -> pl.DataFrame:
    return _survey()


DEMOS: dict[str, dict[str, Any]] = {
    "fertilizer": {
        "title": "Fertilizer Trial on Pechay",
        "summary": "Growth of pechay under three fertilizer treatments, 15 plants each, measured 30 days after transplanting.",
        "data": _fertilizer,
        "levels": {"Treatment": ("nominal", ["Control", "Vermicompost", "Inorganic"]), "Plant": ("identifier", None),
                   **{k: ("numeric", None) for k in ("Plant Height (cm)", "Number of Leaves", "Leaf Width (cm)",
                                                     "Fresh Weight (g)")}},
        "note": "Three treatments in a completely randomized design: no fertilizer (Control), vermicompost, and "
                "inorganic (14-14-14) fertilizer.",
        "objectives": [
            "What is the growth performance of pechay under each fertilizer treatment in terms of:\n"
            "1.1 Plant height\n1.2 Number of leaves\n1.3 Leaf width\n1.4 Fresh weight",
            "Is there a significant difference in the growth performance of pechay among the three fertilizer treatments?",
            "Which fertilizer treatment produced the best growth performance?",
        ],
    },
    "experiment": {
        "title": "Experimental Group Comparison",
        "summary": "Test scores of a control group and a treatment group before and after an intervention.",
        "data": _experiment,
        "levels": {"Group": ("nominal", None), "Pretest": ("numeric", None), "Posttest": ("numeric", None),
                   "Participant": ("identifier", None)},
        "note": "One posttest score is missing to show how missing data are reported.",
        "objectives": [
            "Determine the pretest and posttest scores of the Control and Treatment groups.",
            "Determine whether there is a significant difference in posttest scores between the Control and Treatment groups.",
            "Determine whether there is a significant difference in pretest scores between the Control and Treatment groups.",
            "Determine the relationship between pretest and posttest scores.",
        ],
    },
    "survey": {
        "title": "Survey Data Analysis",
        "summary": "Customer-experience survey with demographics, Likert items and scale scores.",
        "data": _survey,
        "levels": {"Respondent": ("identifier", None), "Gender": ("binary", None), "Program": ("nominal", None),
                   "Year Level": ("ordinal", ["1st year", "2nd year", "3rd year", "4th year"]),
                   "Service Quality": ("numeric", None), "Customer Satisfaction": ("numeric", None),
                   "Purchase Intention": ("numeric", None)},
        "note": "Scale scores are the means of their 1–5 Likert items (SQ, CS and PI).",
        "objectives": [
            "Determine the profile of the respondents in terms of gender, program and year level.",
            "Determine the level of service quality, customer satisfaction and purchase intention.",
            "Determine whether customer satisfaction differs between male and female respondents.",
            "Determine the relationship between service quality, customer satisfaction and purchase intention.",
        ],
    },
}


def list_demos() -> list[dict[str, Any]]:
    out = []
    for key, d in DEMOS.items():
        df = d["data"]()
        out.append({"key": key, "title": d["title"], "summary": d["summary"], "rows": df.height,
                    "columns": df.columns, "objectives": d["objectives"]})
    return out


def _apply_levels(version, demo: dict[str, Any]) -> None:
    for var in version.variables:
        spec = demo["levels"].get(var.column_name)
        if spec:
            var.measurement_level = spec[0]
            if spec[1]:
                var.category_order_json = spec[1]


def create_demo_project(db: Session, user: User, key: str = "fertilizer") -> tuple[Project, int | None]:
    """Creates the demo project, runs its objectives and builds an editable report. Returns (project, report id)."""
    from .reports.service import build_report
    from .services import refresh_profile
    from .stats.planner import parse_objectives

    demo = DEMOS.get(key)
    if demo is None:
        raise KeyError(key)
    project = Project(owner_id=user.id, name=f"Demo — {demo['title']}", is_demo=True,
                      description=f"Fictional sample data. {demo['summary']}", settings_json={})
    db.add(project)
    db.flush()
    rel = new_relative_path("datasets", ".parquet")
    demo["data"]().write_parquet(resolve(rel))
    ds = create_dataset(db, project, name=f"{demo['title']} (fictional sample data)", data_path=rel, fmt="parquet",
                        source_filename=f"demo_{key}.parquet", note="Fictional sample data",
                        lineage={"synthetic": True, "demo": key})
    version = latest_version(ds)
    _apply_levels(version, demo)
    db.flush()
    refresh_profile(db, version)
    db.commit()
    objectives = parse_objectives(version, demo["objectives"])
    report = build_report(db, project, ds, f"{demo['title']} — Results", objectives)
    return project, report.id


@lru_cache(maxsize=8)
def public_preview(key: str) -> dict[str, Any]:
    """Read-only preview for visitors who are not signed in: data sample plus computed results."""
    from .stats.base import REGISTRY, Context, VarMeta
    from .stats.engine import heading
    from .stats.inference_shim import infer_meta

    demo = DEMOS[key]
    df = demo["data"]()
    metas: dict[str, VarMeta] = infer_meta(df, demo["levels"])
    pdf = df.to_pandas()
    results = []
    plans = _preview_plans(key)
    for analysis_type, config in plans:
        spec = REGISTRY[analysis_type]
        ctx = Context(lambda cols: pdf[cols].copy(), metas, {"alpha": 0.05})
        ctx.filter = config.get("filter")
        res = spec.run(ctx, config).to_dict()
        res["heading"] = heading(config, metas)
        results.append({k: res[k] for k in ("title", "plain_title", "heading", "tables", "charts", "interpretation",
                                              "summary", "settings", "notes", "assumptions", "warnings")})
    return {"key": key, "title": demo["title"], "summary": demo["summary"], "note": demo["note"],
            "objectives": demo["objectives"], "columns": df.columns, "rows": [list(r) for r in df.head(12).iter_rows()],
            "n_rows": df.height, "results": results}


def _preview_plans(key: str) -> list[tuple[str, dict[str, Any]]]:
    if key == "fertilizer":
        ms = ["Plant Height (cm)", "Number of Leaves", "Leaf Width (cm)", "Fresh Weight (g)"]
        return [("compare_groups", {"variables": {"group": "Treatment", "measures": ms}, "options": {}}),
                ("descriptives", {"variables": {"variables": ms, "split_by": "Treatment"},
                                  "options": {"statistics": ["n", "mean", "sd", "min", "max"], "charts": False}})]
    if key == "experiment":
        return [("compare_two_groups", {"variables": {"group": "Group", "measures": ["Pretest", "Posttest"]},
                                        "options": {"group_a": "Control", "group_b": "Treatment"}}),
                ("correlation", {"variables": {"variables": ["Pretest", "Posttest"]}, "options": {}})]
    return [("compare_two_groups", {"variables": {"group": "Gender", "measures": ["Service Quality", "Customer Satisfaction",
                                                                                 "Purchase Intention"]}, "options": {}}),
            ("correlation", {"variables": {"variables": ["Service Quality", "Customer Satisfaction", "Purchase Intention"]},
                             "options": {}})]

