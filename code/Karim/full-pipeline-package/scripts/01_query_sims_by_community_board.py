"""
Query NYC Open Data's Street Sign Work Orders dataset for one NYC Community
Board (Community District) and save the filtered street-name-sign records to
a CSV. Standalone script, no Jupyter or AI assistant required.

Same pipeline stage as 01_query_sims_by_zip.py -- same dataset, same WHERE
filters (build_where_parts), same column set (COLS) -- just a different way
of choosing the area. Where the ZIP script pulls a fixed 1-mile-radius box
around a ZIP centroid, this one pulls the district's real boundary:

  1. Get the board's boundary polygon from NYC's Community Districts
     dataset (community_board_lookup.py, shared cache with the report
     scripts).
  2. Reproject it to EPSG:2263 and query SIMS for its bounding box -- a
     first pass, since Socrata can't do point-in-polygon for us.
  3. Drop every record whose (lat, lon) falls in the bbox but outside the
     district itself. Community districts are not rectangles, so the bbox
     overshoots into neighbouring boards and this second pass is required,
     not cosmetic.

Usage:
    python 01_query_sims_by_community_board.py 304
    python 01_query_sims_by_community_board.py Brooklyn CD 4
    python 01_query_sims_by_community_board.py "Brooklyn CD 4"
    python 01_query_sims_by_community_board.py --include-historical 304

Either identifier form works: the raw boro_cd code from the boundary
dataset ("304" = borough 3 (Brooklyn) + district 04) or the human-readable
label ("Brooklyn CD 4", case- and "CD"-optional). See
community_board_lookup.resolve_boro_cd.

Pass --include-historical to keep Historical (replaced/voided) records too,
writing to a separate *_history.csv, exactly as the ZIP script does.

Output:
    signs_zip_cb304.csv                (Brooklyn CD 4)
    signs_zip_cb304_history.csv        (--include-historical)

The signs_zip_ prefix is deliberate: 02_generate_signs_data.py builds its
input path as signs_zip_<label>.csv, so naming the label "cb304" lets that
script consume this output unmodified:

    python 02_generate_signs_data.py cb304
"""
import argparse
import os
import sys
import warnings
from pathlib import Path

import pandas as pd
import requests
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import transform as transform_geometry
from shapely.prepared import prep

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import community_board_lookup as cbl  # noqa: E402

warnings.filterwarnings("ignore")


