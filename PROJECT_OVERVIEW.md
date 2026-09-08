# Telecom Network Quality Intelligence System

## 1. Project ka aim

Is project ka main aim ek mobile-friendly web application banana hai jo real
device se mobile network quality measure kare aur poor-network areas ko
identify kare.

User phone browser se kisi location par:

1. GPS location capture karta hai.
2. Download speed measure karta hai.
3. Upload speed measure karta hai.
4. Ping aur jitter measure karta hai.
5. Network Quality Score (0-100) calculate hota hai.
6. Result database mein save hota hai.
7. Location map par Good, Moderate ya Poor marker ke saath show hoti hai.
8. Nearby public tower aur population information ke basis par recommendation
   milti hai.

Project ka final purpose telecom teams ko decision-support dena hai. Yeh
system final engineering approval ya tower deployment decision replace nahi
karta.

## 2. Complete workflow

```text
Phone browser
    |
    | GPS + speed + ping + jitter
    v
Frontend web app
    |
    | JSON API request
    v
FastAPI backend
    |
    +-- Quality score calculation
    +-- Nearest tower lookup
    +-- WorldPop population lookup
    +-- Recommendation engine
    +-- SQLite database
    v
Live map + dashboard + NLP answers + Excel export
```

## 3. Technologies used

### Frontend

- HTML5
- CSS3
- JavaScript
- Leaflet.js for interactive maps
- OpenStreetMap map tiles
- Browser Geolocation API for real GPS
- Browser `performance.now()` for timing network tests
- Service Worker for basic caching and PWA-style behavior
- Vercel for frontend hosting

### Backend

- Python
- FastAPI
- Uvicorn
- Pydantic validation
- SQLite database
- Rasterio for GeoTIFF population lookup
- Docker for consistent Railway deployment
- Railway for backend hosting

### Data and analysis

- OpenCelliD real public tower data
- WorldPop 2025 population data
- CSV and Excel-compatible CSV exports
- Explainable rule-based recommendation logic
- Simple NLP intent matching for natural-language questions

## 4. Real network measurements

The application collects these values from the user's device/browser:

- Download speed in Mbps
- Upload speed in Mbps
- Average ping in milliseconds
- Jitter in milliseconds
- GPS latitude and longitude
- GPS accuracy in meters
- Browser-reported effective network type, when available

Every saved measurement is labeled as:

```text
DATA SOURCE: REAL DEVICE
```

Browser limitations are handled honestly. A normal mobile browser cannot
reliably provide actual signal strength, carrier name, connected cell ID, or
LTE/5G radio details. The nearest public tower shown by this project is a
geographic reference, not proof of the exact connected tower.

## 5. Network Quality Score

The score is between 0 and 100:

- Download speed: 35%
- Ping: 30%
- Jitter: 20%
- Upload speed: 15%

The current categories are:

- **Good:** 80-100
- **Moderate:** 60-79
- **Poor:** 0-59

The score is explainable rather than black-box machine learning. Missing
metrics do not crash the application; their weight is redistributed among the
metrics that are available.

High ping and high jitter strongly reduce the score because they indicate
latency and instability. GPS accuracy does not increase or decrease the
network score; it only describes how reliable the location reading is.

## 6. Tower dataset: 470 towers

The project uses OpenCelliD as the real public tower source.

- Country: Pakistan
- Region currently filtered: Lahore bounding box
- Result: **470 real public tower records**
- Data source label: `REAL PUBLIC DATA`
- File: `data/towers_real.csv`

The backend prioritizes `towers_real.csv`. The small sample tower file is only
used as a clearly labeled fallback if the real file is unavailable.

For each measurement, the application calculates the nearest tower and its
distance. Recommendations use this distance as evidence:

- Poor result near an existing tower: investigate existing tower, antenna,
  RF configuration, congestion, or backhaul.
- Poor result far from towers: consider a formal new-tower assessment.

These are recommendations for investigation, not confirmed RF conclusions.

## 7. Pakistan `.tif` population dataset

The project includes a Pakistan population GeoTIFF:

```text
data/population/pak_pop_2025_CN_100m_R2025A_v1.tif
```

This is a WorldPop 2025 real public dataset. Rasterio reads the cell covering
the measurement's GPS coordinates and estimates population density.

The backend reports this source as:

