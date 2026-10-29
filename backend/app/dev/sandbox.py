"""Parent side of the Python console: spawns the isolated runner with time and memory limits."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import psutil

from ..config import get_settings

RUNNER = Path(__file__).with_name("sandbox_runner.py")
SECRET_ENV = re.compile(r"SECRET|TOKEN|PASSWORD|PASSWD|KEY|CREDENTIAL|DATABASE_URL|AWS_|AZURE_|GCP_|GOOGLE_", re.I)

TEMPLATES = [
    {"id": "descriptives", "title": "Descriptive statistics",
     "code": "# df is the selected dataset (pandas DataFrame)\nshow(df.describe().T, 'Summary of numeric columns')\n"
             "print(df.isna().sum())"},
    {"id": "correlation", "title": "Correlation matrix",
     "code": "num = df.select_dtypes('number')\nshow(num.corr(method='pearson').round(3), 'Pearson correlations')\n"
             "r = stats.pearsonr(num.iloc[:, 0], num.iloc[:, 1], nan_policy='omit') if num.shape[1] > 1 else None\n"
             "print(r)"},
    {"id": "regression", "title": "Linear regression",
     "code": "# Replace the column names with your own\nmodel = smf.ols('Q(\"y\") ~ Q(\"x1\") + Q(\"x2\")', data=df).fit()\n"
             "print(model.summary())"},
    {"id": "ttest", "title": "Independent-samples t-test",
     "code": "# Replace 'score' and 'group' with your column names\ng = df.dropna(subset=['score', 'group'])\n"
             "a, b = [x['score'] for _, x in g.groupby('group')][:2]\nprint(stats.ttest_ind(a, b, equal_var=False))"},
    {"id": "anova", "title": "One-way ANOVA",
     "code": "groups = [x['score'].dropna() for _, x in df.groupby('group')]\nprint(stats.f_oneway(*groups))\n"
             "print(stats.tukey_hsd(*groups))"},
    {"id": "plot", "title": "Histogram",
     "code": "col = df.select_dtypes('number').columns[0]\nplt.hist(df[col].dropna(), bins=20, color='#1f3a5f')\n"
             "plt.title(f'Distribution of {col}')\nplt.xlabel(col); plt.ylabel('Frequency')"},
]


def run_code(code: str, dataset_path: Path | None) -> dict[str, Any]:
    s = get_settings()
    workdir = s.sandbox_dir / uuid.uuid4().hex
    workdir.mkdir(parents=True)
    try:
        (workdir / "job.json").write_text(json.dumps({"code": code}), encoding="utf-8")
        if dataset_path is not None:
            shutil.copy2(dataset_path, workdir / "dataset.parquet")
        # Pass a scrubbed environment: no application settings or anything that looks like a credential.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("STATEASE_") and not SECRET_ENV.search(k)}
        env.update({"MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8", "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1", "MPLCONFIGDIR": str(workdir), "TEMP": str(workdir),
                    "TMP": str(workdir), "POLARS_SKIP_CPU_CHECK": "1"})
        t0 = time.perf_counter()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen([sys.executable, "-I", "-X", "utf8", str(RUNNER), str(workdir)], cwd=workdir, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        ps = psutil.Process(proc.pid)
        limit = s.python_memory_mb * 1024 * 1024
        killed = None
        peak = 0
        while proc.poll() is None:
            elapsed = time.perf_counter() - t0
            try:
                rss = ps.memory_info().rss
                peak = max(peak, rss)
            except psutil.Error:
                rss = 0
            if elapsed > s.python_timeout_seconds:
                killed = f"Execution exceeded the {s.python_timeout_seconds:g}-second time limit and was stopped."
            elif rss > limit:
                killed = f"Execution exceeded the {s.python_memory_mb} MB memory limit and was stopped."
            if killed:
                proc.kill()
                break
            time.sleep(0.05)
        stdout, stderr = proc.communicate(timeout=10)
        duration = (time.perf_counter() - t0) * 1000
        result_file = workdir / "result.json"
        if killed or not result_file.exists():
            return {"status": "killed" if killed else "error", "stdout": stdout.decode("utf-8", "replace")[-20000:],
                    "stderr": killed or stderr.decode("utf-8", "replace")[-20000:] or "The process ended unexpectedly.",
                    "tables": [], "figures": [], "duration_ms": duration, "peak_memory_mb": peak / 1e6}
        result = json.loads(result_file.read_text(encoding="utf-8"))
        result.update(duration_ms=duration, peak_memory_mb=peak / 1e6)
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
