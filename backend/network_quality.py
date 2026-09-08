"""
Stage 7: Network Quality Score

Converts raw network metrics (download, upload, ping, jitter) into a
single 0-100 score. Handles missing values by redistributing weights
among whichever metrics are actually present.
"""

# Baseline values used to normalize each metric to a 0-100 scale.
# These are simple, explainable thresholds (not machine-learned).
DOWNLOAD_BASELINE_MBPS = 50   # 50 Mbps or more = full marks
UPLOAD_BASELINE_MBPS = 20     # 20 Mbps or more = full marks
PING_MAX_MS = 100             # 100ms or more ping = 0 marks
JITTER_PENALTY_MULTIPLIER = 3 # jitter is penalized more aggressively than ping

# How much each metric contributes to the final score, when ALL metrics are present.
WEIGHTS = {
    "download_speed": 0.35,
    "ping": 0.30,
    "jitter": 0.20,
    "upload_speed": 0.15,
}


def score_download(download_speed):
    """Higher download speed = higher score. Capped at 100."""
    score = (download_speed / DOWNLOAD_BASELINE_MBPS) * 100
    return min(score, 100)


def score_upload(upload_speed):
    """Higher upload speed = higher score. Capped at 100."""
    score = (upload_speed / UPLOAD_BASELINE_MBPS) * 100
    return min(score, 100)


def score_ping(ping):
    """Lower ping = higher score. Floored at 0."""
    score = 100 - ping
    return max(score, 0)


def score_jitter(jitter):
    """Lower jitter = higher score. Jitter is penalized more heavily than ping."""
    score = 100 - (jitter * JITTER_PENALTY_MULTIPLIER)
    return max(score, 0)


def calculate_quality_score(download_speed=None, upload_speed=None, ping=None, jitter=None):
    """
    Calculates a 0-100 Network Quality Score from available metrics.

    Any metric that is None (missing) is skipped, and its weight is
    redistributed proportionally among the metrics that ARE present.

    Returns a dict: {"score": float, "category": str, "metrics_used": list}
    """
    # Step 1: work out which metrics are actually available
    available = {}

    if download_speed is not None:
        available["download_speed"] = score_download(download_speed)

    if upload_speed is not None:
        available["upload_speed"] = score_upload(upload_speed)

    if ping is not None:
        available["ping"] = score_ping(ping)

    if jitter is not None:
        available["jitter"] = score_jitter(jitter)

    # If nothing is available at all, we cannot calculate a score
    if len(available) == 0:
        return {"score": None, "category": "Unknown", "metrics_used": []}

    # Step 2: redistribute weights among only the available metrics
    total_available_weight = sum(WEIGHTS[metric] for metric in available)

    final_score = 0
    for metric, metric_score in available.items():
        # this metric's share of the total available weight
        adjusted_weight = WEIGHTS[metric] / total_available_weight
        final_score += metric_score * adjusted_weight

    final_score = round(final_score, 1)

    # Step 3: convert the number into a category
    category = categorize_score(final_score)

    return {
        "score": final_score,
        "category": category,
        "metrics_used": list(available.keys()),
    }


def categorize_score(score):
    """Converts a numeric score into Good / Moderate / Poor."""
    if score >= 80:
        return "Good"
    elif score >= 60:
        return "Moderate"
    else:
        return "Poor"


# ---------- Quick manual test (run this file directly to check it works) ----------
if __name__ == "__main__":
    # Test 1: all metrics present, good network
    result1 = calculate_quality_score(download_speed=60, upload_speed=25, ping=15, jitter=2)
    print("Test 1 (good network, all metrics):", result1)

    # Test 2: poor network, all metrics present
    result2 = calculate_quality_score(download_speed=2, upload_speed=1, ping=180, jitter=40)
    print("Test 2 (poor network, all metrics):", result2)

    # Test 3: missing jitter and upload speed
    result3 = calculate_quality_score(download_speed=30, ping=40, jitter=None, upload_speed=None)
    print("Test 3 (missing jitter + upload):", result3)

    # Test 4: only ping available
    result4 = calculate_quality_score(ping=25)
    print("Test 4 (only ping available):", result4)

    # Test 5: nothing available
    result5 = calculate_quality_score()
    print("Test 5 (nothing available):", result5)