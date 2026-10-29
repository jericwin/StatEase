"""Recommendation engine: suggests appropriate analyses from variable types, group structure and data.

Rules (not correlations observed in the data) decide what is suggested, so recommendations do not
amount to data dredging. Variable names only raise or lower the ranking; they never decide which test
is valid. Every suggestion explains what it answers and what it assumes.
"""

from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations
from typing import Any

import polars as pl

from ..data.store import parquet_path
from ..models import DatasetVersion

OUTCOME_WORDS = re.compile(
    r"score|satisf|intent|perform|grade|gpa|achiev|income|salary|sales|revenue|quality|attitude|percep|loyal|trust|"
    r"engag|stress|anxiety|depress|motivat|wellbeing|well_being|happiness|commit|effective|efficacy|knowledge|"
    r"awareness|competen|readiness|productiv|outcome|total|index|composite|mean|level|rating|exam|test|result|"
    r"weight|height|bmi|time|duration|cost|price|spend|usage|adoption|behavio|experience|value|benefit", re.I)
GROUP_WORDS = re.compile(
    r"gender|sex|education|educ|year|level|course|program|strand|track|department|dept|status|civil|marital|"
    r"group|treatment|condition|formulation|formula|product|sample|brand|variant|recipe|batch|section|region|location|type|category|age_?group|income_?(bracket|group)|"
    r"employment|occupation|position|rank|school|college|class|religion|ethnic|tenure|experience_?group", re.I)
BINARY_OUTCOME_WORDS = re.compile(r"purchas|pass|churn|default|success|adopt|buy|enrol|dropout|retain|decision|"
                                  r"outcome|result|recommend|hired|admit", re.I)
PAIR_PATTERNS = [
    (re.compile(r"^(pre)[\s_.-]*(?P<stem>.+)$", re.I), re.compile(r"^(post)[\s_.-]*(?P<stem>.+)$", re.I)),
    (re.compile(r"^(?P<stem>.+?)[\s_.-]*(pre|pretest|before|baseline)$", re.I),
     re.compile(r"^(?P<stem>.+?)[\s_.-]*(post|posttest|after|followup|follow_up)$", re.I)),
    (re.compile(r"^(before)[\s_.-]*(?P<stem>.+)$", re.I), re.compile(r"^(after)[\s_.-]*(?P<stem>.+)$", re.I)),
    (re.compile(r"^(pretest)[\s_.-]*(?P<stem>.*)$", re.I), re.compile(r"^(posttest)[\s_.-]*(?P<stem>.*)$", re.I)),
]
TIME_SERIES = re.compile(r"^(?P<stem>.*?)[\s_.-]*(t|time|wave|week|month|session|trial)[\s_.-]*(?P<num>\d{1,2})$", re.I)

MAX_COMPARISONS = 10


