"""
Query NYC Open Data's Street Sign Work Orders dataset for one or more ZIP
codes and save the filtered street-name-sign records to a CSV. Standalone
script, no Jupyter or AI assistant required.

Pass multiple ZIP codes when your capture route crosses a ZIP boundary --
each ZIP only pulls a 1-mile-radius bounding box around its own centroid, so
a corner just across the line from your primary ZIP (e.g. East Village
corners near a Chelsea/zip-10001 route) won't be in signs_data.json unless
its ZIP is included too.

Usage:
    python 01_query_sims_by_zip.py 10002
    python 01_query_sims_by_zip.py 10001 10003
    python 01_query_sims_by_zip.py --include-historical 10001

Pass --include-historical to keep Historical (replaced/voided) records too --
needed by 04_detect_replacement_history.py to find a sign's prior condition
before a replacement. Writes to a separate *_history.csv so the default
active-only output used by 02_generate_signs_data.py is never affected.

Output:
    signs_zip_10002.csv                (single ZIP)
    signs_zip_10001_10003.csv          (multiple ZIPs, merged and de-duplicated)
    signs_zip_10002_history.csv        (--include-historical)
"""
import argparse
import warnings

import pandas as pd
import pgeocode
import requests
from pyproj import Transformer

warnings.filterwarnings("ignore")

API_URL = "https://data.cityofnewyork.us/resource/qt6m-xctn.json"
RADIUS_FEET = 5280  # 1 mile
LIMIT = 5000
ACTIVE_ONLY = True  # exclude voided/historical records, unless --include-historical

COLS = [
    "order_number", "record_type", "sign_code", "sign_description", "sign_size",
    "on_street", "from_street", "to_street", "side_of_street",
    "sign_location", "support", "sheeting_type",
    "sign_x_coord", "sign_y_coord", "latitude", "longitude",
    "order_completed_on_date",
]


def build_where_parts(x_min: float, x_max: float, y_min: float, y_max: float, active_only: bool) -> list[str]:
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
        # sign_x_coord/sign_y_coord are text fields in this dataset, so a plain
        # >=/<= comparison is lexicographic string comparison, not numeric --
        # it silently drops real records whenever the range crosses a digit-count
        # or leading-digit boundary. Cast explicitly to number to compare for real.
        f"sign_x_coord::number >= {x_min:.0f}",
        f"sign_x_coord::number <= {x_max:.0f}",
        f"sign_y_coord::number >= {y_min:.0f}",
        f"sign_y_coord::number <= {y_max:.0f}",
    ]
    if active_only:
        where_parts.append("record_type != 'Historical'")
    return where_parts


def output_filename(label: str, include_historical: bool) -> str:
    suffix = "_history" if include_historical else ""
    return f"signs_zip_{label}{suffix}.csv"


def normalize_records(raw: list[dict], to_wgs: Transformer) -> pd.DataFrame:
    """Turn raw SIMS JSON records into the output DataFrame: numeric
    sign_x_coord/sign_y_coord, latitude/longitude derived from them by
    reprojecting EPSG:2263 -> WGS84, and only the COLS columns.

    Shared with 01_query_sims_by_community_board.py, which selects its
    records by district polygon instead of ZIP but needs the same
    downstream shape."""
    df = pd.DataFrame(raw)
    if df.empty:
        return df

    df["sign_x_coord"] = pd.to_numeric(df["sign_x_coord"], errors="coerce")
    df["sign_y_coord"] = pd.to_numeric(df["sign_y_coord"], errors="coerce")
    mask = df["sign_x_coord"].notna() & df["sign_y_coord"].notna()
    lons, lats = to_wgs.transform(
        df.loc[mask, "sign_x_coord"].values, df.loc[mask, "sign_y_coord"].values
    )
    df.loc[mask, "longitude"] = lons
    df.loc[mask, "latitude"] = lats

    cols = [c for c in COLS if c in df.columns]
    return df[cols].copy()


def query_zip_area(
    zip_code: str,
    to_sp: Transformer,
    to_wgs: Transformer,
    nomi: pgeocode.Nominatim,
    active_only: bool = ACTIVE_ONLY,
) -> pd.DataFrame:
    zip_info = nomi.query_postal_code(zip_code)
    if pd.isna(zip_info.latitude):
        raise SystemExit(f"ZIP code {zip_code} not found. Check the code and try again.")

    lat, lon = zip_info.latitude, zip_info.longitude
    print(f"ZIP {zip_code}: {zip_info.place_name} ({lat:.4f}, {lon:.4f})")

    cx, cy = to_sp.transform(lon, lat)
    x_min, x_max = cx - RADIUS_FEET, cx + RADIUS_FEET
    y_min, y_max = cy - RADIUS_FEET, cy + RADIUS_FEET

    where_parts = build_where_parts(x_min, x_max, y_min, y_max, active_only)

    params = {
        "$where": " AND ".join(where_parts),
        "$limit": LIMIT,
        "$order": "order_number ASC",
    }

    print(f"Querying NYC Open Data for ZIP {zip_code}...")
    resp = requests.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    raw = resp.json()
    print(f"  Records returned: {len(raw)}")

    return normalize_records(raw, to_wgs)


def main(zip_codes: list[str], include_historical: bool = False):
    to_sp = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)
    nomi = pgeocode.Nominatim("us")

    active_only = not include_historical
    frames = [query_zip_area(z, to_sp, to_wgs, nomi, active_only=active_only) for z in zip_codes]
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        raise SystemExit("No results across the given ZIP code(s). Try different ZIP codes.")

    # Full-row dedup only -- order_number is NOT a unique sign key (one order
    # commonly covers several distinct signs at a corner, all sharing the same
    # order_number). A subset=["order_number"] dedup would silently discard
    # those as "duplicates". Only exact-duplicate rows (the same sign record
    # returned twice because two ZIPs' bounding boxes overlap) get dropped here.
    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        print(f"Removed {before - len(df)} exact-duplicate record(s) from overlapping ZIP areas.")

    label = "_".join(zip_codes)
    out_path = output_filename(label, include_historical)
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} records to {out_path}")
    if include_historical:
        print("Next: run 04_detect_replacement_history.py on the same ZIP code(s).")
    else:
        print("Next: run 02_generate_signs_data.py on the same ZIP code(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_codes", nargs="+", help="ZIP code(s) to query")
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Keep Historical (replaced/voided) records too, for replacement-history detection.",
    )
    args = parser.parse_args()
    main(args.zip_codes, include_historical=args.include_historical)
