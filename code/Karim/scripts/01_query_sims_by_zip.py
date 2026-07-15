"""
Query NYC Open Data's Street Sign Work Orders dataset for a given ZIP code and
save the filtered street-name-sign records to a CSV. Standalone script, no
Jupyter or AI assistant required.

Usage:
    python 01_query_sims_by_zip.py 10002

Output:
    signs_zip_10002.csv  (in the current directory)
"""
import sys
import warnings

import pandas as pd
import pgeocode
import requests
from pyproj import Transformer

warnings.filterwarnings("ignore")

API_URL = "https://data.cityofnewyork.us/resource/qt6m-xctn.json"
RADIUS_FEET = 5280  # 1 mile
LIMIT = 5000
ACTIVE_ONLY = True  # exclude voided/historical records


def main(zip_code: str):
    to_sp = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)
    nomi = pgeocode.Nominatim("us")

    zip_info = nomi.query_postal_code(zip_code)
    if pd.isna(zip_info.latitude):
        raise SystemExit(f"ZIP code {zip_code} not found. Check the code and try again.")

    lat, lon = zip_info.latitude, zip_info.longitude
    print(f"ZIP {zip_code}: {zip_info.place_name} ({lat:.4f}, {lon:.4f})")

    cx, cy = to_sp.transform(lon, lat)
    x_min, x_max = cx - RADIUS_FEET, cx + RADIUS_FEET
    y_min, y_max = cy - RADIUS_FEET, cy + RADIUS_FEET

    # Filters, per NYC DOT guidance (D. Arcement):
    #   - SN-*/SI-* sign codes (street name blades / standard signs)
    #   - ST* order numbers (street name sign orders per SIMS)
    #   - sign_size contains '009' (9" height) to exclude oversized signs
    where_parts = [
        "(sign_code like 'SN-%' OR sign_code like 'SI-%')",
        "order_number like 'ST%'",
        "sign_size like '%009%'",
        "sign_x_coord IS NOT NULL",
        "sign_y_coord IS NOT NULL",
        f"sign_x_coord >= '{x_min:.0f}'",
        f"sign_x_coord <= '{x_max:.0f}'",
        f"sign_y_coord >= '{y_min:.0f}'",
        f"sign_y_coord <= '{y_max:.0f}'",
    ]
    if ACTIVE_ONLY:
        where_parts.append("record_type != 'Historical'")

    params = {
        "$where": " AND ".join(where_parts),
        "$limit": LIMIT,
        "$order": "order_number ASC",
    }

    print("Querying NYC Open Data...")
    resp = requests.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    raw = resp.json()
    print(f"Records returned: {len(raw)}")

    df = pd.DataFrame(raw)
    if df.empty:
        raise SystemExit("No results. Try a different ZIP code.")

    df["sign_x_coord"] = pd.to_numeric(df["sign_x_coord"], errors="coerce")
    df["sign_y_coord"] = pd.to_numeric(df["sign_y_coord"], errors="coerce")
    mask = df["sign_x_coord"].notna() & df["sign_y_coord"].notna()
    lons, lats = to_wgs.transform(
        df.loc[mask, "sign_x_coord"].values, df.loc[mask, "sign_y_coord"].values
    )
    df.loc[mask, "longitude"] = lons
    df.loc[mask, "latitude"] = lats

    cols = [
        "order_number", "record_type", "sign_code", "sign_description", "sign_size",
        "on_street", "from_street", "to_street", "side_of_street",
        "sign_location", "support", "sheeting_type",
        "sign_x_coord", "sign_y_coord", "latitude", "longitude",
        "order_completed_on_date",
    ]
    cols = [c for c in cols if c in df.columns]
    df = df[cols].copy()

    out_path = f"signs_zip_{zip_code}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} records to {out_path}")
    print("Next: run 02_generate_signs_data.py on this file.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python 01_query_sims_by_zip.py <ZIP_CODE>")
    main(sys.argv[1])
