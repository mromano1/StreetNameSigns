"""Shared client for authenticating against and fetching images from
Cyclomedia's Atlas API. Used by verify_cyclomedia_fetch.py and
fetch_damaged_panoramas.py so the endpoint/auth logic lives in one place.

Endpoints and parameters below are taken from Cyclomedia's official Atlas API
reference docs (docs.cyclomedia.com/Atlas/2020/Atlas WFS Recordings
Service.pdf and .../Atlas Panorama Rendering Service.pdf), not guessed. Both
services require HTTP Basic Auth (CYCLOMEDIA_USERNAME/PASSWORD); the
Panorama Rendering Service additionally requires a CYCLOMEDIA_API_KEY query
param. This has not yet been exercised against the live service with real
credentials -- CYCLOMEDIA_PASSWORD is still blank in .env as of 2026-07-22.
"""
import os
import re
from datetime import datetime

import requests

ATLAS_WFS_URL = "https://atlasapi.cyclomedia.com/api/recording/wfs"
ATLAS_RENDER_URL = "https://atlasapi.cyclomedia.com/api/panoramarendering/Render/{recording_id}/"

# UNVERIFIED: the actual per-recording date field name in the WFS response
# has never been observed against the live API (CYCLOMEDIA_PASSWORD is still
# blank). "expiredAt" is a guess based on it being the only date-shaped field
# referenced anywhere in this codebase so far -- confirm via a live spike
# (print a feature's full raw `properties` dict) before trusting this at
# scale, and fix in this one place if it's wrong.
RECORDING_DATE_FIELD = "expiredAt"

# Compass-quadrant -> approximate camera heading (degrees, 0=North), for
# aiming an unattended fetch with no human to point the camera. Ported from
# the capture extension's compassGuessFromHeading()/COMPASS_8
# (extension/content.js) -- same 8-point mapping, just used in reverse (given
# a corner's compass label, what heading points toward it, rather than given
# a heading, which corner is ahead).
COMPASS_TO_HEADING = {
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0,
    "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0,
}


class CyclomediaError(Exception):
    """Raised when the Atlas API returns a non-200 response, or no recording
    is found near the requested point."""


def _auth():
    username = os.getenv("CYCLOMEDIA_USERNAME")
    password = os.getenv("CYCLOMEDIA_PASSWORD")
    if not username or not password:
        raise CyclomediaError(
            "CYCLOMEDIA_USERNAME/CYCLOMEDIA_PASSWORD not set -- make sure "
            "ML Project/.env exists and load_dotenv() has been called."
        )
    return (username, password)


def _api_key():
    api_key = os.getenv("CYCLOMEDIA_API_KEY")
    if not api_key:
        raise CyclomediaError(
            "CYCLOMEDIA_API_KEY not set -- make sure ML Project/.env exists "
            "and load_dotenv() has been called."
        )
    return api_key


def _feature_coords(feature):
    """Returns (lon, lat) from a GeoJSON feature's geometry, or None if
    absent (some fixtures/features carry no geometry)."""
    coords = (feature.get("geometry") or {}).get("coordinates")
    if not coords:
        return None
    return coords[0], coords[1]


def _feature_distance_sq(feature, lat, lon):
    coords = _feature_coords(feature)
    if coords is None:
        return float("inf")
    flon, flat = coords
    return (flat - lat) ** 2 + (flon - lon) ** 2


def _feature_image_id(feature):
    return feature["properties"].get("imageId") or feature.get("id")


def find_nearest_recording(lat, lon, radius_deg=0.001, timeout=30):
    """Queries the Atlas Recordings WFS (version 1.1.0) for the recording
    nearest (lat, lon), via an OGC Filter BBOX in EPSG:4326, excluding
    expired recordings. Returns the recording's imageId (str), or None if
    nothing is within radius_deg. Picks the closest feature by geometry, not
    just whatever the API lists first -- the WFS response order is not
    documented as distance-sorted."""
    bbox_filter = (
        "<Filter><And>"
        "<BBOX><gml:Envelope srsName='EPSG:4326'>"
        f"<gml:lowerCorner>{lon - radius_deg} {lat - radius_deg}</gml:lowerCorner>"
        f"<gml:upperCorner>{lon + radius_deg} {lat + radius_deg}</gml:upperCorner>"
        "</gml:Envelope></BBOX>"
        "<PropertyIsNull><PropertyName>expiredAt</PropertyName></PropertyIsNull>"
        "</And></Filter>"
    )
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": "atlas:Recording",
        "srsName": "EPSG:4326",
        "filter": bbox_filter,
        "outputFormat": "application/json",
    }
    resp = requests.get(ATLAS_WFS_URL, params=params, auth=_auth(), timeout=timeout)
    if resp.status_code != 200:
        raise CyclomediaError(f"WFS lookup failed: {resp.status_code} {resp.text[:300]}")

    features = resp.json().get("features", [])
    if not features:
        return None
    nearest = min(features, key=lambda f: _feature_distance_sq(f, lat, lon))
    return _feature_image_id(nearest)


