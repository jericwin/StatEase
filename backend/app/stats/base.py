"""Analysis registry, run context and the uniform result structure.

Every procedure returns the same shape so that the UI, interpretation and DOCX/XLSX exporters
can render any analysis without special cases:

    {analysis_type, title, plain_title, variables, n, tables[], charts[], assumptions[],
     warnings[], interpretation{plain, technical}, summary{}, method{}, code}

Values are kept at full precision; rounding happens only for display and export.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..errors import AnalysisError

NUMERIC_LEVELS = {"numeric"}
SCALE_LEVELS = {"numeric", "ordinal"}  # ordinal allowed where the user may treat ratings as numeric
CATEGORICAL_LEVELS = {"nominal", "ordinal", "binary"}


@dataclass
class Role:
    key: str
    label: str
    description: str
    levels: set[str]
    min: int = 1
    max: int | None = 1
    plain: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["levels"] = sorted(self.levels)
        return d


@dataclass
class Option:
    key: str
    label: str
    type: str  # bool | number | select | multiselect | text | level | levels | proportions
    default: Any = None
    choices: list[dict[str, Any]] | None = None
    help: str = ""
    advanced: bool = False
    depends_on: str | None = None  # role key whose categories populate a level selector
    min: float | None = None
    max: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisSpec:
    id: str
    name: str
    plain_name: str
    category: str
    description: str
    roles: list[Role]
    options: list[Option]
    run: Callable[[Context, dict[str, Any]], Result]
    assumptions: list[str] = field(default_factory=list)
    method: str = ""
    missing_data: str = "Cases with a missing value on any variable in the analysis are excluded (listwise)."
    references: list[str] = field(default_factory=list)
    when_to_use: str = ""
    limitations: list[str] = field(default_factory=list)
    code: Callable[[dict[str, Any], dict[str, Any]], str] | None = None

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "plain_name": self.plain_name, "category": self.category,
            "description": self.description, "when_to_use": self.when_to_use,
            "roles": [r.to_dict() for r in self.roles], "options": [o.to_dict() for o in self.options],
            "assumptions": self.assumptions, "method": self.method, "missing_data": self.missing_data,
            "references": self.references, "limitations": self.limitations,
        }

    def defaults(self) -> dict[str, Any]:
        return {o.key: o.default for o in self.options}


REGISTRY: dict[str, AnalysisSpec] = {}

CATEGORIES = [
    {"id": "descriptives", "name": "Descriptive Statistics", "plain": "Summarise your variables"},
    {"id": "compare", "name": "Compare Groups", "plain": "Compare averages between groups or measurements"},
    {"id": "anova", "name": "ANOVA", "plain": "Compare averages across several groups or factors"},
    {"id": "correlation", "name": "Correlation", "plain": "Check whether variables are related"},
    {"id": "regression", "name": "Regression", "plain": "Predict an outcome from other variables"},
    {"id": "nonparametric", "name": "Nonparametric Tests", "plain": "Rank-based alternatives for skewed or ordinal data"},
    {"id": "categorical", "name": "Categorical Data", "plain": "Analyse counts and categories"},
    {"id": "reliability", "name": "Reliability", "plain": "Check the consistency of questionnaire scales"},
    {"id": "assumptions", "name": "Assumption Checks", "plain": "Check normality and equal variances"},
]


def register(spec: AnalysisSpec) -> AnalysisSpec:
    REGISTRY[spec.id] = spec
    return spec


# --------------------------------------------------------------------------- context


@dataclass
class VarMeta:
    name: str
    label: str
    level: str
    data_type: str
    category_labels: dict[str, str]
    category_order: list[Any]
    unit: str | None = None
    missing_codes: list[Any] = field(default_factory=list)

    @property
    def display(self) -> str:
        return self.label or self.name


class Context:
    """Gives procedures access to data (only the requested columns) and settings."""

    def __init__(self, loader: Callable[[list[str]], pd.DataFrame], variables: dict[str, VarMeta],
                 settings: dict[str, Any]):
        self._loader = loader
        self.variables = variables
        self.alpha: float = float(settings.get("alpha", 0.05))
        self.ci_level: float = float(settings.get("ci_level", 0.95))
        self.p_style: str = settings.get("p_style", "apa")
        self.decimals: int = int(settings.get("decimals", 2))
        self.shapiro_max_n: int = int(settings.get("shapiro_max_n", 5000))
        self.settings = settings
        self.scored_ordinals: set[str] = set()
        # Optional subset: {"column": name, "values": [category labels]} applied to every frame.
        self.filter: dict[str, Any] | None = None
        self.filter_note: str | None = None

    def meta(self, name: str) -> VarMeta:
        if name not in self.variables:
            raise AnalysisError(f"Variable '{name}' does not exist in this dataset.")
        return self.variables[name]

    def label(self, name: str) -> str:
        return self.meta(name).display

    def frame(self, columns: list[str]) -> pd.DataFrame:
        cols = list(dict.fromkeys(columns))
        f = self.filter
        if not (f and f.get("column") and f.get("values")):
            return self._loader(cols)
        fc = f["column"]
        if fc not in self.variables:
            raise AnalysisError(f"Filter variable '{fc}' does not exist in this dataset.")
        df = self._loader(list(dict.fromkeys([*cols, fc])))
        wanted = {str(v) for v in f["values"]}
        labels = self.categorical(df, fc).astype("object")
        keep = labels.map(lambda v: v is not None and not (isinstance(v, float) and v != v) and str(v) in wanted)
        out = df[keep.to_numpy(dtype=bool)]
        if out.empty:
            raise AnalysisError(f"No rows match {self.label(fc)} = {', '.join(sorted(wanted))}.")
        self.filter_note = (f"Analysis restricted to {self.label(fc)} = {', '.join(str(v) for v in f['values'])} "
                            f"({len(out):,} of {len(df):,} rows).")
        return out if fc in cols else out.drop(columns=[fc])

    # Typed accessors -----------------------------------------------------

    def numeric(self, df: pd.DataFrame, name: str) -> pd.Series:
        s = df[name]
        if pd.api.types.is_bool_dtype(s):
            return s.astype(float)
        meta = self.meta(name)
        if meta.level in {"ordinal", "binary"} and not pd.api.types.is_numeric_dtype(s):
            # Ordered text categories (e.g. "Disagree" < "Agree") are scored 1..k in their declared order.
            cat = self.categorical(df, name)
            codes = cat.cat.codes.astype(float) + 1
            codes[codes == 0] = np.nan
            self.scored_ordinals.add(name)
            return codes
        out = pd.to_numeric(s, errors="coerce")
        bad = int(out.isna().sum() - s.isna().sum())
        if bad:
            raise AnalysisError(f"'{self.label(name)}' contains {bad} non-numeric value(s) and cannot be analysed as "
                                "a number. Set its missing-value codes or change its measurement level.")
        return out.astype(float)

    def categorical(self, df: pd.DataFrame, name: str) -> pd.Series:
        """Return a pandas Categorical with category labels applied and the declared order."""
        meta = self.meta(name)
        s = df[name]
        labels = {str(k): v for k, v in (meta.category_labels or {}).items()}

        def key(v: Any) -> str:
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            return str(v)

        raw = s.map(lambda v: None if pd.isna(v) else key(v))
        observed = list(pd.unique(raw.dropna()))
        order = [key(v) for v in meta.category_order or []]
        ordered = [c for c in order if c in observed] + sorted([c for c in observed if c not in order],
                                                               key=_natural_key)
        cat = pd.Categorical(raw, categories=ordered, ordered=meta.level == "ordinal")
        if labels:
            cat = cat.rename_categories([labels.get(c, c) for c in ordered])
        return pd.Series(cat, index=s.index, name=name)


def _natural_key(v: str) -> tuple:
    try:
        return (0, float(v), "")
    except ValueError:
        return (1, 0.0, v.lower())


# --------------------------------------------------------------------------- results


def clean(v: Any) -> Any:
    """Convert numpy scalars/NaN to JSON-safe Python values."""
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return None if not math.isfinite(f) else f
    if isinstance(v, (list, tuple, np.ndarray)):
        return [clean(x) for x in v]
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def col(key: str, label: str, fmt: str = "num", group: str | None = None, help: str | None = None) -> dict[str, Any]:
    """Column definition. ``fmt``: int | num | stat | p | pct | ci | text | r. ``group`` drives report checklists."""
    d = {"key": key, "label": label, "fmt": fmt}
    if group:
        d["group"] = group
    if help:
        d["help"] = help
    return d


class Result:
    def __init__(self, spec: AnalysisSpec, config: dict[str, Any], ctx: Context):
        self.spec = spec
        self.config = config
        self.ctx = ctx
        self.tables: list[dict[str, Any]] = []
        self.charts: list[dict[str, Any]] = []
        self.assumptions: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []
        self.summary: dict[str, Any] = {}
        self.interpretation: dict[str, str] = {"plain": "", "technical": ""}
        self.n: int | None = None
        self.missing: dict[str, Any] = {}
        self.title = spec.name
        self.plain_title = spec.plain_name

    def table(self, id: str, kind: str, title: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]],
              notes: list[str] | None = None) -> dict[str, Any]:
        t = {"id": id, "kind": kind, "title": title, "columns": columns,
             "rows": [clean(r) for r in rows], "notes": notes or []}
        self.tables.append(t)
        return t

    def chart(self, id: str, type: str, title: str, data: dict[str, Any], x_label: str = "", y_label: str = "",
              caption: str = "", note: str | None = None) -> None:
        self.charts.append({"id": id, "type": type, "title": title, "data": clean(data), "x_label": x_label,
                            "y_label": y_label, "caption": caption, "note": note})

    def assumption(self, name: str, status: str, message: str, **values: Any) -> None:
        """status: ok | warning | violated | info"""
        self.assumptions.append({"name": name, "status": status, "message": message, **clean(values)})

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_type": self.spec.id,
            "title": self.title,
            "plain_title": self.plain_title,
            "category": self.spec.category,
            "variables": self.config.get("variables", {}),
            "options": self.config.get("options", {}),
            "n": self.n,
            "missing": clean(self.missing),
            "tables": self.tables,
            "charts": self.charts,
            "assumptions": self.assumptions,
            "warnings": self.warnings,
            "notes": self.notes,
            "summary": clean(self.summary),
            "interpretation": self.interpretation,
            "settings": {"alpha": self.ctx.alpha, "ci_level": self.ctx.ci_level},
            "method": {"description": self.spec.method, "assumptions": self.spec.assumptions,
                       "missing_data": self.spec.missing_data, "references": self.spec.references,
                       "limitations": self.spec.limitations},
        }


# --------------------------------------------------------------------------- formatting


def fmt_num(x: float | None, d: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{x:,.{d}f}".replace(",", "") if abs(x) < 10000 else f"{x:,.{d}f}"


def fmt_p(p: float | None, style: str = "apa", with_symbol: bool = True) -> str:
    """APA style: no leading zero, three decimals, 'p < .001' below the reporting threshold."""
    if p is None or not math.isfinite(p):
        return "p = —" if with_symbol else "—"
    if p < 0.001:
        s = "< .001" if style == "apa" else "< 0.001"
        return f"p {s}" if with_symbol else s
    s = f"{p:.3f}"
    if style == "apa":
        s = s.lstrip("0") if p < 1 else "1.000"
    return f"p = {s}" if with_symbol else s


def fmt_r(r: float | None, d: int = 2, style: str = "apa") -> str:
    """Statistics bounded by ±1 (r, rho, tau) omit the leading zero in APA style."""
    if r is None or not math.isfinite(r):
        return "—"
    s = f"{r:.{d}f}"
    if style == "apa":
        s = s.replace("0.", ".", 1)
    return s


def fmt_ci(lo: float | None, hi: float | None, d: int = 2) -> str:
    return f"[{fmt_num(lo, d)}, {fmt_num(hi, d)}]"


def sig_phrase(p: float | None, alpha: float) -> tuple[bool, str]:
    if p is None or not math.isfinite(p):
        return False, "could not be evaluated"
    return (True, "statistically significant") if p < alpha else (False, "not statistically significant")


def alpha_text(alpha: float) -> str:
    return f"α = {alpha:g}".replace("0.", ".")


# --------------------------------------------------------------------------- validation


def assigned(config: dict[str, Any], key: str) -> list[str]:
    v = (config.get("variables") or {}).get(key)
    if v is None:
        return []
    return [v] if isinstance(v, str) else [x for x in v if x]


def validate_roles(spec: AnalysisSpec, config: dict[str, Any], variables: dict[str, VarMeta]) -> list[str]:
    """Return human-readable problems with the variable assignment (empty list = valid)."""
    problems: list[str] = []
    used: dict[str, str] = {}
    for role in spec.roles:
        names = assigned(config, role.key)
        if len(names) < role.min:
            need = "at least one variable" if role.min == 1 else f"at least {role.min} variables"
            if role.min > 0:
                problems.append(f"{role.label}: choose {need}.")
            continue
        if role.max is not None and len(names) > role.max:
            problems.append(f"{role.label}: choose at most {role.max} variable{'s' if role.max != 1 else ''}.")
        for n in names:
            meta = variables.get(n)
            if meta is None:
                problems.append(f"{role.label}: '{n}' is not in the dataset.")
                continue
            if meta.level not in role.levels:
                allowed = ", ".join(sorted(role.levels))
                problems.append(f"{role.label}: '{meta.display}' is {meta.level}, but this role needs a "
                                f"{allowed} variable. Change its measurement level if it was classified incorrectly.")
            if n in used and used[n] != role.key:
                problems.append(f"'{meta.display}' is assigned to more than one role.")
            used[n] = role.key
    return problems


def listwise(df: pd.DataFrame, columns: list[str], res: Result) -> pd.DataFrame:
    total = len(df)
    out = df.dropna(subset=columns)
    excluded = total - len(out)
    res.missing = {"total_rows": total, "used": len(out), "excluded": excluded,
                   "method": "listwise", "variables": columns}
    if excluded:
        names = ", ".join(res.ctx.label(c) for c in columns)
        res.notes.append(f"{excluded:,} of {total:,} rows were excluded because of missing values on {names}.")
    return out


def require_n(n: int, minimum: int, what: str, suggestion: str | None = None) -> None:
    if n < minimum:
        raise AnalysisError(f"{what} has only {n} valid observation(s); at least {minimum} are needed.",
                            code="insufficient_data", suggestion=suggestion)
