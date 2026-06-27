"""Local DAG parse check — called by `make dags-validate`."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp())

# Airflow adds the dags folder to sys.path in Composer; mirror that locally.
sys.path.insert(0, str(Path(__file__).parent / "dags"))

from airflow.models import DagBag  # noqa: E402

bag = DagBag("airflow/dags", include_examples=False)
for path, err in bag.import_errors.items():
    print(f"ERROR  {path}:\n{err}", file=sys.stderr)
if bag.import_errors:
    sys.exit(1)
print(f"OK  {len(bag.dags)} DAG(s) parsed, 0 import errors")
