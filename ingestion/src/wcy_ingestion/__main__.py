import argparse
import logging
from pathlib import Path

from wcy_ingestion import seed
from wcy_ingestion.config import Settings
from wcy_ingestion.pipelines import nass_yield, weather

_SEED_CSV = Path(__file__).parents[3] / "dbt" / "seeds" / "county_centroids.csv"


def _seed(settings: Settings) -> None:
    count = seed.build(_SEED_CSV, settings.target_states)
    logging.info("wrote %d county centroids to %s", count, _SEED_CSV)


def _weather(settings: Settings) -> None:
    weather.run(settings)


def _yield(settings: Settings) -> None:
    nass_yield.run(settings)


_COMMANDS = {"seed": _seed, "weather": _weather, "yield": _yield}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(prog="wcy_ingestion")
    parser.add_argument("command", choices=_COMMANDS)
    args = parser.parse_args()

    _COMMANDS[args.command](Settings())


if __name__ == "__main__":
    main()
