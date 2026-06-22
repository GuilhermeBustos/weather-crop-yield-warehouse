from datetime import date

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _discover_project_id() -> str:
    import google.auth

    _, project = google.auth.default()
    if not project:
        raise ValueError("GCP project not found in ADC; set WCY_PROJECT_ID explicitly")
    return project


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WCY_", env_file=".env")

    # GCP — project_id resolved from ADC when WCY_PROJECT_ID is not set
    project_id: str = Field(default_factory=_discover_project_id)
    bronze_bucket: str  # set WCY_BRONZE_BUCKET in .env
    raw_dataset: str = "raw"
    region: str = "us-central1"

    # Scope — locked to the 2025 Corn Belt slice
    target_states: list[str] = ["IA", "IL", "IN", "NE", "MN"]

    # Open-Meteo archive
    start_date: date = date(2025, 4, 1)
    end_date: date = date(2025, 10, 31)
    daily_variables: list[str] = [
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        "precipitation_sum",
        "et0_fao_evapotranspiration",
        "shortwave_radiation_sum",
        "windspeed_10m_max",
    ]
    batch_size: int = 50

    # NASS Quick Stats
    commodities: list[str] = ["CORN", "SOYBEANS"]
    nass_year: int = 2025
    nass_secret_name: str  # set WCY_NASS_SECRET_NAME to the Secret Manager resource name
