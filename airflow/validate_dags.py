"""Local DAG parse check — called by `make dags-validate`."""

import os
import sys
import tempfile

os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp())

from airflow.models import DagBag  # noqa: E402

bag = DagBag("airflow/dags", include_examples=False)
for path, err in bag.import_errors.items():
    print(f"ERROR  {path}:\n{err}", file=sys.stderr)
if bag.import_errors:
    sys.exit(1)
print(f"OK  {len(bag.dags)} DAG(s) parsed, 0 import errors")
