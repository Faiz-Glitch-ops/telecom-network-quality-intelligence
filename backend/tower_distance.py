"""Utilities for finding the closest tower to a GPS measurement."""

from math import asin, cos, radians, sin, sqrt


EARTH_RADIUS_KM = 6371.0


def haversine_distance_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Return the great-circle distance between two coordinates in kilometres."""
    latitude_delta = radians(latitude_2 - latitude_1)
    longitude_delta = radians(longitude_2 - longitude_1)
    first_latitude = radians(latitude_1)
    second_latitude = radians(latitude_2)

    a = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude)
        * cos(second_latitude)
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def find_nearest_tower(latitude: float, longitude: float, towers: list[dict]) -> dict | None:
    """Find the closest tower and return its details plus distance in kilometres."""
    if not towers:
        return None

    nearest_tower = min(
        towers,
        key=lambda tower: haversine_distance_km(
            latitude,
            longitude,
            tower["latitude"],
            tower["longitude"],
        ),
    )
    distance = haversine_distance_km(
        latitude,
        longitude,
        nearest_tower["latitude"],
        nearest_tower["longitude"],
    )
    return {
        "tower_id": nearest_tower["tower_id"],
        "distance_km": round(distance, 3),
        "operator": nearest_tower["operator"],
        "technology": nearest_tower["technology"],
        "data_source": nearest_tower["data_source"],
    }
