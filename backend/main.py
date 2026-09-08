"""
Telecom Network Quality Intelligence System - Backend
Stage 2: Ping + Download-speed test endpoints, and measurement storage.
"""

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from typing import Optional
import sqlite3
import csv
import io
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path
from datetime import datetime
from network_quality import calculate_quality_score
from tower_distance import find_nearest_tower
from population_density import (
    WORLDPOP_FILE,
    find_nearest_population_cell,
    load_population_cells,
)
from recommendations import make_recommendation
from area_analysis import summarize_areas

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_TOWERS_FILE = PROJECT_ROOT / "data" / "towers_real.csv"
SAMPLE_TOWERS_FILE = PROJECT_ROOT / "data" / "towers.csv"


def load_towers():
    """
    Tower dataset load karta hai. REAL data (OpenCelliD se filter kiya gaya)
    ko priority deta hai; agar woh file na mile, SAMPLE data pe fallback karta hai.

    Har tower record mein 'data_source' field batata hai woh REAL PUBLIC DATA
    hai ya SAMPLE — isse kabhi confuse nahi hoga ki data asli hai ya nahi.
    """
    try:
        towers = read_towers_csv(REAL_TOWERS_FILE)
        print(f"Loaded {len(towers)} REAL towers from OpenCelliD data.")
        return towers
    except FileNotFoundError:
        towers = read_towers_csv(SAMPLE_TOWERS_FILE)
        print(f"Real tower file not found. Loaded {len(towers)} SAMPLE towers instead.")
        return towers


def read_towers_csv(filepath):
    """CSV file ko padh kar list of tower dicts banata hai."""
    towers = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            towers.append({
                "tower_id": row["tower_id"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "operator": row["operator"],
                "technology": row["technology"],
                "data_source": row["data_source"],
            })
    return towers

app = FastAPI(title="Telecom Network Quality Intelligence System")

# CORS: browser se fetch() calls allow karne ke liye
# (frontend HTML file ek "different origin" maana jaata hai browser ke liye)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # prototype ke liye sab allow, production mein restrict karenge
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = PROJECT_ROOT / "backend" / "network_data.db"


def get_connection():
    """SQLite database se connection banata hai."""
    return sqlite3.connect(DB_FILE)


def create_table():
    """Agar table exist nahi karti, to naya table banata hai."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS network_measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL,
            longitude REAL,
            accuracy REAL,
            download_speed REAL,
            upload_speed REAL,
            ping REAL,
            jitter REAL,
            network_type TEXT,
            data_source TEXT,
            timestamp TEXT,
            quality_score REAL,
            quality_category TEXT,
            nearest_tower_id TEXT,
            nearest_tower_distance_km REAL,
            nearest_tower_data_source TEXT,
            population_density REAL,
            population_data_source TEXT,
            recommendation TEXT,
            recommendation_reason TEXT,
            location_name TEXT,
            location_address TEXT,
            nearby_landmark TEXT
        )
    """)
    existing_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(network_measurements)")
    }
    for column_name, column_type in (
        ("nearest_tower_id", "TEXT"),
        ("nearest_tower_distance_km", "REAL"),
        ("nearest_tower_data_source", "TEXT"),
        ("population_density", "REAL"),
        ("population_data_source", "TEXT"),
        ("recommendation", "TEXT"),
        ("recommendation_reason", "TEXT"),
        ("location_name", "TEXT"),
        ("location_address", "TEXT"),
        ("nearby_landmark", "TEXT"),
    ):
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE network_measurements ADD COLUMN {column_name} {column_type}"
            )
    conn.commit()
    conn.close()


# App start hote hi table create ho jaye
create_table()


