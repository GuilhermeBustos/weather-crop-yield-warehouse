import os
import sys
from pathlib import Path

# DAG modules read WCY_RAW_DATASET at import time; set a dev default before any import.
os.environ.setdefault("WCY_RAW_DATASET", "raw")

# Make airflow/dags/ importable as a plain namespace so tests can do `from common import ...`.
sys.path.insert(0, str(Path(__file__).parent.parent))