def _load_zip_script():
    """01_query_sims_by_zip.py can't be imported by name (the filename
    starts with a digit), so load it by path -- the same importlib pattern
    its own test file uses. This script reuses its API_URL, COLS,
    build_where_parts, output_filename and normalize_records so the two
    area-selection methods can't drift apart."""
    import importlib.util

    module_path = SCRIPT_DIR / "01_query_sims_by_zip.py"
    spec = importlib.util.spec_from_file_location("query_sims_by_zip", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qsz = _load_zip_script()

API_URL = qsz.API_URL
COLS = qsz.COLS
ACTIVE_ONLY = qsz.ACTIVE_ONLY
PAGE_LIMIT = qsz.LIMIT  # 5000, Socrata's default page size for this dataset

# Shared with report_physical.py's community-board lookup -- one cached copy
# of the boundary GeoJSON for the whole project.
COMMUNITY_BOARD_CACHE_PATH = SCRIPT_DIR.parent / "data" / "community_districts.geojson"

# Env var names checked for an optional Socrata app token. Anonymous requests
# work (this dataset needs no auth) but are throttled harder, so a token is a
# nice-to-have, not a requirement.
APP_TOKEN_ENV_VARS = ("SOCRATA_APP_TOKEN", "NYC_OPEN_DATA_APP_TOKEN")


def board_output_label(boro_cd: str) -> str:
    """"304" -> "cb304". Keeps the CSV label short enough to hand to
    02_generate_signs_data.py as-is, and prefixed so it can't be confused
    with a ZIP code."""
    return f"cb{boro_cd}"


def output_filename(boro_cd: str, include_historical: bool) -> str:
    """Delegates to the ZIP script's filename builder so both stages share
    one naming rule."""
    return qsz.output_filename(board_output_label(boro_cd), include_historical)


def app_token_headers(env=None) -> dict:
    """Returns {"X-App-Token": ...} if a Socrata app token is configured in
    the environment, else {}. Requests without one still succeed against
    this dataset; a token just raises the throttling ceiling."""
    env = os.environ if env is None else env
    for name in APP_TOKEN_ENV_VARS:
        token = (env.get(name) or "").strip()
        if token:
            return {"X-App-Token": token}
    return {}


def board_bbox_2263(polygon, to_sp: Transformer) -> tuple[float, float, float, float]:
    """Reprojects a WGS84 board polygon to EPSG:2263 (State Plane feet) and
    returns its bounding box as (x_min, x_max, y_min, y_max) -- the argument
    order build_where_parts expects.

    Reprojects the whole polygon rather than just its lat/lon bbox corners,
    so the returned box provably contains every district vertex even though
    the projection isn't axis-aligned with WGS84."""
    projected = transform_geometry(lambda x, y: to_sp.transform(x, y), polygon)
    x_min, y_min, x_max, y_max = projected.bounds
    return x_min, x_max, y_min, y_max


def filter_points_in_polygon(df: pd.DataFrame, polygon) -> pd.DataFrame:
    """Second pass: keep only rows whose (latitude, longitude) falls inside
    the board polygon. Rows with missing/unparseable coordinates are
    dropped -- without a location there's no way to attribute a sign to a
    district."""
    if df.empty:
        return df

    lats = pd.to_numeric(df["latitude"], errors="coerce")
    lons = pd.to_numeric(df["longitude"], errors="coerce")
    has_coords = lats.notna() & lons.notna()

    prepared = prep(polygon)  # prepared geometry: much faster for many points
    inside = pd.Series(False, index=df.index)
    inside.loc[has_coords] = [
        prepared.contains(Point(lon, lat))
        for lon, lat in zip(lons[has_coords], lats[has_coords])
    ]
    return df[inside].copy()


def fetch_all_records(where: str, headers: dict = None, page_limit: int = None) -> list[dict]:
    """Pages through the SIMS API until a short page arrives, returning all
    records. A community district's bounding box can hold more signs than
    one page holds (Brooklyn CD 4's box returned 3,278 -- larger districts
    exceed the 5,000 page size), and a single un-paged request would
    silently truncate the district.

    Orders by :id -- Socrata's stable row identifier -- because
    order_number is not unique in this dataset, and paging over a
    non-unique sort key can repeat or skip rows between pages."""
    page_limit = page_limit or PAGE_LIMIT
    records: list[dict] = []
    offset = 0

    while True:
        params = {
            "$where": where,
            "$limit": page_limit,
            "$offset": offset,
            "$order": ":id",
        }
        resp = requests.get(API_URL, params=params, headers=headers or {}, timeout=60)
        resp.raise_for_status()
        page = resp.json()
        records.extend(page)
        if len(page) < page_limit:
            return records
        offset += page_limit
        print(f"  Fetched {len(records)} records so far, requesting next page...")


def query_community_board(
    polygon,
    to_sp: Transformer,
    to_wgs: Transformer,
    active_only: bool = ACTIVE_ONLY,
    headers: dict = None,
) -> pd.DataFrame:
    """Runs the bbox query for a board polygon, then trims the result down
    to the polygon itself. Returns a DataFrame with the same columns the
    ZIP script produces."""
    x_min, x_max, y_min, y_max = board_bbox_2263(polygon, to_sp)
    print(
        f"District bounding box (EPSG:2263): "
        f"x {x_min:.0f}-{x_max:.0f}, y {y_min:.0f}-{y_max:.0f}"
    )

    where = " AND ".join(qsz.build_where_parts(x_min, x_max, y_min, y_max, active_only))

    print("Querying NYC Open Data...")
    raw = fetch_all_records(where, headers=headers)
    print(f"  Records in bounding box: {len(raw)}")

    df = qsz.normalize_records(raw, to_wgs)
    if df.empty:
        return df

    before = len(df)
    df = filter_points_in_polygon(df, polygon)
    print(f"  Inside the district itself: {len(df)} ({before - len(df)} dropped as outside)")
    return df


def main(board: str, include_historical: bool = False, cache_path=COMMUNITY_BOARD_CACHE_PATH):
    boro_cd = cbl.resolve_boro_cd(board)
    if not boro_cd:
        raise SystemExit(
            f"Could not read '{board}' as a Community Board. Pass a boro_cd code "
            f"like 304, or a label like \"Brooklyn CD 4\"."
        )

    label = cbl.boro_cd_to_label(boro_cd)
    print(f"Community Board: {label} (boro_cd {boro_cd})")

    polygon = cbl.load_community_board_polygon(cache_path, boro_cd)
    if polygon is None:
        raise SystemExit(
            f"boro_cd {boro_cd} is not in the Community Districts boundary dataset."
        )

    to_sp = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)

    headers = app_token_headers()
    if headers:
        print("Using the Socrata app token from the environment.")

    df = query_community_board(
        polygon,
        to_sp,
        to_wgs,
        active_only=not include_historical,
        headers=headers,
    )
    if df.empty:
        raise SystemExit(f"No street name sign records found inside {label}.")

    # Full-row dedup only, for the same reason as the ZIP script: one
    # order_number can legitimately cover several distinct signs at a corner.
    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        print(f"Removed {before - len(df)} exact-duplicate record(s).")

    out_path = output_filename(boro_cd, include_historical)
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} records to {out_path}")
    if include_historical:
        print(f"Next: run 04_detect_replacement_history.py against {out_path}.")
    else:
        print(f"Next: run 02_generate_signs_data.py {board_output_label(boro_cd)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Query SIMS street name signs for one NYC Community Board."
    )
    parser.add_argument(
        "board",
        nargs="+",
        help='Community Board: a boro_cd code (304) or a label ("Brooklyn CD 4").',
    )
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Keep Historical (replaced/voided) records too, for replacement-history detection.",
    )
    args = parser.parse_args()
    main(" ".join(args.board), include_historical=args.include_historical)