# ---------- Pydantic model: incoming data ka shape define karta hai ----------
class Measurement(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: Optional[float] = Field(default=None, ge=0)
    download_speed: Optional[float] = Field(default=None, ge=0)
    upload_speed: Optional[float] = Field(default=None, ge=0)
    ping: Optional[float] = Field(default=None, ge=0)
    jitter: Optional[float] = Field(default=None, ge=0)
    network_type: Optional[str] = None
    data_source: str = "REAL DEVICE"
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    nearby_landmark: Optional[str] = None


# ---------- ENDPOINT 1: /ping ----------
@app.get("/ping")
def ping():
    """
    Khaali, instant response deta hai.
    Frontend isse round-trip time (ping) measure karne ke liye use karta hai.
    """
    return {"status": "ok"}


@app.get("/health")
def health():
    """Report whether the backend and required public datasets are available."""
    towers = load_towers()
    population = load_population_cells()
    return {
        "status": "healthy",
        "tower_count": len(towers),
        "population_source": (
            "REAL PUBLIC DATA - WorldPop 2025"
            if WORLDPOP_FILE.exists()
            else (population[0]["data_source"] if population else "UNAVAILABLE")
        ),
    }


# ---------- ENDPOINT 2: /testfile ----------
@app.get("/testfile")
def testfile():
    """
    Ek fixed-size (2 MB) real file deta hai.
    Frontend isse download karke, time measure kar ke, download speed nikalta hai.
    2MB isliye chuna kyunki chhoti file (jaise 500KB) mein connection-setup overhead
    (TCP handshake, TLS, etc.) speed number ko galat tarah se skew kar deta hai.
    """
    size_in_bytes = 2 * 1024 * 1024  # 2 MB
    data = b"0" * size_in_bytes  # content matter nahi karta, sirf size
    return Response(content=data, media_type="application/octet-stream")


# ---------- ENDPOINT 3: /upload-test ----------
@app.post("/upload-test")
async def upload_test(data: bytes = Body(default=b"")):
    """
    Frontend se bheja gaya data receive karta hai.
    Upload speed measure karne ke liye use hota hai.
    """
    return {"received_bytes": len(data)}


# ---------- ENDPOINT 4: /measurements (POST) ----------
@app.post("/measurements")
def save_measurement(measurement: Measurement):
    """
    Real measurement ko database mein save karta hai.
    Save karne se pehle Network Quality Score bhi calculate karta hai.
    """
    # Quality score calculate karo (missing metrics automatically handle ho jaate hain)
    result = calculate_quality_score(
        download_speed=measurement.download_speed,
        upload_speed=measurement.upload_speed,
        ping=measurement.ping,
        jitter=measurement.jitter,
    )
    nearest_tower = find_nearest_tower(
        measurement.latitude,
        measurement.longitude,
        load_towers(),
    )
    population = find_nearest_population_cell(
        measurement.latitude,
        measurement.longitude,
        load_population_cells(),
    )
    recommendation = make_recommendation(
        result["category"],
        nearest_tower["distance_km"] if nearest_tower else None,
        population["density_per_km2"] if population else None,
        population["data_source"] if population else None,
        measurement.download_speed,
        measurement.ping,
        measurement.jitter,
        measurement.upload_speed,
    )
    measured_at = datetime.now().astimezone().isoformat(timespec="seconds")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO network_measurements
        (latitude, longitude, accuracy, download_speed, upload_speed, ping, jitter,
         network_type, data_source, timestamp, quality_score, quality_category,
         nearest_tower_id, nearest_tower_distance_km, nearest_tower_data_source,
         population_density, population_data_source, recommendation, recommendation_reason,
         location_name, location_address, nearby_landmark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        measurement.latitude,
        measurement.longitude,
        measurement.accuracy,
        measurement.download_speed,
        measurement.upload_speed,
        measurement.ping,
        measurement.jitter,
        measurement.network_type,
        measurement.data_source,
        measured_at,
        result["score"],
        result["category"],
        nearest_tower["tower_id"] if nearest_tower else None,
        nearest_tower["distance_km"] if nearest_tower else None,
        nearest_tower["data_source"] if nearest_tower else None,
        population["density_per_km2"] if population else None,
        population["data_source"] if population else None,
        recommendation["action"],
        recommendation["reason"],
        measurement.location_name,
        measurement.location_address,
        measurement.nearby_landmark,
    ))
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": "Measurement saved",
        "quality_score": result["score"],
        "quality_category": result["category"],
        "measured_at": measured_at,
        "nearest_tower": nearest_tower,
        "population": population,
        "recommendation": recommendation,
    }


# ---------- ENDPOINT 5: /towers (GET) ----------
@app.get("/towers")
def get_towers():
    """
    Sample tower dataset wapas deta hai.
    DATA SOURCE: SAMPLE (real operator data nahi hai)
    """
    towers = load_towers()
    return {"count": len(towers), "data": towers}