def _key(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _rec_key(analysis_type: str, variables: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps([analysis_type, variables], sort_keys=True).encode()).hexdigest()[:16]


def _label(v) -> str:
    return v.variable_label or v.column_name


def recommend(version: DatasetVersion) -> dict[str, Any]:
    variables = list(version.variables)
    prof = {c["name"]: c for c in (version.profile_json or {}).get("variables", [])}
    rows = (version.profile_json or {}).get("rows") or version.row_count or 0

    def usable(v) -> bool:
        p = prof.get(v.column_name, {})
        if v.measurement_level in {"identifier", "text", "date", "datetime"}:
            return False
        if p.get("unique", 2) <= 1:
            return False
        return not (rows and p.get("missing", 0) / rows > 0.5)

    use = [v for v in variables if usable(v)]
    by_name = {v.column_name: v for v in use}
    scale_groups: dict[str, list] = {}
    for v in use:
        if v.scale_group:
            scale_groups.setdefault(v.scale_group, []).append(v)
    scale_groups = {k: g for k, g in scale_groups.items() if len(g) >= 3}
    grouped_items = {v.column_name for g in scale_groups.values() for v in g}

    numeric = [v for v in use if v.measurement_level == "numeric"]
    ordinal_single = [v for v in use if v.measurement_level == "ordinal" and v.column_name not in grouped_items]
    groupers = []
    for v in use:
        if v.measurement_level not in {"nominal", "binary", "ordinal"} or v.column_name in grouped_items:
            continue
        cats = prof.get(v.column_name, {}).get("categories") or []
        k = len(cats) or prof.get(v.column_name, {}).get("unique", 0)
        if 2 <= k <= 10:
            smallest = min((c["count"] for c in cats), default=0)
            groupers.append((v, k, smallest))

    skew = _skewness(version, [v.column_name for v in numeric])
    recs: list[dict[str, Any]] = []

    def add(analysis_type: str, vars_: dict[str, Any], *, title: str, question: str, test: str, why: str,
            score: float, limitations: list[str] | None = None, options: dict[str, Any] | None = None,
            alternative: str | None = None, kind: str = "analysis") -> None:
        recs.append({"key": _rec_key(analysis_type, vars_), "kind": kind, "analysis_type": analysis_type,
                     "config": {"variables": vars_, "options": options or {}}, "title": title, "question": question,
                     "test": test, "why": why, "limitations": limitations or [], "alternative": alternative,
                     "score": score})

    # 1. Descriptives
    desc_vars = [v.column_name for v in numeric] + [v.column_name for v in ordinal_single]
    if desc_vars:
        names = ", ".join(_label(by_name[c]) for c in desc_vars[:4]) + (" …" if len(desc_vars) > 4 else "")
        add("descriptives", {"variables": desc_vars[:30]}, title="Summarise the numeric variables",
            question=f"What are the typical values and spread of {names}?", test="Descriptive statistics",
            why="Mean, median, standard deviation and range describe each variable before any comparison.", score=100)
    cat_vars = [v.column_name for v, _, _ in groupers]
    if cat_vars:
        names = ", ".join(_label(by_name[c]) for c in cat_vars[:4]) + (" …" if len(cat_vars) > 4 else "")
        add("frequencies", {"variables": cat_vars[:20]}, title="Profile the respondents",
            question=f"How are cases distributed across {names}?", test="Frequency tables",
            why="Counts and percentages for each category, typically the first table of a research report.", score=98)

    # 2. Scale items: reliability + composite scores
    for name, items in scale_groups.items():
        cols = [v.column_name for v in items]
        add("reliability", {"items": cols}, title=f"Check the consistency of the {name} items",
            question=f"Do the {len(cols)} {name} items ({cols[0]}–{cols[-1]}) measure consistently?",
            test="Cronbach's alpha", why="Items sharing a name prefix look like one questionnaire scale. Reliability "
                                         "should be checked before averaging them into a score.",
            limitations=["Only meaningful if the items are intended to measure one construct; confirm from your "
                         "questionnaire.", "Reverse-worded items must be marked as reversed."], score=90)
        add("compute_scale", {"items": cols}, kind="transform", title=f"Create a {name} scale score",
            question=f"Average {cols[0]}–{cols[-1]} into one {name} score for further analysis.",
            test="Mean of items (new variable)", why="Comparisons and correlations are usually run on scale scores "
                                                     "rather than on every item separately.",
            options={"name": f"{name}_mean", "method": "mean"}, score=89)

    # 3. Outcomes ranked by name relevance
    # Ordinal columns with few categories that act as grouping factors (e.g. education level) are not outcomes.
    grouper_names = {v.column_name: k for v, k, _ in groupers}
    outcomes = numeric + [o for o in ordinal_single if grouper_names.get(o.column_name, 99) >= 5]
    def oscore(v) -> float:
        s = 2.0 if OUTCOME_WORDS.search(v.column_name + " " + (v.variable_label or "")) else 0.0
        if v.measurement_level == "numeric":
            s += 1
        if GROUP_WORDS.search(v.column_name) and not OUTCOME_WORDS.search(v.column_name):
            s -= 1
        return s
    outcomes.sort(key=oscore, reverse=True)

    def gscore(item) -> float:
        v, k, smallest = item
        s = 2.0 if GROUP_WORDS.search(v.column_name + " " + (v.variable_label or "")) else 0.0
        s += 1 if smallest >= 10 else 0
        s -= 2 if smallest < 3 else 0
        return s
    groupers.sort(key=gscore, reverse=True)

    comparisons = 0
    per_outcome: dict[str, int] = {}
    for gv, k, smallest in groupers[:5]:
        for ov in outcomes[:6]:
            if comparisons >= MAX_COMPARISONS or per_outcome.get(ov.column_name, 0) >= 3:
                continue
            if smallest < 2:
                continue
            o_name, g_name = _label(ov), _label(gv)
            sk = skew.get(ov.column_name)
            rank_based = ov.measurement_level == "ordinal" or (sk is not None and abs(sk) > 2)
            reason_np = ("the outcome is an ordinal rating" if ov.measurement_level == "ordinal"
                         else f"the outcome is strongly skewed (skewness {sk:.1f})" if rank_based else "")
            score = 70 + oscore(ov) * 4 + gscore((gv, k, smallest)) * 3
            vars_ = {"dependent": ov.column_name, "group" if k == 2 else "factor": gv.column_name}
            if k == 2:
                if rank_based:
                    add("mann_whitney", vars_, title=f"Compare {o_name} by {g_name}",
                        question=f"Do the two {g_name} groups differ in {o_name}?", test="Mann–Whitney U test",
                        why=f"Two independent groups; a rank-based test is suggested because {reason_np}.",
                        alternative="independent_t", score=score)
                else:
                    add("independent_t", vars_, title=f"Compare {o_name} by {g_name}",
                        question=f"Is the average {o_name} different between the two {g_name} groups?",
                        test="Independent-samples t-test (Welch)",
                        why="A numeric outcome and a grouping variable with two independent groups.",
                        limitations=["Assumes each case belongs to one group only."], alternative="mann_whitney",
                        score=score)
            else:
                if rank_based:
                    add("kruskal_wallis", vars_, title=f"Compare {o_name} across {g_name} groups",
                        question=f"Does {o_name} differ across the {k} {g_name} groups?", test="Kruskal–Wallis test",
                        why=f"{k} independent groups; a rank-based test is suggested because {reason_np}.",
                        alternative="one_way_anova", score=score)
                else:
                    add("one_way_anova", vars_, title=f"Compare {o_name} across {g_name} groups",
                        question=f"Does the average {o_name} differ across the {k} {g_name} groups?",
                        test="One-way ANOVA with post hoc tests",
                        why=f"A numeric outcome and {k} independent groups. Post hoc tests show which groups differ.",
                        limitations=["If group variances differ, Welch's ANOVA is the safer choice; the result will "
                                     "flag this."] + ([f"The smallest group has only {smallest} cases."]
                                                      if smallest < 10 else []),
                        alternative="kruskal_wallis", score=score)
            comparisons += 1
            per_outcome[ov.column_name] = per_outcome.get(ov.column_name, 0) + 1

    # 3b. Bundled group comparisons: one table across all measures (e.g. Formulation 1 vs Formulation 2).
    for gv, k, smallest in groupers[:2]:
        measures = [o.column_name for o in outcomes if o.column_name != gv.column_name][:10]
        if not measures or smallest < 2:
            continue
        labels = {str(kk): vv for kk, vv in (gv.category_labels_json or {}).items()}
        cats = [labels.get(_key(c["value"]), _key(c["value"])) for c in prof.get(gv.column_name, {}).get("categories", [])]
        mnames = ", ".join(_label(by_name[m]) for m in measures[:3]) + (" …" if len(measures) > 3 else "")
        if k == 2 and len(cats) == 2:
            a, b = sorted(cats, key=lambda c: (gv.category_order_json or []).index(c) if c in (gv.category_order_json or []) else 99)
            add("compare_two_groups", {"group": gv.column_name, "measures": measures},
                options={"group_a": a, "group_b": b}, title=f"Compare {a} and {b}",
                question=f"Do {a} and {b} differ in {mnames}?", test="Two-group comparison (test chosen per measure)",
                why=f"'{_label(gv)}' splits the data into two groups; every score is compared in one table.",
                limitations=["Assumes different participants in each group. If the same people rated both, use a "
                             "paired comparison."], score=97 + gscore((gv, k, smallest)))
        elif k >= 3:
            add("compare_groups", {"group": gv.column_name, "measures": measures},
                title=f"Compare the {k} {_label(gv)} groups", question=f"Do the {_label(gv)} groups differ in {mnames}?",
                test="Multi-group comparison with post hoc tests",
                why=f"'{_label(gv)}' has {k} groups; one overall test per measure, then corrected pairwise comparisons.",
                score=93 + gscore((gv, k, smallest)))

    # 4. Relationships between numeric outcomes
    corr_vars = [v for v in outcomes if v.column_name not in grouped_items][:12]
    if len(corr_vars) >= 2:
        any_ord = any(v.measurement_level == "ordinal" for v in corr_vars)
        skewed = [v for v in corr_vars if skew.get(v.column_name) is not None and abs(skew[v.column_name]) > 2]
        method = "spearman" if (any_ord or skewed) else "pearson"
        names = ", ".join(_label(v) for v in corr_vars[:4]) + (" …" if len(corr_vars) > 4 else "")
        add("correlation", {"variables": [v.column_name for v in corr_vars]}, options={"methods": [method]},
            title="Check how the numeric variables relate to each other",
            question=f"Which of {names} tend to rise or fall together?",
            test="Spearman correlation matrix" if method == "spearman" else "Pearson correlation matrix",
            why=("Spearman's ρ is suggested because some variables are ordinal or skewed." if method == "spearman"
                 else "Pearson's r measures the strength of linear relationships between numeric variables."),
            limitations=["Correlation shows association, not cause and effect."],
            alternative="spearman" if method == "pearson" else "pearson", score=80)
        key_vars = [v for v in corr_vars if OUTCOME_WORDS.search(v.column_name)][:4]
        for a, b in list(combinations(key_vars, 2))[:3]:
            add("correlation", {"variables": [a.column_name, b.column_name]}, options={"methods": [method]},
                title=f"Examine the relationship between {_label(a)} and {_label(b)}",
                question=f"Are higher {_label(a)} values associated with higher (or lower) {_label(b)}?",
                test=("Spearman" if method == "spearman" else "Pearson") + " correlation",
                why="Both are numeric measures that are commonly related in research models.",
                limitations=["Association only; not evidence that one causes the other."], score=74)

    # 5. Regression on the most outcome-like variable
    if len(corr_vars) >= 3 and oscore(corr_vars[0]) >= 2:
        dv = corr_vars[0]
        preds = [v.column_name for v in corr_vars[1:8]]
        add("linear_regression", {"dependent": dv.column_name, "predictors": preds},
            title=f"Predict {_label(dv)} from the other measures",
            question=f"Which variables best predict {_label(dv)} when considered together?",
            test="Multiple linear regression",
            why=f"'{_label(dv)}' looks like an outcome measure. Confirm that this matches your research model; the "
                "choice of outcome and predictors must come from your hypotheses.",
            limitations=["Choose predictors from theory, not by trial and error.", "Shows association, not causation."],
            score=60)

    # 6. Binary outcome → logistic regression
    for v, k, _ in groupers:
        if k == 2 and BINARY_OUTCOME_WORDS.search(v.column_name) and corr_vars:
            preds = [x.column_name for x in corr_vars[:6] if x.column_name != v.column_name]
            if preds:
                add("logistic_regression", {"dependent": v.column_name, "predictors": preds},
                    title=f"Predict {_label(v)}", question=f"Which variables are associated with {_label(v)}?",
                    test="Binary logistic regression", why=f"'{_label(v)}' has two outcomes (e.g. yes/no).",
                    limitations=["Needs at least about 10 cases in the smaller outcome group per predictor."], score=58)
            break

    # 7. Two categorical variables
    for (a, ka, _sa), (b, kb, _sb) in list(combinations(groupers[:4], 2))[:3]:
        cells = ka * kb
        small = rows and rows / cells < 5
        test = "Fisher's exact test" if (ka == 2 and kb == 2 and small) else "Chi-square test of independence"
        add("fisher_exact" if test.startswith("Fisher") else "chi_square", {"rows": a.column_name, "columns": b.column_name},
            title=f"Check whether {_label(a)} and {_label(b)} are related",
            question=f"Does the distribution of {_label(b)} differ across {_label(a)} groups?", test=test,
            why="Both variables are categorical, so the relationship is tested with a contingency table.",
            limitations=["Expected counts should be at least 5 in most cells; the result will check this."], score=55)

    # 8. Paired / repeated measurements by name pattern
    names = [v.column_name for v in numeric + ordinal_single]
    used: set[str] = set()
    for pre_re, post_re in PAIR_PATTERNS:
        pre = {m.group("stem").lower(): n for n in names if (m := pre_re.match(n))}
        post = {m.group("stem").lower(): n for n in names if (m := post_re.match(n))}
        for stem in pre.keys() & post.keys():
            a, b = pre[stem], post[stem]
            if a in used or b in used:
                continue
            used |= {a, b}
            sk = skew.get(a)
            t = "wilcoxon" if by_name[a].measurement_level == "ordinal" or (sk and abs(sk) > 2) else "paired_t"
            add(t, {"first": a, "second": b}, title=f"Compare {a} with {b}",
                question=f"Did scores change from {a} to {b}?",
                test="Wilcoxon signed-rank test" if t == "wilcoxon" else "Paired-samples t-test",
                why="The column names suggest two measurements of the same participants.",
                limitations=["Valid only if each row holds both measurements of the same person; confirm this."],
                score=88)
    series: dict[str, list[tuple[int, str]]] = {}
    for n in names:
        if (m := TIME_SERIES.match(n)) and n not in used:
            series.setdefault(m.group("stem").lower(), []).append((int(m.group("num")), n))
    for items in series.values():
        if len(items) >= 3:
            cols = [n for _, n in sorted(items)]
            add("rm_anova", {"within": cols}, title=f"Compare the repeated measurements {cols[0]}–{cols[-1]}",
                question="Do scores change across the measurement occasions?", test="Repeated-measures ANOVA",
                why="The column names suggest the same variable measured repeatedly.",
                limitations=["Valid only if each row is the same participant at every occasion."], score=86)

    recs.sort(key=lambda r: -r["score"])
    seen, out = set(), []
    for r in recs:
        if r["key"] not in seen:
            seen.add(r["key"])
            out.append(r)
    excluded = [{"name": v.column_name, "reason": _exclusion_reason(v, prof, rows)} for v in variables if not usable(v)]
    return {"recommendations": out, "excluded": excluded,
            "summary": {"numeric": len(numeric), "ordinal": len(ordinal_single), "grouping": len(groupers),
                        "scales": len(scale_groups), "rows": rows}}


def _exclusion_reason(v, prof, rows) -> str:
    p = prof.get(v.column_name, {})
    if v.measurement_level == "identifier":
        return "Identifier — not analysed."
    if v.measurement_level == "text":
        return "Free text — not analysed."
    if v.measurement_level in {"date", "datetime"}:
        return "Date — not used in automatic recommendations."
    if p.get("unique", 2) <= 1:
        return "Constant — every value is the same."
    return "More than half of the values are missing."


def _skewness(version: DatasetVersion, cols: list[str]) -> dict[str, float | None]:
    if not cols:
        return {}
    try:
        row = (pl.scan_parquet(parquet_path(version)).select([pl.col(c).cast(pl.Float64).skew().alias(c) for c in cols])
               .collect(engine="streaming").row(0, named=True))
        return {k: (float(v) if v is not None else None) for k, v in row.items()}
    except Exception:  # noqa: BLE001
        return {}
