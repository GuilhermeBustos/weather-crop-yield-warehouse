"""DAG: backfill — manually triggered, parameterized re-run of the full pipeline."""

from airflow.sdk import Param, dag, task
from common import (
    DBT_PROJECT_DIR,
    PROFILES_DIR,
    make_default_args,
    run_nass_yield_year,
    run_weather_window,
)
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import LoadMode
from cosmos.operators.local import DbtSeedLocalOperator

_profile_config = ProfileConfig(
    profile_name="wcy", target_name="dev", profiles_yml_filepath=PROFILES_DIR / "profiles.yml"
)


@dag(
    dag_id="backfill",
    schedule=None,
    catchup=False,
    params={
        "weather_start": Param(
            "2025-04-01",
            type="string",
            format="date",
            description="Weather window start (YYYY-MM-DD)",
        ),
        "weather_end": Param(
            "2025-10-31",
            type="string",
            format="date",
            description="Weather window end (YYYY-MM-DD)",
        ),
        "nass_year": Param(2025, type="integer", description="NASS yield crop year"),
    },
    default_args=make_default_args(),
    tags=["wcy", "backfill"],
)
def backfill():
    @task
    def ingest_weather(**context):
        p = context["params"]
        run_weather_window(p["weather_start"], p["weather_end"])

    @task
    def ingest_yield(**context):
        p = context["params"]
        run_nass_yield_year(p["nass_year"])

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
            load_method=LoadMode.DBT_MANIFEST, emit_datasets=False, exclude=["resource_type:seed"]
        ),
    )

    [ingest_weather(), ingest_yield()] >> seed >> transform


backfill()
