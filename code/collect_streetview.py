#!/usr/bin/env python3
"""Collect Google Street View metadata and pilot images.

Usage:
    export GOOGLE_MAPS_API_KEY="your_key"
    python code/collect_streetview.py data/candidate_locations.csv

Input CSV columns:
    location_id,location

The location value can be either an address or "lat,lng".
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"

IMAGE_SIZE = "640x640"
DEFAULT_IMAGE_HEADINGS = "0,45,90,135,180,225,270,315"
DEFAULT_IMAGE_FOV = "70"
DEFAULT_IMAGE_PITCH = "10"


def request_json(url: str) -> dict:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, output_path: Path) -> None:
    with urlopen(url, timeout=20) as response:
        output_path.write_bytes(response.read())


def build_url(base_url: str, params: dict[str, str]) -> str:
    return f"{base_url}?{urlencode(params)}"


def get_headings() -> list[str]:
    raw_headings = os.environ.get("STREETVIEW_HEADINGS", DEFAULT_IMAGE_HEADINGS)
    return [heading.strip() for heading in raw_headings.split(",") if heading.strip()]


def get_image_setting(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python code/collect_streetview.py data/candidate_locations.csv")
        return 2

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Missing GOOGLE_MAPS_API_KEY environment variable.")
        return 2

    input_csv = Path(sys.argv[1])
    if not input_csv.exists():
        print(f"Input CSV not found: {input_csv}")
        return 2

    output_root = Path("data/streetview")
    image_dir = output_root / "images"
    output_root.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    metadata_csv = output_root / "metadata.csv"
    headings = get_headings()
    image_fov = get_image_setting("STREETVIEW_FOV", DEFAULT_IMAGE_FOV)
    image_pitch = get_image_setting("STREETVIEW_PITCH", DEFAULT_IMAGE_PITCH)

    with input_csv.open(newline="", encoding="utf-8") as source_file, metadata_csv.open(
        "w", newline="", encoding="utf-8"
    ) as metadata_file:
        reader = csv.DictReader(source_file)
        fieldnames = [
            "location_id",
            "image_id",
            "request_location",
            "heading",
            "metadata_status",
            "matched_latitude",
            "matched_longitude",
            "pano_id",
            "image_date",
            "copyright",
            "image_path",
            "download_status",
            "download_error",
        ]
        writer = csv.DictWriter(metadata_file, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            location_id = row["location_id"].strip()
            request_location = row["location"].strip()
            print(f"{location_id}: checking metadata", flush=True)

            metadata_params = {
                "location": request_location,
                "key": api_key,
            }
            try:
                metadata = request_json(build_url(METADATA_URL, metadata_params))
                status = metadata.get("status", "")
                metadata_error = ""
            except (HTTPError, URLError) as error:
                metadata = {}
                status = "ERROR"
                metadata_error = str(error)

            matched_location = metadata.get("location", {})
            for heading in headings:
                image_id = f"{location_id}_h{heading}"
                image_path = ""
                download_status = "not_requested"
                download_error = metadata_error
                if status == "OK":
                    image_path_obj = image_dir / f"{image_id}.jpg"
                    image_params = {
                        "size": IMAGE_SIZE,
                        "location": request_location,
                        "heading": heading,
                        "fov": image_fov,
                        "pitch": image_pitch,
                        "key": api_key,
                    }
                    try:
                        download_file(build_url(IMAGE_URL, image_params), image_path_obj)
                        image_path = str(image_path_obj)
                        download_status = "OK"
                    except HTTPError as error:
                        download_status = "ERROR"
                        download_error = f"HTTP {error.code}: {error.reason}"
                    except URLError as error:
                        download_status = "ERROR"
                        download_error = str(error.reason)

                writer.writerow(
                    {
                        "location_id": location_id,
                        "image_id": image_id,
                        "request_location": request_location,
                        "heading": heading,
                        "metadata_status": status,
                        "matched_latitude": matched_location.get("lat", ""),
                        "matched_longitude": matched_location.get("lng", ""),
                        "pano_id": metadata.get("pano_id", ""),
                        "image_date": metadata.get("date", ""),
                        "copyright": metadata.get("copyright", ""),
                        "image_path": image_path,
                        "download_status": download_status,
                        "download_error": download_error,
                    }
                )

                print(f"{image_id}: metadata={status}, download={download_status}", flush=True)

    print(f"Saved metadata to {metadata_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
