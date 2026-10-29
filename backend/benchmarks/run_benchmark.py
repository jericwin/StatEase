"""Benchmark the import → analysis path on synthetic data of increasing size.

Usage:  python -m benchmarks.run_benchmark [rows ...]      (default: 100000 1000000)
Writes a Markdown table to stdout. Uses a temporary database and storage directory.
"""

from __future__ import annotations

import os
import platform
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import polars as pl
import psutil

TMP = Path(tempfile.mkdtemp(prefix="statease-bench-"))
os.environ["STATEASE_DATABASE_URL"] = f"sqlite:///{(TMP / 'bench.db').as_posix()}"
os.environ["STATEASE_STORAGE_DIR"] = str(TMP / "storage")
os.environ["STATEASE_MAX_UPLOAD_MB"] = "4096"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

API = "/api/v1"
ANALYSES = [
    ("descriptives", {"variables": ["score", "income", "age"]}),
    ("independent_t", {"dependent": "score", "group": "gender"}),
    ("one_way_anova", {"dependent": "score", "factor": "region"}),
    ("correlation", {"variables": ["score", "income", "age"]}),
    ("chi_square", {"rows": "gender", "columns": "region"}),
    ("linear_regression", {"dependent": "score", "predictors": ["income", "age"]}),
    ("mann_whitney", {"dependent": "score", "group": "gender"}),
]


def make_csv(n: int, path: Path) -> None:
    rng = np.random.default_rng(1)
    region = rng.choice(["North", "South", "East", "West"], n)
    df = pl.DataFrame({
        "id": np.arange(n),
        "gender": rng.choice(["Female", "Male"], n),
        "region": region,
        "age": rng.integers(18, 70, n),
        "income": np.round(rng.lognormal(10, 0.6, n), 2),
        "score": np.round(rng.normal(50, 10, n) + (region == "North") * 0.5, 3),
    })
    df.write_csv(path)


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def main(sizes: list[int]) -> None:
    rows = []
    with TestClient(app) as c:
        pid = c.post(f"{API}/projects", json={"name": "bench"}).json()["id"]
        for n in sizes:
            csv = TMP / f"bench_{n}.csv"
            make_csv(n, csv)
            size_mb = csv.stat().st_size / 1e6
            with csv.open("rb") as f:
                up, t_up = timed(lambda: c.post(f"{API}/datasets/uploads", files={"file": (csv.name, f, "text/csv")}))
            up.raise_for_status()
            ds, t_imp = timed(lambda: c.post(f"{API}/datasets", json={"project_id": pid, "upload_id": up.json()["upload"]["upload_id"]}))
            ds.raise_for_status()
            ds = ds.json()
            vid = ds["version"]["id"]
            c.patch(f"{API}/datasets/{ds['id']}/variables", json={"variables": {"age": {"level": "numeric"}}})
            _, t_page = timed(lambda: c.get(f"{API}/datasets/{ds['id']}/preview", params={"offset": n // 2, "limit": 200, "sort": "score"}))
            _, t_rec = timed(lambda: c.get(f"{API}/analyses/recommendations", params={"dataset_id": ds["id"]}))
            row = {"rows": n, "csv_mb": size_mb, "upload_preview": t_up, "import_profile": t_imp, "sorted_page": t_page,
                   "recommendations": t_rec}
            for atype, variables in ANALYSES:
                cfg = c.post(f"{API}/analyses/configurations", json={"project_id": pid, "dataset_version_id": vid,
                                                                      "analysis_type": atype, "variables": variables}).json()
                r, t = timed(lambda cfg=cfg: c.post(f"{API}/analyses/runs", json={"configuration_ids": [cfg["id"]], "wait": True}))
                status = r.json()["items"][0]["status"]
                row[atype] = t if status == "completed" else f"{status}"
            for fmt in ("docx", "xlsx"):
                runs = [x["run"]["id"] for x in c.get(f"{API}/analyses/results", params={"project_id": pid}).json()["items"]
                        if x["run"]["status"] == "completed" and x["run"]["dataset_version_id"] == vid]
                _, row[f"export_{fmt}"] = timed(lambda fmt=fmt, runs=runs: c.post(
                    f"{API}/exports", json={"project_id": pid, "format": fmt, "options": {"run_ids": runs}}).raise_for_status())
            row["peak_rss_mb"] = psutil.Process().memory_info().rss / 1e6
            rows.append(row)
            print(f"done {n:,}", file=sys.stderr)

    cpu = platform.processor() or platform.machine()
    print(f"Hardware: {cpu}; {psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads; "
          f"{psutil.virtual_memory().total / 1e9:.1f} GB RAM; {platform.system()} {platform.release()}; "
          f"Python {platform.python_version()}\n")
    keys = [k for k in rows[0] if k not in ("rows", "csv_mb")]
    print("| Step | " + " | ".join(f"{r['rows']:,} rows ({r['csv_mb']:.0f} MB CSV)" for r in rows) + " |")
    print("|---|" + "---:|" * len(rows))
    for k in keys:
        cells = []
        for r in rows:
            v = r[k]
            cells.append(f"{v:,.0f} MB" if k == "peak_rss_mb" else (f"{v:.2f} s" if isinstance(v, float) else str(v)))
        print(f"| {k.replace('_', ' ')} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [100_000, 1_000_000])
