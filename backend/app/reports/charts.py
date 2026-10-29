"""Renders the engine's chart specifications to PNG with matplotlib (for DOCX/XLSX exports).

The same specification drives the interactive ECharts view in the browser, so exported figures show
exactly the data the user saw.
"""

from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

NAVY = "#1f3a5f"
PALETTE = ["#1f3a5f", "#c0504d", "#4f8a5b", "#d08c2f", "#6b5b95", "#3f7fbf", "#8c564b", "#7f7f7f"]


def _style(ax, spec: dict[str, Any]) -> None:
    ax.set_xlabel(spec.get("x_label") or "", fontsize=9)
    ax.set_ylabel(spec.get("y_label") or "", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.6)
    ax.set_axisbelow(True)


def _arr(values) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in values], dtype=float)


def _styled(ax, spec: dict[str, Any]) -> None:
    """Category data (means, counts, profiles) drawn in the style the user picked: bar, hbar, stacked, line, dot, pie."""
    style, d = spec["style"], spec["data"]
    cats, series = d.get("categories", []), d.get("series", [])
    n = max(len(series), 1)
    x = np.arange(len(cats))
    if style == "pie":
        vals = _arr(series[0]["values"])
        keep = np.isfinite(vals) & (vals > 0)
        ax.pie(vals[keep], labels=[c for c, k in zip(cats, keep, strict=True) if k], colors=PALETTE, autopct="%1.0f%%",
               startangle=90, counterclock=False, textprops={"fontsize": 7}, wedgeprops={"edgecolor": "white", "linewidth": 0.8})
        ax.axis("equal")
        return
    if style == "stacked":
        bottom = np.zeros(len(cats))
        for i, s in enumerate(series):
            vals = np.nan_to_num(_arr(s["values"]))
            ax.bar(x, vals, bottom=bottom, label=s["name"], color=PALETTE[i % len(PALETTE)], width=0.6)
            bottom += vals
    else:
        w = 0.8 / n
        for i, s in enumerate(series):
            vals = _arr(s["values"])
            lo, hi = _arr(s.get("lower") or [None] * len(vals)), _arr(s.get("upper") or [None] * len(vals))
            pos = x + (i - (n - 1) / 2) * (w if style in ("bar", "hbar") else min(w, 0.12))
            color = PALETTE[i % len(PALETTE)]
            err = [vals - lo, hi - vals] if np.isfinite(lo).any() else None
            if style == "hbar":
                ax.barh(pos, vals, height=w, label=s["name"], color=color)
                if err:
                    ax.errorbar(vals, pos, xerr=err, fmt="none", ecolor="#333333", capsize=3, linewidth=0.9)
                continue
            if style == "bar":
                ax.bar(pos, vals, width=w, label=s["name"], color=color)
            elif style == "line":
                ax.plot(pos, vals, marker="o", markersize=4, label=s["name"], color=color, linewidth=1.4)
            else:  # dot
                ax.plot(pos, vals, "o", markersize=5.5, label=s["name"], color=color)
            if err:
                ax.errorbar(pos, vals, yerr=err, fmt="none", ecolor="#333333" if style == "bar" else color, capsize=3,
                            linewidth=0.9)
    long = max((len(str(c)) for c in cats), default=0) > 10
    if style == "hbar":
        ax.set_yticks(x, cats)
        ax.invert_yaxis()
    else:
        ax.set_xticks(x, cats, rotation=30 if long else 0, ha="right" if long else "center")
    if len(series) > 1:
        ax.legend(fontsize=7, frameon=False)