# ---------- ENDPOINT 6: /measurements (GET) ----------
@app.get("/measurements")
def get_measurements():
    """
    Ab tak collect kiye gaye sab measurements wapas deta hai.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM network_measurements ORDER BY id DESC")
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    conn.close()

    towers = load_towers()
    population_cells = load_population_cells()
    results = []
    for row in rows:
        measurement = dict(zip(columns, row))
        nearest_tower = find_nearest_tower(
            measurement["latitude"],
            measurement["longitude"],
            towers,
        )
        if nearest_tower is not None:
            measurement["nearest_tower"] = nearest_tower
        elif measurement["nearest_tower_id"] is not None:
            measurement["nearest_tower"] = {
                "tower_id": measurement["nearest_tower_id"],
                "distance_km": measurement["nearest_tower_distance_km"],
                "data_source": measurement["nearest_tower_data_source"],
            }
        else:
            measurement["nearest_tower"] = None
        population = find_nearest_population_cell(
            measurement["latitude"],
            measurement["longitude"],
            population_cells,
        )
        measurement["population"] = population
        measurement["recommendation"] = make_recommendation(
            measurement["quality_category"],
            nearest_tower["distance_km"] if nearest_tower else None,
            population["density_per_km2"] if population else None,
            population["data_source"] if population else None,
            measurement["download_speed"],
            measurement["ping"],
            measurement["jitter"],
            measurement["upload_speed"],
        )
        results.append(measurement)
    return {"count": len(results), "data": results}


@app.delete("/measurements/{measurement_id}")
def delete_measurement(measurement_id: int):
    """Delete one saved measurement by its database ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM network_measurements WHERE id = ?", (measurement_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted == 0:
        return {"status": "not_found", "message": "Measurement not found"}
    return {"status": "success", "message": "Measurement deleted", "id": measurement_id}