```text
REAL PUBLIC DATA - WorldPop 2025
```

Population density helps prioritize poor areas. A dense area with poor quality
may receive a higher-priority assessment recommendation. If the raster cannot
be read, the backend uses the labeled fallback data and reports the fallback
source instead of silently pretending it is real raster data.

## 8. NLP: iska kya kaam hai?

NLP tab user ko natural language mein project data se questions poochne deta
hai. User technical API query likhne ke bajaye simple English question pooch
sakta hai, for example:

- “Show poor areas”
- “Which towers need investigation?”
- “Where should we consider a new tower?”
- “How many measurements?”
- “Give me a summary”
- “How is the quality score calculated?”

NLP layer:

1. User ke question ka intent samajhti hai.
2. Saved measurements aur area summaries read karti hai.
3. Poor, Moderate aur Good results count karti hai.
4. Tower distance aur recommendations ko summarize karti hai.
5. Plain-language answer dashboard mein show karti hai.

Current NLP explainable rule-based approach use karti hai. Is project ke liye
yeh approach beginner-friendly, fast, free aur auditable hai. Har answer saved
real measurements par based hota hai; NLP fake measurement create nahi karti.

## 9. Recommendations

Recommendation engine poor result ke saath yeh information provide karta hai:

- Action
- Priority
- Reason
- Evidence
- Likely causes
- Suggested checks

Possible actions:

- No intervention indicated
- Investigate existing tower or antenna
- High-priority candidate for new-tower assessment
- Lower-priority candidate for further assessment
- Collect more measurements

Formal drive test, RF planning, coverage study aur business validation ke
baghair koi final tower decision nahi liya jana chahiye.

## 10. Live map

Live Network Map mein:

- Poor measurements red markers hain.
- Moderate measurements amber markers hain.
- Good measurements green markers hain.
- Real public towers black markers hain.
- Current user location blue marker se show hoti hai.
- Blue marker `watchPosition` ke through update hota rehta hai.
- “Locate Me on Map” button fresh high-accuracy GPS lekar map ko current
  location par center karta hai.
- Reverse geocoding se road, locality ya area name show hota hai.
- Agar address service response na de, GPS coordinates fallback label ke roop
  mein show hote hain.

## 11. Storage and exports

Har successful measurement SQLite database mein save hoti hai:

```text
backend/network_data.db
```

Railway production par persistent storage ke liye:

```text
Volume mount: /data
DATABASE_PATH=/data/network_data.db
```

Complete measurement sheet mein Good, Moderate aur Poor readings include hoti
hain. Ismein GPS, time, speed, ping, jitter, score, tower distance,
population source aur recommendation information include hoti hai.

## 12. Deployment

### Backend

- Platform: Railway
- Runtime: Docker
- Health endpoint: `/health`
- Public API:
  `https://telecom-network-quality-intelligence-production.up.railway.app`

### Frontend

- Platform: Vercel
- Entry file: `frontend/index.html`
- Main app: `frontend/app.html`

Phone par app use karne ke liye HTTPS, GPS permission aur deployed Railway API
URL required hain.

## 13. Data-source principle

Project ka core principle **REAL DATA FIRST** hai:

- `REAL DEVICE`: phone browser se captured measurements
- `REAL PUBLIC DATA`: OpenCelliD towers aur WorldPop population
- `SAMPLE`: sirf fallback/testing ke liye clearly labeled data

System sample data ko real data ke naam se present nahi karta.

## 14. Known limitations

- Browser exact connected cell tower ID nahi de sakta.
- Browser actual cellular signal strength reliably expose nahi karta.
- Ping Railway backend tak measured hota hai; yeh pure radio-interface latency
  ka replacement nahi hai.
- GPS accuracy building, weather, device aur satellite visibility par depend
  karti hai.
- Reverse geocoding area name kabhi unavailable ya approximate ho sakta hai.
- OpenCelliD tower record nearest geographic reference hai, connected tower ka
  confirmation nahi.
- Population raster decision-support estimate hai, live census count nahi.

## 15. Project ka final outcome

Yeh system ek practical telecom intelligence workflow provide karta hai:

```text
Real phone measurement
    -> Saved GPS-tagged record
    -> Quality score
    -> Map visualization
    -> Tower and population context
    -> NLP explanation
    -> Investigation recommendation
    -> Downloadable report data
```

