"""Local DAG parse check — called by `make dags-validate`."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp())

# Mirror the Composer env vars that DAGs depend on for path/config resolution.
# All use setdefault so they're no-ops when the real Composer values are present.
# Evaluated here (before Airflow import / CWD changes) so resolve() is reliable.
_repo_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("DBT_PROFILES_DIR", str(_repo_root / "dbt" / "profiles"))
os.environ.setdefault("WCY_RAW_DATASET", "raw")

# Airflow adds the dags folder to sys.path in Composer; mirror that locally.
sys.path.insert(0, str(Path(__file__).parent / "dags"))

from airflow.models import DagBag  # noqa: E402

bag = DagBag("airflow/dags", include_examples=False)
for path, err in bag.import_errors.items():
    print(f"ERROR  {path}:\n{err}", file=sys.stderr)
if bag.import_errors:
    sys.exit(1)
print(f"OK  {len(bag.dags)} DAG(s) parsed, 0 import errors")
