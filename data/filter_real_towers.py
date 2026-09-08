"""
Real Tower Data Loader

Yeh script OpenCelliD se download ki gayi Pakistan CSV file ko padhta hai,
aur usse sirf Lahore ke bounding box ke andar wale towers filter karta hai.

Kaise use karein:
1. https://opencellid.org se free account banao
2. Yeh URL se Pakistan ka data download karo (apna token daal ke):
   https://opencellid.org/downloads.php?token=YOUR_TOKEN&type=mcc&file=410.csv.gz
3. .gz file ko extract karo -> 410.csv milega
4. Us 410.csv file ko is script ke saath waisi hi folder mein rakho
5. Yeh script chalao: python filter_real_towers.py
"""

import csv

# OpenCelliD se download ki gayi raw file ka naam
INPUT_FILE = "410.csv"

# Output: humare project ke schema mein converted file
OUTPUT_FILE = "towers_real.csv"

# Lahore ka approximate bounding box (lat/long range)
# Isse bahar wale towers ignore ho jayenge
LAHORE_BOUNDS = {
    "min_lat": 31.30,
    "max_lat": 31.70,
    "min_lon": 74.10,
    "max_lon": 74.50,
}


def filter_lahore_towers():
    filtered_towers = []

    # OpenCelliD ki file mein header row NAHI hoti — pehli row se hi data start ho jata hai.
    # Isliye humein column names manually batani padengi (OpenCelliD ka standard column order):
    column_names = ["radio", "mcc", "net", "area", "cell", "unit",
                     "lon", "lat", "range", "samples", "changeable",
                     "created", "updated", "averageSignal"]

    with open(INPUT_FILE, newline="") as infile:
        reader = csv.DictReader(infile, fieldnames=column_names)

        for row in reader:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, KeyError):
                continue  # agar row corrupt/missing hai, skip karo

            # Sirf Lahore bounding box ke andar wale towers rakho
            if (LAHORE_BOUNDS["min_lat"] <= lat <= LAHORE_BOUNDS["max_lat"] and
                    LAHORE_BOUNDS["min_lon"] <= lon <= LAHORE_BOUNDS["max_lon"]):

                filtered_towers.append({
                    "tower_id": row.get("cell", "unknown"),
                    "latitude": lat,
                    "longitude": lon,
                    "operator": row.get("net", "unknown"),   # network code (operator ka exact naam nahi deta)
                    "technology": row.get("radio", "unknown"),  # GSM/UMTS/LTE
                    "data_source": "REAL PUBLIC DATA",
                })

    # Naya filtered CSV likho, humare project ke schema mein
    with open(OUTPUT_FILE, "w", newline="") as outfile:
        fieldnames = ["tower_id", "latitude", "longitude", "operator", "technology", "data_source"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filtered_towers)

    print(f"Total Lahore towers found: {len(filtered_towers)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    filter_lahore_towers()
