"""DAG: transform_dbt — run the wcy dbt project via astronomer-cosmos."""

import os
from pathlib import Path

from airflow.sdk import dag
from common import WEATHER_DATASET, YIELD_DATASET, make_default_args
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import LoadMode
from cosmos.operators.local import DbtSeedLocalOperator

# DBT_PROFILES_DIR is set in Composer by Terraform (T1) to the synced dbt/profiles/ path.
# Fall back to the repo-relative location for local DAG parse validation.
_PROFILES_DIR = Path(
    os.environ.get(
        "DBT_PROFILES_DIR", str(Path(__file__).resolve().parents[2] / "dbt" / "profiles")
    )
)
_PROJECT_DIR = _PROFILES_DIR.parent

_profile_config = ProfileConfig(
    profile_name="wcy", target_name="dev", profiles_yml_filepath=_PROFILES_DIR / "profiles.yml"
)


@dag(
    dag_id="transform_dbt",
    schedule=[WEATHER_DATASET, YIELD_DATASET],
    catchup=False,
    default_args=make_default_args(),
    tags=["wcy", "transform"],
)
def transform_dbt():
    seed = DbtSeedLocalOperator(
        task_id="dbt_seed",
        project_dir=str(_PROJECT_DIR),
        profile_config=_profile_config,
        install_deps=True,
    )

    transform = DbtTaskGroup(
        group_id="dbt_transform",
        project_config=ProjectConfig(
            dbt_project_path=_PROJECT_DIR,
            # LoadMode.DBT_MANIFEST reads the pre-generated manifest.json instead of
            # running dbt ls, avoiding any profile/credential requirement at parse time.
            manifest_path=_PROJECT_DIR / "target" / "manifest.json",
        ),
        profile_config=_profile_config,
        execution_config=ExecutionConfig(),
        render_config=RenderConfig(load_method=LoadMode.DBT_MANIFEST, emit_datasets=False),
    )

    seed >> transform


transform_dbt()
