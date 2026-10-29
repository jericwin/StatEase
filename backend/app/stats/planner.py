"""Turns simple user intents into concrete analyses.

1. ``plan_compare``: the Compare screen (two groups, several groups, or two measurements).
2. ``parse_objectives``: research objectives typed by the user -> one analysis per objective.

Both are deterministic rules over the dataset's variables and observed categories. Nothing is invented:
when an objective cannot be matched to columns, it is returned with a short clarification question.
"""

from __future__ import annotations

import re
from typing import Any

import polars as pl

from ..data.store import parquet_path
from ..errors import AppError
from ..models import DatasetVersion

GROUP_LEVELS = {"nominal", "binary", "ordinal"}
MEASURE_LEVELS = {"numeric", "ordinal"}


class VarInfo:
    def __init__(self, version: DatasetVersion):
        prof = {c["name"]: c for c in (version.profile_json or {}).get("variables", [])}
        self.vars = {v.column_name: v for v in version.variables}
        self.label = {n: (v.variable_label or n) for n, v in self.vars.items()}
        self.level = {n: v.measurement_level for n, v in self.vars.items()}
        self.categories: dict[str, list[str]] = {}
        for n, v in self.vars.items():
            cats = prof.get(n, {}).get("categories") or []
            if v.measurement_level in GROUP_LEVELS and cats:
                labels = {str(k): lbl for k, lbl in (v.category_labels_json or {}).items()}
                self.categories[n] = [labels.get(_key(c["value"]), _key(c["value"])) for c in cats]
        self.version = version

    def groupers(self) -> list[str]:
        return [n for n, cats in self.categories.items() if 2 <= len(cats) <= 12]

    def measures(self) -> list[str]:
        grp = set(self.groupers())
        out = [n for n, lv in self.level.items() if lv == "numeric"]
        # Ordinal ratings with several points count as measures unless they look like a grouping factor.
        out += [n for n, lv in self.level.items() if lv == "ordinal" and (n not in grp or len(self.categories.get(n, [])) >= 5)]
        return [n for n in self.vars if n in out]