def render(spec: dict[str, Any], width: float = 6.0, height: float = 3.6) -> bytes:
    t, d = spec["type"], spec["data"]
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    try:
        if spec.get("style") and t in ("means", "bar", "interaction"):
            _styled(ax, spec)
            style = spec["style"]
            if style == "hbar":
                ax.set_xlabel(spec.get("y_label") or "", fontsize=9)
                ax.set_ylabel(spec.get("x_label") or "", fontsize=9)
                ax.spines[["top", "right"]].set_visible(False)
                ax.tick_params(labelsize=8)
                ax.grid(axis="x", color="#e5e7eb", linewidth=0.6)
                ax.set_axisbelow(True)
            elif style != "pie":
                _style(ax, spec)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            return buf.getvalue()
        if t == "histogram":
            bins = d.get("bins") or []
            if bins:
                ax.bar([(b[0] + b[1]) / 2 for b in bins], [b[2] for b in bins], width=[b[1] - b[0] for b in bins],
                       color=NAVY, alpha=0.85, edgecolor="white", linewidth=0.5)
            if d.get("normal"):
                xs, ys = zip(*d["normal"], strict=True)
                ax.plot(xs, ys, color="#c0504d", linewidth=1.2, label="Normal curve")
                ax.legend(fontsize=7, frameon=False)
        elif t == "box":
            groups = [g for g in d["groups"] if g.get("n")]
            stats_ = [{"med": g["median"], "q1": g["q1"], "q3": g["q3"], "whislo": g["min"], "whishi": g["max"],
                       "fliers": g.get("outliers", []), "label": f"{g['name']}\n(n={g['n']})"} for g in groups]
            ax.bxp(stats_, showfliers=True, patch_artist=True,
                   boxprops={"facecolor": "#dbe4f0", "edgecolor": NAVY}, medianprops={"color": NAVY, "linewidth": 1.5},
                   flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "#9ca3af", "markeredgecolor": "none"})
        elif t == "meanci":
            groups = [g for g in d["groups"] if g.get("mean") is not None]
            x = np.arange(len(groups))
            means = [g["mean"] for g in groups]
            lo = [g["mean"] - g["lower"] if g.get("lower") is not None else 0 for g in groups]
            hi = [g["upper"] - g["mean"] if g.get("upper") is not None else 0 for g in groups]
            ax.errorbar(x, means, yerr=[lo, hi], fmt="o", color=NAVY, capsize=4, markersize=5, linewidth=1.2)
            ax.set_xticks(x, [g["name"] for g in groups])
            ax.margins(x=0.2)
        elif t == "qq":
            pts = d.get("points") or []
            if pts:
                xs, ys = zip(*pts, strict=True)
                ax.scatter(xs, ys, s=8, color=NAVY, alpha=0.7)
                line = d.get("line")
                if line:
                    gx = np.array([min(xs), max(xs)])
                    ax.plot(gx, line["intercept"] + line["slope"] * gx, color="#c0504d", linewidth=1)
        elif t == "scatter":
            pts = d.get("points") or []
            if pts:
                xs, ys = zip(*pts, strict=True)
                ax.scatter(xs, ys, s=8, color=NAVY, alpha=0.55)
            fit = d.get("fit")
            if fit:
                gx = np.array([fit["x_min"], fit["x_max"]])
                ax.plot(gx, fit["intercept"] + fit["slope"] * gx, color="#c0504d", linewidth=1.2)
            if d.get("zero_line"):
                ax.axhline(0, color="#c0504d", linewidth=0.8, linestyle="--")
        elif t == "bar":
            cats = d["categories"]
            series = d["series"]
            x = np.arange(len(cats))
            if d.get("stacked"):
                bottom = np.zeros(len(cats))
                for i, s in enumerate(series):
                    vals = np.array([v or 0 for v in s["values"]])
                    ax.bar(x, vals, bottom=bottom, label=s["name"], color=PALETTE[i % len(PALETTE)], width=0.6)
                    bottom += vals
                ax.legend(fontsize=7, frameon=False, bbox_to_anchor=(1.01, 1), loc="upper left")
            else:
                w = 0.8 / len(series)
                for i, s in enumerate(series):
                    ax.bar(x + (i - (len(series) - 1) / 2) * w, s["values"], width=w, label=s["name"],
                           color=PALETTE[i % len(PALETTE)])
                if len(series) > 1:
                    ax.legend(fontsize=7, frameon=False)
            ax.set_xticks(x, cats, rotation=30 if max((len(str(c)) for c in cats), default=0) > 8 else 0,
                          ha="right" if max((len(str(c)) for c in cats), default=0) > 8 else "center")
        elif t == "means":
            cats = d.get("categories", [])
            series = d.get("series", [])
            x = np.arange(len(cats))
            w = 0.8 / max(len(series), 1)
            for i, s in enumerate(series):
                vals = np.array([np.nan if v is None else v for v in s["values"]], dtype=float)
                lo = np.array([np.nan if v is None else v for v in (s.get("lower") or [None] * len(vals))], dtype=float)
                hi = np.array([np.nan if v is None else v for v in (s.get("upper") or [None] * len(vals))], dtype=float)
                pos = x + (i - (len(series) - 1) / 2) * w
                ax.bar(pos, vals, width=w, label=s["name"], color=PALETTE[i % len(PALETTE)])
                if np.isfinite(lo).any():
                    ax.errorbar(pos, vals, yerr=[vals - lo, hi - vals], fmt="none", ecolor="#333333", capsize=3,
                                linewidth=0.9)
            ax.set_xticks(x, cats, rotation=30 if max((len(str(c)) for c in cats), default=0) > 10 else 0,
                          ha="right" if max((len(str(c)) for c in cats), default=0) > 10 else "center")
            if len(series) > 1:
                ax.legend(fontsize=7, frameon=False)
        elif t == "heatmap":
            labels = d["labels"]
            m = np.array([[np.nan if v is None else v for v in row] for row in d["matrix"]], dtype=float)
            im = ax.imshow(m, cmap="RdBu_r", vmin=-1, vmax=1)
            ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=7)
            ax.set_yticks(range(len(labels)), labels, fontsize=7)
            if len(labels) <= 12:
                for i in range(len(labels)):
                    for j in range(len(labels)):
                        if np.isfinite(m[i, j]):
                            ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center", fontsize=6,
                                    color="white" if abs(m[i, j]) > 0.6 else "black")
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            ax.grid(False)
        elif t == "interaction":
            cats = d["categories"]
            x = np.arange(len(cats))
            for i, s in enumerate(d["series"]):
                vals = [np.nan if v is None else v for v in s["values"]]
                ax.plot(x, vals, marker="o", markersize=4, label=s["name"], color=PALETTE[i % len(PALETTE)])
            ax.set_xticks(x, cats)
            ax.legend(fontsize=7, frameon=False, title=None)
        else:
            raise ValueError(f"unsupported chart type {t}")
        _style(ax, spec)
        if t == "heatmap":
            ax.grid(False)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)
