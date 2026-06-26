import sys
from pathlib import Path

# Make airflow/dags/ importable as a plain namespace so tests can do `from common import ...`.
sys.path.insert(0, str(Path(__file__).parent.parent))
