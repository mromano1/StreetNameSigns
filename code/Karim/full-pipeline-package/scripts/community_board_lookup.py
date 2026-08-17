"""
Looks up the NYC Community Board (Community District) label for a given
lat/lon, via NYC Open Data's Community Districts boundary dataset.

Data source (verified live 2026-08-11):
https://data.cityofnewyork.us/resource/5crt-au7u.geojson -- Socrata
dataset 5crt-au7u, 71 features. Each feature has a `boro_cd` string
property like "410": the first digit is the borough (1=Manhattan,
2=Bronx, 3=Brooklyn, 4=Queens, 5=Staten Island), the remaining two digits
are the community district number. Geometries are WGS84 (lat/lon),
matching this project's manifest latitude/longitude fields directly --
no reprojection needed for the join.

A handful of boro_cd codes (e.g. "480"-"484", "595") are Joint Interest
Areas (parks/airports), not real community districts -- these have
district numbers above any borough's real CD range (see MAX_REAL_CD) and
render as "<Borough> JIA" without a number, since street signs are not
expected to fall inside a park/airport polygon.
"""
import json
import re
from pathlib import Path

import requests
from shapely.geometry import Point, shape
from shapely.ops import unary_union

COMMUNITY_DISTRICTS_URL = (
    "https://data.cityofnewyork.us/resource/5crt-au7u.geojson?$limit=200"
)

BOROUGH_NAMES = {
    "1": "Manhattan",
    "2": "Bronx",
    "3": "Brooklyn",
    "4": "Queens",
    "5": "Staten Island",
}

# Highest real community district number per borough, used to tell a real
# CD apart from a Joint Interest Area code sharing the same boro_cd range.
MAX_REAL_CD = {"1": 12, "2": 12, "3": 18, "4": 14, "5": 3}


def boro_cd_to_label(boro_cd):
    """"105" -> "Manhattan CD 5". "483" -> "Queens JIA" (83 exceeds
    Queens' max real CD of 14). Returns "" for missing/unrecognized
    input."""
    boro_cd = (boro_cd or "").strip()
    if len(boro_cd) < 2:
        return ""
    borough_digit, district_str = boro_cd[0], boro_cd[1:]
    borough_name = BOROUGH_NAMES.get(borough_digit)
    if borough_name is None:
        return ""
    district_num = int(district_str)
    if district_num > MAX_REAL_CD[borough_digit]:
        return f"{borough_name} JIA"
    return f"{borough_name} CD {district_num}"


BOROUGH_DIGITS = {name.lower(): digit for digit, name in BOROUGH_NAMES.items()}

# "Brooklyn CD 4", "brooklyn cd4", "Staten Island 3" -- borough name, an
# optional "CD" keyword, then the district number.
_LABEL_PATTERN = re.compile(r"^(?P<borough>[a-z ]+?)\s*(?:cd\s*)?(?P<district>\d{1,2})$")


def label_to_boro_cd(label):
    """"Brooklyn CD 4" -> "304". The reverse of boro_cd_to_label, for
    going from a human-readable board name back to the dataset's boro_cd
    key. Case- and whitespace-insensitive, and the "CD" keyword is
    optional ("Staten Island 3" works).

    Returns "" for anything unrecognized, including a district number
    above the borough's real CD range and a "<Borough> JIA" label (each
    borough has several Joint Interest Area polygons, so a JIA label has
    no unique boro_cd to reverse to -- pass the raw code instead)."""
    text = " ".join((label or "").split()).lower()
    match = _LABEL_PATTERN.match(text)
    if match is None:
        return ""
    borough_digit = BOROUGH_DIGITS.get(match.group("borough").strip())
    if borough_digit is None:
        return ""
    district_num = int(match.group("district"))
    if not 1 <= district_num <= MAX_REAL_CD[borough_digit]:
        return ""
    return f"{borough_digit}{district_num:02d}"


def resolve_boro_cd(board):
    """Normalizes either input form a caller might have to the dataset's
    boro_cd key: a raw code ("304", or "34" -> zero-padded to "304") or a
    label ("Brooklyn CD 4"). Returns "" if neither form resolves.

    Raw codes are accepted even when they name a Joint Interest Area
    ("483"), since a code is unambiguous where its label is not."""
    text = " ".join((board or "").split())
    if text.isdigit():
        if len(text) < 2:
            return ""
        canonical = f"{text[0]}{int(text[1:]):02d}"
        return canonical if boro_cd_to_label(canonical) else ""
    return label_to_boro_cd(text)


def fetch_community_districts_geojson(cache_path):
    """Returns the parsed GeoJSON FeatureCollection dict. Uses cache_path
    on disk if it already exists; otherwise fetches from
    COMMUNITY_DISTRICTS_URL and writes the cache for next time."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    resp = requests.get(COMMUNITY_DISTRICTS_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def build_community_board_index(geojson):
    """geojson: a FeatureCollection dict. Returns a list of (shapely
    geometry, label) pairs for lookup_community_board. Features whose
    boro_cd doesn't resolve to a label (see boro_cd_to_label) are
    skipped."""
    index = []
    for feature in geojson.get("features", []):
        label = boro_cd_to_label(feature.get("properties", {}).get("boro_cd", ""))
        if not label:
            continue
        index.append((shape(feature["geometry"]), label))
    return index


def lookup_community_board(lat, lon, index):
    """Returns the label of the first indexed polygon containing (lat,
    lon), or "" if none matches."""
    point = Point(lon, lat)  # shapely geometry is (x, y) = (lon, lat)
    for polygon, label in index:
        if polygon.contains(point):
            return label
    return ""


def load_community_board_index(cache_path):
    """Convenience: fetch/cache the GeoJSON, then build the lookup
    index, in one call."""
    geojson = fetch_community_districts_geojson(cache_path)
    return build_community_board_index(geojson)


def build_community_board_polygon(geojson, board):
    """The reverse of build_community_board_index/lookup_community_board:
    given a board (raw boro_cd or label, see resolve_boro_cd), returns the
    shapely geometry of that board's boundary, or None if the board can't
    be resolved or isn't in the FeatureCollection.

    Geometry is WGS84 (lon, lat), as it comes from the source dataset --
    reproject at the call site if you need State Plane. Features sharing a
    boro_cd are unioned, so the return value is always a single geometry."""
    boro_cd = resolve_boro_cd(board)
    if not boro_cd:
        return None
    geoms = [
        shape(feature["geometry"])
        for feature in geojson.get("features", [])
        if (feature.get("properties", {}).get("boro_cd") or "").strip() == boro_cd
    ]
    if not geoms:
        return None
    if len(geoms) == 1:
        return geoms[0]
    return unary_union(geoms)


def load_community_board_polygon(cache_path, board):
    """Convenience: fetch/cache the GeoJSON (sharing the same cache file
    as load_community_board_index), then pull one board's polygon out of
    it, in one call."""
    geojson = fetch_community_districts_geojson(cache_path)
    return build_community_board_polygon(geojson, board)