@app.delete("/measurements")
def delete_all_measurements():
    """Delete all saved measurements after an explicit frontend confirmation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM network_measurements")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"status": "success", "message": "All measurements deleted", "deleted_count": deleted}


@app.get("/areas")
def get_area_summaries():
    """Return repeated-measurement summaries for approximately 1 km grid areas."""
    return {"data": summarize_areas(get_measurements()["data"])}


@app.get("/weak-locations")
def get_weak_locations():
    """Return Poor measurements with the nearest real public tower distance."""
    measurements = get_measurements()["data"]
    weak_locations = [
        measurement
        for measurement in measurements
        if measurement["quality_category"] == "Poor"
    ]
    return {
        "count": len(weak_locations),
        "data": weak_locations,
        "distance_method": "Haversine great-circle distance in kilometres",
        "tower_source": "OpenCelliD REAL PUBLIC DATA when available",
        "limitation": (
            "Browser GPS cannot identify the exact connected cell tower; "
            "nearest public tower is used as a decision-support reference."
        ),
    }


@app.get("/location/reverse")
def reverse_location(latitude: float, longitude: float):
    """Get a readable location and nearby named place from OpenStreetMap."""
    query = urlencode({
        "format": "jsonv2",
        "lat": latitude,
        "lon": longitude,
        "zoom": 18,
        "addressdetails": 1,
    })
    request = Request(
        f"https://nominatim.openstreetmap.org/reverse?{query}",
        headers={"User-Agent": "TelecomNetworkQualityDemo/1.0"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            result = json.load(response)
    except Exception:
        return {
            "location_name": None,
            "area_name": None,
            "address": None,
            "nearby_landmark": None,
            "data_source": "UNAVAILABLE",
        }
    address = result.get("address", {})
    location_name = (
        address.get("suburb")
        or address.get("neighbourhood")
        or address.get("village")
        or address.get("town")
        or address.get("city")
    )
    landmark = (
        result.get("name")
        or address.get("amenity")
        or address.get("shop")
        or address.get("building")
    )
    return {
        "location_name": location_name,
        "area_name": ", ".join(
            part
            for part in (
                address.get("road"),
                address.get("suburb")
                or address.get("neighbourhood")
                or address.get("quarter")
                or address.get("city_district"),
            )
            if part
        ) or address.get("city"),
        "address": result.get("display_name"),
        "nearby_landmark": landmark,
        "data_source": "OpenStreetMap Nominatim",
    }


@app.get("/ask")
def ask_question(question: str):
    """Answer natural-language dashboard questions using current stored measurements."""
    normalized = question.strip().lower()
    measurements = get_measurements()["data"]
    areas = summarize_areas(measurements)
    if not normalized:
        return {"answer": "Please ask a question about poor areas or tower investigations."}

    poor = [item for item in measurements if item["quality_category"] == "Poor"]
    moderate = [item for item in measurements if item["quality_category"] == "Moderate"]
    good = [item for item in measurements if item["quality_category"] == "Good"]
    investigations = [
        item for item in poor
        if item["recommendation"]["action"] == "Investigate existing tower or antenna"
    ]
    new_tower_candidates = [
        item for item in poor
        if "new-tower" in item["recommendation"]["action"]
    ]
    if any(word in normalized for word in ("cause", "reason")) and any(
        word in normalized for word in ("poor", "weak", "slow", "bad", "internet", "network")
    ):
        poor_causes = [
            cause
            for item in poor
            for cause in item["recommendation"].get("likely_causes", [])
        ]
        return {
            "answer": (
                "Observed evidence-based causes: "
                + (", ".join(sorted(set(poor_causes))) if poor_causes else
                   "no poor measurements are currently stored.")
                + " These are indicators, not confirmed engineering faults."
            ),
            "data": poor,
        }
    if "distance" in normalized and any(
        word in normalized for word in ("tower", "location", "weak", "poor")
    ):
        return {
            "answer": (
                f"{len(poor)} weak location(s) found. Each result includes the "
                "nearest real public tower and Haversine distance in kilometres."
            ),
            "data": poor,
        }
    if any(word in normalized for word in ("poor", "weak", "slow", "bad", "worst", "low quality")):
        return {
            "answer": f"{len(poor)} poor/weak measurement(s) found across "
            f"{sum(area['status'] == 'Confirmed weak area' for area in areas)} confirmed weak area(s).",
            "data": poor,
            "areas": areas,
        }
    if "tower" in normalized and any(word in normalized for word in ("investigat", "check", "fix", "problem", "issue")):
        return {
            "answer": f"{len(investigations)} existing tower investigation candidate(s) found.",
            "data": investigations,
        }
    if ("new" in normalized or "build" in normalized or "deploy" in normalized) and "tower" in normalized:
        return {
            "answer": f"{len(new_tower_candidates)} new-tower assessment candidate(s) found.",
            "data": new_tower_candidates,
        }
    if any(word in normalized for word in ("good", "best", "healthy", "strong")):
        return {"answer": f"{len(good)} Good measurement(s) found.", "data": good}
    if "moderate" in normalized or "average" in normalized or "medium" in normalized:
        return {"answer": f"{len(moderate)} Moderate measurement(s) found.", "data": moderate}
    if any(word in normalized for word in ("how many", "count", "total", "number", "summary", "overview")):
        return {
            "answer": f"Total: {len(measurements)} | Good: {len(good)} | "
            f"Moderate: {len(moderate)} | Poor: {len(poor)}.",
        }
    if any(word in normalized for word in ("where", "location", "place", "area", "areas")):
        return {
            "answer": f"{len(areas)} measured area(s) are available. "
            "Use the map to inspect exact GPS locations and readings.",
            "areas": areas,
        }
    if any(word in normalized for word in ("how", "why", "explain", "score", "calculate")):
        return {
            "answer": "The score combines download (35%), ping (30%), jitter (20%), "
            "and upload (15%). Good is 80-100, Moderate is 60-79, and Poor is 0-59.",
        }
    return {
        "answer": "I can analyze poor areas, tower investigations, new-tower candidates, causes, "
        "scores, current measurements, or exports. Try: 'show poor areas', "
        "'which towers need investigation', 'why is the network slow', or 'summary'.",
        "suggested_questions": [
            "Show poor areas with tower distance",
            "Why is the network slow?",
            "Which towers need investigation?",
            "Where should we consider a new tower?",
            "Give me a summary with counts",
        ],
    }


@app.get("/report", response_class=PlainTextResponse)
def report():
    """Return a plain-text report that can be downloaded or shared."""
    measurements = get_measurements()["data"]
    counts = {
        category: sum(item["quality_category"] == category for item in measurements)
        for category in ("Good", "Moderate", "Poor")
    }
    lines = [
        "TELECOM NETWORK QUALITY REPORT",
        "Generated: " + datetime.now().isoformat(),
        "DATA NOTE: Measurements are REAL DEVICE only when marked in each record.",
        "Tower source: OpenCelliD public data when available.",
        "",
        f"Total measurements: {len(measurements)}",
        f"Good: {counts['Good']}",
        f"Moderate: {counts['Moderate']}",
        f"Poor: {counts['Poor']}",
        "",
        "LOCATION FINDINGS",
    ]
    for item in measurements:
        recommendation = item["recommendation"]
        lines.append(
            f"#{item['id']} | {item['latitude']:.6f}, {item['longitude']:.6f} | "
            f"score={item['quality_score']} ({item['quality_category']}) | "
            f"recommendation={recommendation['action']} | "
            f"reason={recommendation['reason']}"
        )
    return PlainTextResponse(
        content="\ufeff" + "\n".join(lines),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="network-quality-report.txt"'},
    )


@app.get("/export/poor-locations.csv")
def export_poor_locations():
    """Export weak-network locations in an Excel-compatible CSV file."""
    measurements = get_measurements()["data"]
    poor_measurements = [
        item for item in measurements if item["quality_category"] == "Poor"
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "measurement_id",
        "latitude",
        "longitude",
        "gps_accuracy_m",
        "date",
        "time",
        "download_mbps",
        "upload_mbps",
        "ping_ms",
        "jitter_ms",
        "quality_score",
        "quality_category",
        "nearest_tower_id",
        "nearest_tower_distance_km",
        "recommendation",
        "recommendation_reason",
        "measurement_data_source",
        "location_name",
        "location_address",
        "nearby_landmark",
    ])
    for item in poor_measurements:
        timestamp = item.get("timestamp") or ""
        date, separator, time = timestamp.partition("T")
        writer.writerow([
            item["id"],
            f"{item['latitude']:.7f}",
            f"{item['longitude']:.7f}",
            item.get("accuracy"),
            date,
            time.split(".")[0] if separator else "",
            item.get("download_speed"),
            item.get("upload_speed"),
            item.get("ping"),
            item.get("jitter"),
            item.get("quality_score"),
            item.get("quality_category"),
            (item.get("nearest_tower") or {}).get("tower_id"),
            (item.get("nearest_tower") or {}).get("distance_km"),
            (item.get("recommendation") or {}).get("action"),
            (item.get("recommendation") or {}).get("reason"),
            item.get("data_source"),
            item.get("location_name"),
            item.get("location_address"),
            item.get("nearby_landmark"),
        ])
    return PlainTextResponse(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="poor-network-locations.csv"'
        },
    )


@app.get("/export/all-measurements.csv")
def export_all_measurements():
    """Export every saved measurement, regardless of quality category."""
    measurements = get_measurements()["data"]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "measurement_id", "latitude", "longitude", "gps_accuracy_m",
        "date", "time", "download_mbps", "upload_mbps", "ping_ms",
        "jitter_ms", "quality_score", "quality_category", "data_source",
        "nearest_tower_id", "nearest_tower_distance_km", "recommendation",
        "location_name", "location_address", "nearby_landmark",
    ])
    for item in measurements:
        timestamp = item.get("timestamp") or ""
        date, separator, time = timestamp.partition("T")
        tower = item.get("nearest_tower") or {}
        recommendation = item.get("recommendation") or {}
        writer.writerow([
            item["id"], f"{item['latitude']:.7f}", f"{item['longitude']:.7f}",
            item.get("accuracy"), date, time.split(".")[0] if separator else "",
            item.get("download_speed"), item.get("upload_speed"),
            item.get("ping"), item.get("jitter"), item.get("quality_score"),
            item.get("quality_category"), item.get("data_source"),
            tower.get("tower_id"), tower.get("distance_km"),
            recommendation.get("action"),
            item.get("location_name"), item.get("location_address"),
            item.get("nearby_landmark"),
        ])
    return PlainTextResponse(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="all-network-measurements.csv"',
        },
    )