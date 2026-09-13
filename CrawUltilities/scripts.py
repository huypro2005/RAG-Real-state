import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv


load_dotenv()

GOONG_API_KEY = os.getenv("GOONG_API_KEY")
SEARCH_RADIUS = 4000
GRID_STEP = 0.05
OUTPUT_FILE = "hcm_pois.csv"


def crawl_goong_pois(grid_centers):
    all_pois = []
    seen_place_ids = set()
    search_url = "https://rsapi.goong.io/Place/AutoComplete"
    detail_url = "https://rsapi.goong.io/Place/Detail"
    categories = {
        "school": "trường học",
        "hospital": "bệnh viện",
        "market": "chợ",
    }

    try:
        for lat, lon in grid_centers:
            for category, keyword in categories.items():
                try:
                    response = requests.get(
                        search_url,
                        params={
                            "input": keyword,
                            "location": f"{lat},{lon}",
                            "radius": SEARCH_RADIUS,
                            "limit": 20,
                            "api_key": GOONG_API_KEY,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    predictions = response.json().get("predictions", [])
                    time.sleep(0.5)

                    for prediction in predictions:
                        place_id = prediction.get("place_id")

                        if not place_id or place_id in seen_place_ids:
                            continue

                        detail_response = requests.get(
                            detail_url,
                            params={
                                "place_id": place_id,
                                "api_key": GOONG_API_KEY,
                            },
                            timeout=30,
                        )
                        detail_response.raise_for_status()
                        item = detail_response.json().get("result", {})
                        time.sleep(0.5)

                        location = item.get("geometry", {}).get("location", {})
                        if location.get("lat") is None or location.get("lng") is None:
                            continue

                        seen_place_ids.add(place_id)
                        all_pois.append(
                            {
                                "poi_id": f"goong_{place_id}",
                                "name": item.get(
                                    "name", prediction.get("description")
                                ),
                                "category": category,
                                "lat": location["lat"],
                                "lon": location["lng"],
                                "address": item.get("formatted_address"),
                            }
                        )
                except Exception as e:
                    print(f"Error at {lat},{lon} ({category}): {e}")

            print(f"Scanned: {lat:.2f}, {lon:.2f} | Collected: {len(all_pois)}")
    finally:
        # Luon luu du lieu da thu duoc, ke ca khi bam Ctrl+C.
        df = pd.DataFrame(
            all_pois,
            columns=["poi_id", "name", "category", "lat", "lon", "address"],
        ).drop_duplicates(subset=["poi_id"])
        df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
        print(f"Saved {len(df)} unique POIs to {OUTPUT_FILE}")

    return df


grid_centers = []
lat = 10.35

while lat <= 11.16:
    lon = 106.35

    while lon <= 106.95:
        grid_centers.append((lat, lon))
        lon = round(lon + GRID_STEP, 10)

    lat = round(lat + GRID_STEP, 10)

crawl_goong_pois(grid_centers)
