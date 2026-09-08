"""Explainable decision-support rules for poor-network locations."""


def make_recommendation(
    quality_category: str,
    tower_distance_km: float | None,
    population_density: float | None,
    population_data_source: str | None = None,
    download_speed: float | None = None,
    ping: float | None = None,
    jitter: float | None = None,
    upload_speed: float | None = None,
) -> dict:
    """Return a cautious recommendation, never a final engineering decision."""
    if quality_category in ("Good", "Moderate"):
        return {
            "action": "No intervention indicated",
            "reason": "The measured network quality is not currently poor.",
            "likely_causes": [],
            "suggested_checks": [],
        }

    if quality_category == "Unknown":
        return {
            "action": "Collect more measurements",
            "reason": "A quality score is not available for this location.",
            "likely_causes": ["Insufficient network metrics"],
            "suggested_checks": ["Repeat the test with all metrics available."],
        }

    likely_causes = []
    suggested_checks = []
    if download_speed is not None and download_speed < 5:
        likely_causes.append("Low measured download capacity")
        suggested_checks.append("Repeat at different times to check for congestion.")
    if upload_speed is not None and upload_speed < 2:
        likely_causes.append("Low measured upload capacity")
    if ping is not None and ping > 100:
        likely_causes.append("High measured latency")
        suggested_checks.append("Check backhaul latency and routing during a repeat test.")
    if jitter is not None and jitter > 20:
        likely_causes.append("Unstable measured latency")
        suggested_checks.append("Repeat the test to distinguish persistent instability from a temporary event.")

    if tower_distance_km is not None and tower_distance_km <= 2:
        suggested_checks.append("Inspect the nearby tower's RF configuration, congestion, antenna orientation, and backhaul.")
        return {
            "action": "Investigate existing tower or antenna",
            "reason": "Poor quality was measured within 2 km of an existing tower; "
            "check RF configuration, congestion, and backhaul.",
            "likely_causes": likely_causes or ["Poor quality despite a nearby public tower record"],
            "suggested_checks": suggested_checks,
        }

    has_real_population = (
        population_density is not None
        and population_data_source == "REAL PUBLIC DATA"
    )
    if has_real_population and population_density >= 5000:
        return {
            "action": "High-priority candidate for new-tower assessment",
            "reason": "Poor quality and high estimated population density were found "
            "without a nearby tower; perform a formal coverage and business study.",
            "likely_causes": likely_causes + ["No nearby public tower record within the 2 km investigation radius"],
            "suggested_checks": suggested_checks + ["Perform a formal RF drive test and coverage study before any deployment decision."],
        }

    return {
        "action": "Lower-priority candidate for further assessment",
        "reason": "Poor quality was measured, but verified population density or "
        "tower proximity does not yet justify a high-priority recommendation.",
        "likely_causes": likely_causes,
        "suggested_checks": suggested_checks + ["Collect repeat readings from nearby streets and times."],
    }
