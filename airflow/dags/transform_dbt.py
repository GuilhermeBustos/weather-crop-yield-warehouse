"""DAG: transform_dbt — run the wcy dbt project via astronomer-cosmos."""

from airflow.sdk import dag
from common import DBT_PROJECT_DIR, PROFILES_DIR, WEATHER_DATASET, YIELD_DATASET, make_default_args
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import LoadMode, TestBehavior
from cosmos.operators.local import DbtSeedLocalOperator

_profile_config = ProfileConfig(
    profile_name="wcy", target_name="dev", profiles_yml_filepath=PROFILES_DIR / "profiles.yml"
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
        project_dir=str(DBT_PROJECT_DIR),
        profile_config=_profile_config,
        install_deps=True,
    )

    transform = DbtTaskGroup(
        group_id="dbt_transform",
        project_config=ProjectConfig(
            dbt_project_path=DBT_PROJECT_DIR,
            manifest_path=DBT_PROJECT_DIR / "target" / "manifest.json",
        ),
        profile_config=_profile_config,
        execution_config=ExecutionConfig(),
        render_config=RenderConfig(
            load_method=LoadMode.DBT_MANIFEST,
            emit_datasets=False,
            exclude=["resource_type:seed"],
            test_behavior=TestBehavior.AFTER_ALL,
        ),
    )

    seed >> transform


transform_dbt()
