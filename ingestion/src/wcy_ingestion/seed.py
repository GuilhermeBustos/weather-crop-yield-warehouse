import csv
import io
import urllib.request
import zipfile
from pathlib import Path

_GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2025_Gazetteer/2025_Gaz_counties_national.zip"
)
_OUT_COLUMNS = ["fips", "state_alpha", "county_name", "lat", "lon"]


def build(output: Path, states: list[str]) -> int:
    with urllib.request.urlopen(_GAZETTEER_URL) as resp:
        raw = resp.read()

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        txt_name = next(n for n in zf.namelist() if n.endswith(".txt"))
        content = zf.read(txt_name).decode("utf-8")

    state_set = frozenset(states)
    reader = csv.DictReader(io.StringIO(content), delimiter="|")
    reader.fieldnames = [f.strip() for f in reader.fieldnames]

    rows = []
    for row in reader:
        if row["USPS"] not in state_set:
            continue
        rows.append(
            {
                "fips": row["GEOID"],
                "state_alpha": row["USPS"],
                "county_name": row["NAME"],
                "lat": row["INTPTLAT"].strip(),
                "lon": row["INTPTLONG"].strip(),
            }
        )

    rows.sort(key=lambda r: r["fips"])

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
