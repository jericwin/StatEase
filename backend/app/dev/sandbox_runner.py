"""Executed in a separate Python process (``python -I sandbox_runner.py <workdir>``).

Restrictions applied inside the child process (defence in depth; the process boundary, time and
memory limits enforced by the parent are the primary controls; for hostile multi-tenant use run the
console in a container with no network and a read-only filesystem, see docs/SECURITY.md):
- networking, subprocesses, ctypes and native-library loading are blocked through an audit hook;
- files may be written only inside the job's working directory;
- files may be read only from the working directory and the Python installation.
"""

import base64
import contextlib
import io
import json
import os
import sys
import traceback

WORKDIR = os.path.realpath(sys.argv[1])
os.chdir(WORKDIR)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402
import scipy  # noqa: E402,F401
import statsmodels.api as sm  # noqa: E402,F401
import statsmodels.formula.api as smf  # noqa: E402,F401
from scipy import stats  # noqa: E402,F401

try:
    import pingouin as pg  # noqa: F401
except Exception:  # noqa: BLE001
    pg = None

READ_ROOTS = [WORKDIR, os.path.realpath(sys.prefix), os.path.realpath(sys.base_prefix)]
BLOCKED_EVENTS = ("socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork",
                  "ctypes.", "winreg.", "_winapi.", "os.startfile", "webbrowser.", "urllib.Request",
                  "ftplib.", "smtplib.", "imaplib.", "poplib.", "telnetlib.", "http.client")
FS_EVENTS = {"os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "shutil.rmtree", "shutil.copyfile",
             "shutil.move", "os.truncate", "os.symlink", "os.link"}
BLOCKED_IMPORTS = {"socket", "subprocess", "ctypes", "multiprocessing", "requests", "urllib3", "httpx", "_socket",
                   "asyncio.subprocess", "pty"}


def _inside(path, roots):
    try:
        real = os.path.realpath(os.fspath(path))
    except (TypeError, ValueError):
        return False
    return any(real == r or real.startswith(r + os.sep) for r in roots)


def _hook(event, args):
    if event.startswith(BLOCKED_EVENTS):
        raise PermissionError(f"'{event}' is not allowed in the analysis console.")
    if event == "import" and args and str(args[0]).split(".")[0] in BLOCKED_IMPORTS:
        raise PermissionError(f"Importing '{args[0]}' is not allowed in the analysis console.")
    if event == "open" and args:
        path, mode = args[0], (args[1] if len(args) > 1 else "r") or "r"
        if isinstance(path, int):
            return
        writing = any(c in str(mode) for c in "wax+") or (isinstance(mode, int) and mode & (os.O_WRONLY | os.O_RDWR))
        roots = [WORKDIR] if writing else READ_ROOTS
        if not _inside(path, roots):
            raise PermissionError("File access outside the console's working directory is not allowed.")
    if event in FS_EVENTS and args and not _inside(args[0], [WORKDIR]):
        raise PermissionError("File changes outside the console's working directory are not allowed.")


tables = []


def show(obj, title=None, max_rows=500):
    """Display a DataFrame (pandas or polars) or Series as a table in the console output."""
    if isinstance(obj, pl.DataFrame):
        obj = obj.to_pandas()
    if isinstance(obj, pd.Series):
        obj = obj.to_frame()
    if not isinstance(obj, pd.DataFrame):
        print(obj)
        return
    frame = obj.head(max_rows).reset_index() if not isinstance(obj.index, pd.RangeIndex) else obj.head(max_rows)
    tables.append({"title": title or f"Table {len(tables) + 1}", "columns": [str(c) for c in frame.columns],
                   "rows": json.loads(frame.to_json(orient="values", date_format="iso", default_handler=str)),
                   "total_rows": int(len(obj))})


def main():
    job = json.load(open(os.path.join(WORKDIR, "job.json"), encoding="utf-8"))
    namespace = {"pd": pd, "np": np, "pl": pl, "stats": stats, "sm": sm, "smf": smf, "plt": plt, "show": show,
                 "pg": pg, "__name__": "__console__"}
    data_file = os.path.join(WORKDIR, "dataset.parquet")
    if os.path.exists(data_file):
        namespace["df"] = pd.read_parquet(data_file)
    # Modules already loaded by the libraries above stay usable by those libraries, but are evicted from the
    # import cache so that user code importing them goes through the audit hook.
    for name in list(sys.modules):
        if name.split(".")[0] in BLOCKED_IMPORTS:
            del sys.modules[name]
    sys.addaudithook(_hook)
    out, err = io.StringIO(), io.StringIO()
    status = "completed"
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            exec(compile(job["code"], "<console>", "exec"), namespace)  # noqa: S102 - isolated child process
        except Exception:  # noqa: BLE001
            status = "error"
            tb = traceback.format_exc().splitlines()
            err.write("\n".join(line for line in tb if "sandbox_runner.py" not in line))
    figures = []
    for num in plt.get_fignums()[:10]:
        buf = io.BytesIO()
        plt.figure(num).savefig(buf, format="png", dpi=110, bbox_inches="tight")
        figures.append(base64.b64encode(buf.getvalue()).decode())
    result = {"status": status, "stdout": out.getvalue()[-200_000:], "stderr": err.getvalue()[-50_000:],
              "tables": tables[:20], "figures": figures}
    with open(os.path.join(WORKDIR, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, default=str)


main()