def find_nearest_recording_at_date(lat, lon, before_date, radius_deg=0.001, timeout=30):
    """Like find_nearest_recording, but for a historical recording dated on
    or before `before_date` (a datetime.date) -- deliberately does NOT
    exclude expired recordings, since that's the whole point. Among
    recordings dated on/before the cutoff, picks the latest date (closest to
    the cutoff), breaking ties by distance. Returns None if the WFS returns
    no feature with a usable, sufficiently-old date.

    RECORDING_DATE_FIELD is unverified (see module-level comment) -- this
    function is not safe to trust at scale until a live spike confirms it."""
    bbox_filter = (
        "<Filter>"
        "<BBOX><gml:Envelope srsName='EPSG:4326'>"
        f"<gml:lowerCorner>{lon - radius_deg} {lat - radius_deg}</gml:lowerCorner>"
        f"<gml:upperCorner>{lon + radius_deg} {lat + radius_deg}</gml:upperCorner>"
        "</gml:Envelope></BBOX>"
        "</Filter>"
    )
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": "atlas:Recording",
        "srsName": "EPSG:4326",
        "filter": bbox_filter,
        "outputFormat": "application/json",
    }
    resp = requests.get(ATLAS_WFS_URL, params=params, auth=_auth(), timeout=timeout)
    if resp.status_code != 200:
        raise CyclomediaError(f"WFS lookup failed: {resp.status_code} {resp.text[:300]}")

    candidates = []
    for feature in resp.json().get("features", []):
        raw_date = feature.get("properties", {}).get(RECORDING_DATE_FIELD)
        if not raw_date:
            continue
        recorded = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
        if recorded <= before_date:
            candidates.append((recorded, feature))

    if not candidates:
        return None

    _, best_feature = max(
        candidates, key=lambda pair: (pair[0], -_feature_distance_sq(pair[1], lat, lon))
    )
    return _feature_image_id(best_feature)


def render_recording(recording_id, heading, width=1600, height=1200, fov=75, timeout=30):
    """Renders a rectilinear (non-panoramic) image from a known Cyclomedia
    `recording_id`, looking in the given compass `heading` (degrees, 0=North,
    via the Render operation's `yaw` + `srsName=EPSG:4326`). Raises
    CyclomediaError on any failure, with the raw response body included so a
    401/404 can be diagnosed. Returns raw JPEG bytes on success."""
    url = ATLAS_RENDER_URL.format(recording_id=recording_id)
    params = {
        "width": width,
        "height": height,
        "srsName": "EPSG:4326",
        "yaw": heading,
        "hfov": fov,
        "apiKey": _api_key(),
    }
    resp = requests.get(url, params=params, auth=_auth(), timeout=timeout)
    if resp.status_code != 200:
        raise CyclomediaError(
            f"Image fetch failed for recording {recording_id}: {resp.status_code} {resp.text[:300]}"
        )
    return resp.content


def fetch_cyclomedia_image(lat, lon, heading, width=1600, height=1200, fov=75, timeout=30):
    """Fetches a rectilinear image from the Cyclomedia recording nearest
    (lat, lon). Thin convenience wrapper combining find_nearest_recording +
    render_recording for callers that don't need to reuse one recording
    lookup across multiple renders."""
    recording_id = find_nearest_recording(lat, lon, timeout=timeout)
    if recording_id is None:
        raise CyclomediaError(f"No Cyclomedia recording found near ({lat}, {lon}).")
    return render_recording(recording_id, heading, width, height, fov, timeout)


def compass_from_sign_location(sign_location):
    """Ports extension/content.js's compassFromSignLocation(): classifies a
    SIMS sign_location string into one of the 8 compass corners, or None if
    it's a median/mall/apex/offset placement rather than a real corner. See
    the JS version's comment for the NYC DOT sign_location vocabulary this
    is based on."""
    s = (sign_location or "").strip().upper()
    m = re.match(r"^([NS])/([EW])\s*C(URB)?\b", s)
    if m:
        return m.group(1) + m.group(2)
    m = re.match(r"^([NSEW])\s*C(URB)?\b", s)
    if m:
        return m.group(1)
    return None


def heading_candidates_for_corner(sign_location):
    """Approximate camera heading (degrees) to point toward a sign given its
    SIMS sign_location, for an unattended fetch with no human aiming the
    camera. This is a known accuracy limitation (a quadrant-level guess, not
    a computed bearing) -- pair with a wide hfov in render_recording/
    fetch_cyclomedia_image to absorb the imprecision. Returns None when
    sign_location isn't a classifiable corner (see compass_from_sign_location)."""
    compass = compass_from_sign_location(sign_location)
    if compass is None:
        return None
    return COMPASS_TO_HEADING[compass]