def _key(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _skewed(version: DatasetVersion, cols: list[str]) -> bool:
    try:
        row = pl.scan_parquet(parquet_path(version)).select([pl.col(c).cast(pl.Float64).skew().alias(c) for c in cols]) \
            .collect().row(0)
        return any(v is not None and abs(v) > 1.5 for v in row)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- Compare screen


def plan_compare(version: DatasetVersion, req: dict[str, Any]) -> dict[str, Any]:
    info = VarInfo(version)
    mode = req.get("mode")
    if mode == "groups":
        group = req.get("group")
        measures = [m for m in req.get("measures") or [] if m]
        if group not in info.vars:
            raise AppError("invalid_plan", "Choose the column that identifies the groups.", 422)
        if info.level[group] not in GROUP_LEVELS:
            raise AppError("invalid_plan", f"'{info.label[group]}' is {info.level[group]}, not a grouping column. If its "
                                           "values are group codes, change its type to nominal in the Data tab.", 422)
        if not measures:
            raise AppError("invalid_plan", "Choose at least one measure to compare.", 422)
        bad = [m for m in measures if info.level.get(m) not in MEASURE_LEVELS]
        if bad:
            raise AppError("invalid_plan", f"{', '.join(info.label.get(b, b) for b in bad)} cannot be compared as "
                                           "scores (not numeric or rating).", 422)
        observed = info.categories.get(group, [])
        levels = [lv for lv in (req.get("levels") or observed) if lv in observed] or observed
        if len(levels) < 2:
            raise AppError("invalid_plan", "Select at least two groups to compare.", 422)
        names = ", ".join(info.label[m] for m in measures[:3]) + (f" and {len(measures) - 3} more" if len(measures) > 3 else "")
        if len(levels) == 2:
            return {"analysis_type": "compare_two_groups",
                    "variables": {"group": group, "measures": measures},
                    "options": {"group_a": levels[0], "group_b": levels[1], "test": req.get("test") or "auto"},
                    "title": f"Compare {levels[0]} and {levels[1]}",
                    "explanation": f"Two independent groups compared on {names}. The test is chosen per measure: "
                                   "Welch's t-test for numeric scores, Mann–Whitney U for ratings or non-normal small "
                                   "samples."}
        return {"analysis_type": "compare_groups", "variables": {"group": group, "measures": measures},
                "options": {"groups": levels if len(levels) < len(observed) else [], "test": req.get("test") or "auto"},
                "title": f"Compare {len(levels)} {info.label[group]} groups",
                "explanation": f"{len(levels)} independent groups: one overall test per measure (ANOVA, Welch's ANOVA or "
                               "Kruskal–Wallis), followed by corrected post hoc comparisons — not uncorrected pairwise "
                               "tests."}
    if mode == "variables":
        v1, v2 = req.get("var1"), req.get("var2")
        for v in (v1, v2):
            if v not in info.vars or info.level[v] not in MEASURE_LEVELS:
                raise AppError("invalid_plan", "Choose two numeric or rating columns.", 422)
        if v1 == v2:
            raise AppError("invalid_plan", "Choose two different columns.", 422)
        relation = req.get("relation")
        if relation not in ("paired", "relationship"):
            return {"question": {"text": f"Were {info.label[v1]} and {info.label[v2]} measured on the same participants "
                                         "(for example before and after)?",
                                 "options": [{"value": "paired", "label": "Yes — compare the two measurements (paired)"},
                                             {"value": "relationship", "label": "No — check whether they are related"}]}}
        ordinal = info.level[v1] == "ordinal" or info.level[v2] == "ordinal"
        if relation == "paired":
            rank = ordinal or _skewed(version, [v1, v2])
            atype = req.get("test") if req.get("test") in ("paired_t", "wilcoxon") else ("wilcoxon" if rank else "paired_t")
            return {"analysis_type": atype, "variables": {"first": v1, "second": v2}, "options": {},
                    "title": f"Compare {info.label[v1]} and {info.label[v2]}",
                    "explanation": "The same participants were measured twice, so a paired test is used "
                                   + ("(Wilcoxon signed-rank, because the scores are ratings or skewed)." if atype == "wilcoxon"
                                      else "(paired-samples t-test). Treating them as independent groups would be wrong.")}
        method = "spearman" if ordinal or _skewed(version, [v1, v2]) else "pearson"
        if req.get("test") in ("pearson", "spearman", "kendall"):
            method = req["test"]
        return {"analysis_type": "correlation", "variables": {"variables": [v1, v2]}, "options": {"methods": [method]},
                "title": f"Relationship between {info.label[v1]} and {info.label[v2]}",
                "explanation": f"{'Spearman' if method == 'spearman' else method.title()} correlation measures how "
                               "strongly the two columns move together. It shows association, not cause and effect."}
    raise AppError("invalid_plan", "Unknown comparison type.", 422)


# --------------------------------------------------------------------------- objectives

# Order matters: relationship wording ("relationship between X and Y") must win over comparison wording.
INTENTS = [
    ("relationship", re.compile(r"relationship|correlat|associat|related to|relation between|link between", re.I)),
    ("predict", re.compile(r"predict|influence|effect of|impact of|determinants?|factors? (affecting|influencing)|"
                           r"affect", re.I)),
    ("reliability", re.compile(r"reliab|internal consistency|cronbach", re.I)),
    ("profile", re.compile(r"profile|demographic|characteristics of (the )?respondents|distribution of respondents",
                           re.I)),
    ("rank", re.compile(r"\bmost\b|\bbest\b|\bhighest\b|\bpreferred\b|\bmore acceptable\b|which (of the )?"
                        r"(formulation|product|sample|treatment|group|variant|recipe)", re.I)),
    ("compare", re.compile(r"significant(ly)? differen|differen(ce|t)|compar|versus|\bvs\.?\b|between .+ and ", re.I)),
]
MAIN_ITEM = re.compile(r"^\s*(?:\(?(\d+)[.)]|objective\s*(\d+)\s*[:.-]|[-•*])\s*(?!\d)", re.I)
SUB_ITEM = re.compile(r"^\s*(?:\d+\.\d+\.?|\(?[a-z][.)]|[ivx]+[.)])\s*", re.I)
TREATMENT_NAME = re.compile(r"formulation|formula|treatment|product|sample|variant|recipe|batch|brand|condition|group",
                            re.I)
OVERALL_NAME = re.compile(r"overall|general|total|acceptab", re.I)


def split_objectives(text: str) -> list[dict[str, Any]]:
    """Numbered objectives; decimal or lettered sub-items (1.1 Age, 1.2 Gender) belong to their parent."""
    items: list[dict[str, Any]] = []
    for raw in re.split(r"[\r\n]+", text or ""):
        line = raw.strip()
        if len(line) < 2:
            continue
        numbered_main = bool(MAIN_ITEM.match(line)) and not SUB_ITEM.match(line)
        # Sub-items: "1.1 Age", "a) Gender", or plain lines listed under an objective ending in ":".
        is_sub = items and (bool(SUB_ITEM.match(line)) or (not numbered_main and items[-1]["text"].rstrip().endswith(":")))
        if is_sub:
            sub = SUB_ITEM.sub("", line).strip(" .;:")
            if sub:
                items[-1]["subitems"].append(sub)
            continue
        items.append({"text": MAIN_ITEM.sub("", line).strip(), "subitems": []})
    if len(items) == 1 and ";" in items[0]["text"] and not items[0]["subitems"]:
        items = [{"text": p.strip(), "subitems": []} for p in items[0]["text"].split(";") if p.strip()]
    out = []
    for it in items:
        text = it["text"].rstrip(" :")
        full = f"{text}: {', '.join(it['subitems'])}" if it["subitems"] else text
        if len(full) > 3:
            out.append({"text": text, "subitems": it["subitems"], "full": full})
    return out[:20]


UNIT_SUFFIX = re.compile(r"\s*[(\[][^)\]]*[)\]]\s*$")


def _norm(s: str) -> str:
    # Punctuation becomes spaces so "in terms of: age, gender" matches the column "Age".
    return re.sub(r"[^0-9a-z]+", " ", s.lower()).strip()


def _mentions(text: str, info: VarInfo) -> tuple[list[str], dict[str, list[str]]]:
    t = " " + _norm(text) + " "
    cols: list[tuple[int, str]] = []
    for n in info.vars:
        # "Plant Height (cm)" is also found as "plant height": objectives rarely repeat the unit.
        bare = {_norm(UNIT_SUFFIX.sub("", x)) for x in (n, info.label[n])}
        for name in {_norm(n), _norm(info.label[n]), *bare}:
            if len(name) >= 2 and (pos := t.find(f" {name} ")) >= 0:
                cols.append((pos, n))
                break
            if len(name) >= 4 and (pos := t.find(name)) >= 0:
                cols.append((pos, n))
                break
    levels: dict[str, list[str]] = {}
    for n, cats in info.categories.items():
        if len(cats) > 20:
            continue
        cname = _norm(info.label[n])
        for c in cats:
            cn = _norm(c)
            hit = (len(cn) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(cn)}(?![a-z0-9])", t)) or \
                  re.search(rf"{re.escape(cname)}\s*{re.escape(cn)}(?![a-z0-9])", t)
            if hit:
                levels.setdefault(n, []).append(c)
    ordered = [n for _, n in sorted(cols)]
    return list(dict.fromkeys(ordered)), levels


def _intent(text: str) -> str:
    for name, rx in INTENTS:
        if rx.search(text):
            return name
    return "describe"


def _analysis(atype: str, variables: dict[str, Any], title: str, options: dict[str, Any] | None = None,
              filter_: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"analysis_type": atype, "variables": variables, "options": options or {}, "filter": filter_, "title": title}


def parse_objectives(version: DatasetVersion, text_or_list: str | list[str]) -> list[dict[str, Any]]:
    info = VarInfo(version)
    if isinstance(text_or_list, str):
        items = split_objectives(text_or_list)
    else:
        items = [x for t in text_or_list if t.strip() for x in split_objectives(t)]
    all_measures = info.measures()
    groupers = info.groupers()
    treatments = [g for g in groupers if TREATMENT_NAME.search(g + " " + info.label[g])]
    out = []
    for i, item in enumerate(items, start=1):
        text = item["full"]
        cols, levels = _mentions(text, info)
        intent = _intent(item["text"])
        measures = [c for c in cols if c in all_measures and c not in levels]
        mentioned_groups = [c for c in cols if c in groupers] + [c for c in levels if c not in cols]
        group = (mentioned_groups or [None])[0]
        if group is None and levels:
            group = next(iter(levels))
        obj: dict[str, Any] = {"id": f"o{i}", "text": item["text"], "subitems": item["subitems"], "full_text": text,
                               "intent": intent, "status": "ready", "question": None, "assumed": [], "analyses": []}

        def default_measures(measures=measures, obj=obj, group_=None):
            if measures:
                return measures
            obj["assumed"].append("All score columns were used because the objective does not name specific ones.")
            return [m for m in all_measures if m != group_][:12]

        def need(question: str, atype: str, variables: dict[str, Any], obj=obj) -> None:
            obj["status"], obj["question"] = "needs_input", question
            obj["analyses"].append({**_analysis(atype, variables, obj["text"][:80]), "status": "needs_input"})

        if intent == "profile":
            named = [c for c in cols if info.level.get(c) not in ("identifier", "text", "date", "datetime")]
            if not named:
                named = groupers[:8]
                if named:
                    obj["assumed"].append("No columns were named, so all category columns are profiled.")
            cats = [c for c in named if c in info.categories and c not in all_measures]
            nums = [c for c in named if c not in cats and info.level.get(c) in ("numeric", "ordinal")]
            if cats:
                obj["analyses"].append(_analysis("frequencies", {"variables": cats}, "Profile of the respondents"))
            if nums:
                obj["analyses"].append(_analysis("descriptives", {"variables": nums},
                                                 "Profile of the respondents: " + ", ".join(info.label[n] for n in nums),
                                                 {"statistics": ["n", "mean", "sd", "min", "max"]}))
            if not obj["analyses"]:
                need("Which columns describe the respondents?", "frequencies", {"variables": []})
        elif intent == "reliability":
            named = [c for c in cols if info.vars[c].scale_group] or [v.column_name for v in info.vars.values() if v.scale_group]
            if len(named) < 2:
                need("Which questionnaire items form the scale?", "reliability", {"items": []})
            else:
                obj["analyses"].append(_analysis("reliability", {"items": named}, "Reliability of the scale"))
        elif intent in ("compare", "rank"):
            if group is None and len(treatments) == 1:
                group = treatments[0]
                obj["assumed"].append(f"Groups taken from '{info.label[group]}'.")
            elif group is None and len(groupers) == 1:
                group = groupers[0]
                obj["assumed"].append(f"Groups taken from '{info.label[group]}', the only grouping column.")
            if group is None and intent == "compare" and len(measures) == 2:
                need(f"Were {info.label[measures[0]]} and {info.label[measures[1]]} measured on the same participants? If "
                     "so this paired comparison is correct; otherwise choose a grouping column.", "paired_t",
                     {"first": measures[0], "second": measures[1]})
            elif group is None:
                need("Which column identifies the groups?", "compare_two_groups" if intent == "compare" else "rank_groups",
                     {"group": "", "measures": default_measures()})
            else:
                ms = default_measures(group_=group)
                cats = info.categories.get(group, [])
                lv = levels.get(group, [])
                chosen = lv if len(lv) >= 2 else cats
                if intent == "rank":
                    overall = next((m for m in ms if OVERALL_NAME.search(m + " " + info.label[m])), None)
                    obj["analyses"].append(_analysis("rank_groups", {"group": group, "measures": ms},
                                                     f"Most acceptable {info.label[group].lower()}",
                                                     {"decide_by": overall or "average"}))
                elif len(chosen) == 2:
                    obj["analyses"].append(_analysis("compare_two_groups", {"group": group, "measures": ms},
                                                     f"Comparison of {chosen[0]} and {chosen[1]}",
                                                     {"group_a": chosen[0], "group_b": chosen[1]}))
                else:
                    obj["analyses"].append(_analysis("compare_groups", {"group": group, "measures": ms},
                                                     f"Comparison across {info.label[group]} groups",
                                                     {"groups": chosen if len(chosen) < len(cats) else []}))
        elif intent == "relationship":
            nums = [c for c in cols if c in all_measures]
            catc = [c for c in cols if c in info.categories and c not in all_measures]
            if len(nums) >= 2:
                obj["analyses"].append(_analysis("correlation", {"variables": nums},
                                                 "Relationship between " + " and ".join(info.label[n] for n in nums[:3])))
            elif len(catc) >= 2:
                obj["analyses"].append(_analysis("chi_square", {"rows": catc[0], "columns": catc[1]},
                                                 f"Association between {info.label[catc[0]]} and {info.label[catc[1]]}"))
            else:
                need("Which two (or more) measures should be related?", "correlation", {"variables": nums})
        elif intent == "predict":
            on = re.search(r"\bon\s+(the\s+)?(.+)$", text, re.I)
            outcome = None
            if on:
                tail_cols, _ = _mentions(on.group(2), info)
                outcome = next((c for c in tail_cols if c in all_measures), None)
            preds = [c for c in cols if c != outcome and (c in all_measures or c in info.categories)]
            if outcome and preds:
                obj["analyses"].append(_analysis("linear_regression", {"dependent": outcome, "predictors": preds},
                                                 f"Predictors of {info.label[outcome]}"))
            else:
                need("Which column is the outcome, and which columns are the predictors?", "linear_regression",
                     {"dependent": outcome or "", "predictors": preds})
        else:  # describe: "level of acceptability ... in terms of ..."
            ms = default_measures(group_=group)
            lv = levels.get(group, []) if group else []
            if not ms:
                need("Which columns should be summarised?", "descriptives", {"variables": []})
            elif len(lv) == 1:
                obj["analyses"].append(_analysis("descriptives", {"variables": ms}, f"Results for {lv[0]}",
                                                 filter_={"column": group, "values": lv}))
            elif len(lv) > 1:
                obj["analyses"].append(_analysis("descriptives", {"variables": ms, "split_by": group},
                                                 f"Results by {info.label[group]}", filter_={"column": group, "values": lv}))
            elif len(treatments) == 1:
                # Studies that develop products report each formulation's acceptability separately.
                t = treatments[0]
                obj["assumed"].append(f"Reported separately for each {info.label[t]}.")
                obj["analyses"].append(_analysis("descriptives", {"variables": ms, "split_by": t},
                                                 f"Results by {info.label[t]}"))
            else:
                obj["analyses"].append(_analysis("descriptives", {"variables": ms}, "Descriptive statistics"))
        for a in obj["analyses"]:
            a.setdefault("status", "ready")
            a["variables_labels"] = {k: ([info.label.get(x, x) for x in v] if isinstance(v, list) else info.label.get(v, v))
                                     for k, v in a["variables"].items()}
        # Back-compatible single-analysis fields (first analysis).
        first = obj["analyses"][0] if obj["analyses"] else {}
        for k in ("analysis_type", "variables", "options", "filter", "title", "variables_labels"):
            obj[k] = first.get(k)
        obj["title"] = obj["title"] or item["text"][:80]
        out.append(obj)
    return out
