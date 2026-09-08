"""Population-density lookup with a real-data-first CSV loader."""

import csv
import math
import os
from pathlib import Path

import rasterio
from rasterio.errors import RasterioError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_POPULATION_FILE = PROJECT_ROOT / "data" / "population_density_real.csv"
SAMPLE_POPULATION_FILE = PROJECT_ROOT / "data" / "population_density_sample.csv"
WORLDPOP_FILE = PROJECT_ROOT / "data" / "population" / "pak_pop_2025_CN_100m_R2025A_v1.tif"


def read_population_csv(filepath: str) -> list[dict]:
    """Read population grid cells from the project's standard CSV format."""
    cells = []
    with open(filepath, newline="", encoding="utf-8") as population_file:
        for row in csv.DictReader(population_file):
            cells.append({
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "density_per_km2": float(row["density_per_km2"]),
                "data_source": row["data_source"],
            })
    return cells


def load_population_cells() -> list[dict]:
    """Prefer a downloaded real dataset; use clearly labeled sample data otherwise."""
    filepath = REAL_POPULATION_FILE if os.path.exists(REAL_POPULATION_FILE) else SAMPLE_POPULATION_FILE
    return read_population_csv(filepath)


def find_nearest_population_cell(
    latitude: float,
    longitude: float,
    cells: list[dict],
) -> dict | None:
    """Return population density from WorldPop, or the labeled CSV fallback."""
    if WORLDPOP_FILE.exists():
        try:
            with rasterio.open(WORLDPOP_FILE) as dataset:
                if not (
                    dataset.bounds.left <= longitude <= dataset.bounds.right
                    and dataset.bounds.bottom <= latitude <= dataset.bounds.top
                ):
                    return None
                row, column = dataset.index(longitude, latitude)
                value = float(dataset.read(1, window=((row, row + 1), (column, column + 1)))[0, 0])
                if value == dataset.nodata or value < 0:
                    return None
                cell_width_degrees = abs(dataset.transform.a)
                cell_height_degrees = abs(dataset.transform.e)
                cell_area_km2 = (
                    cell_width_degrees
                    * 111.32
                    * cell_height_degrees
                    * 111.32
                    * max(0.01, abs(math.cos(math.radians(latitude))))
                )
                return {
                    "population_count": round(value, 2),
                    "density_per_km2": round(value / cell_area_km2, 2),
                    "data_source": "REAL PUBLIC DATA - WorldPop 2025",
                }
        except (RasterioError, OSError, ValueError, IndexError) as error:
            print(f"WorldPop raster unavailable; using labeled fallback: {error}")
    if not cells:
        return None
    nearest = min(
        cells,
        key=lambda cell: (cell["latitude"] - latitude) ** 2
        + (cell["longitude"] - longitude) ** 2,
    )
    return {
        "density_per_km2": nearest["density_per_km2"],
        "data_source": nearest["data_source"],
    }
