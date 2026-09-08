"""Area-level aggregation for repeated network measurements."""

from collections import defaultdict


GRID_SIZE_DEGREES = 0.01


def summarize_areas(measurements: list[dict]) -> list[dict]:
    """Group nearby readings and report weak-area confidence transparently."""
    groups = defaultdict(list)
    for measurement in measurements:
        grid_key = (
            round(measurement["latitude"] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES,
            round(measurement["longitude"] / GRID_SIZE_DEGREES) * GRID_SIZE_DEGREES,
        )
        groups[grid_key].append(measurement)

    summaries = []
    for (grid_latitude, grid_longitude), readings in groups.items():
        poor_count = sum(item["quality_category"] == "Poor" for item in readings)
        scores = [
            item["quality_score"]
            for item in readings
            if item["quality_score"] is not None
        ]
        poor_ratio = poor_count / len(readings)
        if len(readings) >= 2 and poor_ratio >= 0.5:
            status = "Confirmed weak area"
        elif poor_count:
            status = "Needs more measurements"
        else:
            status = "No weak pattern detected"
        summaries.append({
            "grid_center": {
                "latitude": round(grid_latitude, 5),
                "longitude": round(grid_longitude, 5),
            },
            "measurement_count": len(readings),
            "poor_measurement_count": poor_count,
            "poor_percentage": round(poor_ratio * 100, 1),
            "average_quality_score": round(sum(scores) / len(scores), 1) if scores else None,
            "status": status,
            "data_source": "REAL DEVICE measurements",
        })
    return sorted(
        summaries,
        key=lambda area: (-area["poor_percentage"], -area["measurement_count"]),
    )
