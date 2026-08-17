"""
Bulk-fetches Cyclomedia panoramas for every corner known to the pipeline:
one "latest" shot per corner in signs_data.json, and one "prior_to_replacement"
shot per sign thread in signs_history_*.json that has a detected
prior-to-replacement record (see StreetNameSigns/code/Karim/scripts/
04_detect_replacement_history.py).

Heading is a v1 approximation only -- compass-quadrant-derived via
cyclomedia_client.heading_candidates_for_corner(), not a computed bearing.
Pair with a wide hfov (see render_recording's default) to absorb the
imprecision; this is a known limitation, not a bug, per the design doc.

Cyclomedia fetch failures (auth error, 404, no recording found) are recorded
per-job in fetch_manifest.json rather than raising, so one bad corner doesn't
lose the rest of the run. Already-fetched images are skipped on re-run (same
output path = same job), so this script is safe to re-run after a partial
failure without burning extra API calls on corners already done.

This is the annotation tool's input: fetch_manifest.json lists every
attempted job and its outcome (status: ok/failed/skipped), with `path`
relative to the output directory for successful fetches.

Usage:
    python fetch_cyclomedia_panoramas.py signs_data.json [signs_history.json]
    python fetch_cyclomedia_panoramas.py signs_data.json --limit 50
    python fetch_cyclomedia_panoramas.py signs_data.json --output-dir some/dir --limit 50
    python fetch_cyclomedia_panoramas.py signs_data.json --multi-angle

--multi-angle additionally clusters this board's corners into intersections
and fetches one "center" shot plus one "side" shot per adjacent corner
pair, on top of the existing one-per-corner fetch -- roughly doubles API
calls/runtime for a typical 4-way intersection. Off by default.

--limit N caps the run to the first N planned jobs (in signs_data.json's
corner order) -- for a quick/cheap demo pull instead of a full board,
which can be hundreds of real Cyclomedia API calls. Not a random or
representative sample, just "the first N" -- good enough for a demo,
not for judging coverage.
"""
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import cyclomedia_client as cc
import geo_clustering

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parent / "data" / "cyclomedia_panoramas"

DEFAULT_HEADING = 0.0  # fallback when no sign at a corner has a classifiable sign_location
WIDE_HFOV = 120  # wider than render_recording's 75-deg default, to absorb heading-guess imprecision

# Empirically measured (2026-08-14) against every real fetched board in this
# repo at the time: cb211->max 5, cb304->max 8, cb301->max 13, cb101->max 49
# corners per cluster. Confirmed reasonable at this scale -- see
# MAX_INTERSECTION_CLUSTER_SIZE below for what happens at the dense end,
# where single-linkage chaining stops representing real intersections.
INTERSECTION_CLUSTER_DISTANCE_FT = 250

# Empirically measured (2026-08-14, FINAL WHOLE-BRANCH REVIEW) real per-board
# max cluster sizes at the threshold above: cb211->5, cb304->8, cb301->13,
# cb101->49. 5-8 corners is a plausible complex real intersection (a wide
# multi-leg junction); 13+ is neighborhood-scale over-clustering from
# single-linkage chaining, not a real intersection -- cb101's 49-corner
# cluster is the crash case this cap exists to prevent. 10 sits in the gap
# between cb304 (kept) and cb301 (dropped), with a little headroom above the
# largest plausible case actually observed.
#
# Real coverage cost, not just a theoretical tradeoff: on cb101 (the
# densest board in this repo), dropping oversized clusters removes ~47% of
# its 349 corners (163 of them) from multi-angle capture entirely -- those
# dense blocks get no center/side shots at all, only their existing
# per-corner "latest" fetch. Each drop prints the corner_ids involved, so
# it's visible per-run, not silent. A denser board deserves real
# sub-clustering (e.g. splitting an oversized cluster by street segment)
# rather than a flat drop; that's deferred, not built here.
MAX_INTERSECTION_CLUSTER_SIZE = 10

# 2x render_recording's own 1600x1200 default -- confirmed live 2026-08-12
# that the Panorama Rendering Service serves real additional detail at this
# size (legible street signs/storefront text), not just an upscale; tested
# up to 4800x3600 (also succeeds) but 3200x2400 was chosen as the balance
# of detail vs. fetch time/storage across the full 3,605-corner run.
RENDER_WIDTH = 3200
RENDER_HEIGHT = 2400


def _centroid(corners: list[dict]) -> tuple[float, float]:
    xs = [c["x_2263"] for c in corners]
    ys = [c["y_2263"] for c in corners]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _bearing_deg(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """Compass bearing in degrees (0=North, 90=East) from one EPSG:2263
    point to another. atan2(dx, dy), not the usual atan2(dy, dx), because
    EPSG:2263's y-axis already increases northward, matching compass
    bearing directly."""
    dx = to_x - from_x
    dy = to_y - from_y
    return math.degrees(math.atan2(dx, dy)) % 360


def _sort_corners_by_bearing(corners: list[dict], center_x: float, center_y: float) -> list[dict]:
    return sorted(corners, key=lambda c: _bearing_deg(center_x, center_y, c["x_2263"], c["y_2263"]))


def _adjacent_pairs(sorted_corners: list[dict]) -> list[tuple[dict, dict]]:
    """Consecutive corners in bearing-sorted order, wrapping last-to-first
    -- perimeter-adjacent pairs ("sides"), never diagonals. Special-cased
    for n<=2: naive (i, i+1 mod n) wrapping would produce the same
    physical segment twice for exactly 2 corners (A->B and B->A)."""
    n = len(sorted_corners)
    if n < 2:
        return []
    if n == 2:
        return [(sorted_corners[0], sorted_corners[1])]
    return [(sorted_corners[i], sorted_corners[(i + 1) % n]) for i in range(n)]


def cluster_corners_into_intersections(
    corners: list[dict], threshold_ft: float = INTERSECTION_CLUSTER_DISTANCE_FT
) -> list[list[dict]]:
    """Groups corners into intersections via geo_clustering.cluster_points_by_distance
    on each corner's (x_2263, y_2263). Returns only clusters of 2+ corners
    -- an isolated corner (no neighbor within threshold_ft) already gets
    its own "latest" job from build_fetch_jobs, so it's dropped here
    rather than producing a redundant single-corner cluster.

    Assumes no two corners share the exact same (x_2263, y_2263) -- true
    for real SIMS corner data, where distinct corners are always at
    distinct points -- since that coordinate pair is used as a lookup key
    to map clustered points back to their full corner dict.

    Clusters larger than MAX_INTERSECTION_CLUSTER_SIZE are dropped entirely
    (not truncated, not turned into a job) -- single-linkage clustering
    chains transitively, so a dense area of corners can merge into one
    neighborhood-scale cluster that isn't a real intersection at all (see
    MAX_INTERSECTION_CLUSTER_SIZE's own comment for the real board data this
    was measured against). Printed, not silent, so a run against a dense
    board still tells the operator what got skipped and why."""
    xy_to_corner = {(c["x_2263"], c["y_2263"]): c for c in corners}
    xy_points = list(xy_to_corner.keys())
    clusters_xy = geo_clustering.cluster_points_by_distance(xy_points, threshold_ft=threshold_ft)
    clusters = [
        [xy_to_corner[pt] for pt in cluster_xy]
        for cluster_xy in clusters_xy
        if len(cluster_xy) >= 2
    ]

    kept = []
    for cluster_corners in clusters:
        if len(cluster_corners) > MAX_INTERSECTION_CLUSTER_SIZE:
            dropped_ids = sorted(c["corner_id"] for c in cluster_corners)
            print(
                f"Dropping oversized intersection cluster: {len(dropped_ids)} corners "
                f"(> MAX_INTERSECTION_CLUSTER_SIZE={MAX_INTERSECTION_CLUSTER_SIZE}), "
                f"likely neighborhood-scale over-clustering, not a real intersection: "
                f"{dropped_ids}"
            )
        else:
            kept.append(cluster_corners)
    return kept


MAX_INTERSECTION_ID_LENGTH = 100  # see _intersection_id docstring


def _intersection_id(cluster_corners: list[dict]) -> str:
    """Deterministic id for a cluster: sorted corner_ids joined with "+".

    Defense-in-depth on top of cluster_corners_into_intersections's own
    MAX_INTERSECTION_CLUSTER_SIZE cap -- this is what actually becomes a
    directory name (job_relative_path), so it's bounded independently here
    too, in case a future cap increase (or some other path that hands
    build_intersection_jobs an oversized cluster directly) lets a long
    joined string through again. Above MAX_INTERSECTION_ID_LENGTH, falls
    back to "<first corner_id>_<8-hex-char sha1 of the full sorted list>" --
    short, deterministic (same cluster always produces the same id, so
    re-running the fetch resumes correctly), and collision-safe in
    practice. No information is lost: the full corner_ids list still lives
    on the job dict regardless of which form intersection_id takes."""
    sorted_ids = sorted(c["corner_id"] for c in cluster_corners)
    joined = "+".join(sorted_ids)
    if len(joined) <= MAX_INTERSECTION_ID_LENGTH:
        return joined
    digest = hashlib.sha1("+".join(sorted_ids).encode("utf-8")).hexdigest()[:8]
    return f"{sorted_ids[0]}_{digest}"


def _representative_heading(cluster_corners: list[dict]) -> float:
    """Same fallback pattern build_fetch_jobs already uses per-corner
    (first classifiable sign_location wins), scoped across every corner
    in the cluster instead of just one -- a v1 approximation, same
    documented-limitation spirit as this file's existing per-corner
    heading logic."""
    for corner in cluster_corners:
        for sign in corner.get("signs", []):
            candidate = cc.heading_candidates_for_corner(sign.get("sign_location"))
            if candidate is not None:
                return candidate
    return DEFAULT_HEADING


def build_intersection_jobs(clusters: list[list[dict]]) -> list[dict]:
    """Pure planning step: no network calls. clusters is the output of
    cluster_corners_into_intersections (each cluster already guaranteed
    2+ corners). Returns one "center" job plus one "side" job per
    perimeter-adjacent corner pair, for every cluster."""
    jobs = []
    for cluster_corners in clusters:
        center_x, center_y = _centroid(cluster_corners)
        center_lat, center_lon = geo_clustering.reproject_2263_to_lat_lon(center_x, center_y)
        intersection_id = _intersection_id(cluster_corners)
        corner_ids = sorted(c["corner_id"] for c in cluster_corners)
        heading = _representative_heading(cluster_corners)

        jobs.append({
            "image_kind": "center",
            "intersection_id": intersection_id,
            "corner_ids": corner_ids,
            "lat": center_lat,
            "lon": center_lon,
            "heading": heading,
        })

        sorted_corners = _sort_corners_by_bearing(cluster_corners, center_x, center_y)
        for corner_a, corner_b in _adjacent_pairs(sorted_corners):
            mid_x = (corner_a["x_2263"] + corner_b["x_2263"]) / 2
            mid_y = (corner_a["y_2263"] + corner_b["y_2263"]) / 2
            mid_lat, mid_lon = geo_clustering.reproject_2263_to_lat_lon(mid_x, mid_y)
            side_heading = _bearing_deg(mid_x, mid_y, center_x, center_y)
            side_corner_ids = tuple(sorted([corner_a["corner_id"], corner_b["corner_id"]]))
            jobs.append({
                "image_kind": "side",
                "intersection_id": intersection_id,
                "corner_ids": corner_ids,
                "side_corner_ids": side_corner_ids,
                "lat": mid_lat,
                "lon": mid_lon,
                "heading": side_heading,
            })
    return jobs


def build_fetch_jobs(signs_data: dict, signs_history: dict | None) -> list[dict]:
    """Pure planning step: no network calls. Returns one job per "latest"
    corner shot plus one job per thread with a valid prior_to_replacement
    record. Each job has enough info for run_job() to execute it
    independently."""
    jobs = []

    for corner in signs_data.get("corners", []):
        heading = DEFAULT_HEADING
        for sign in corner.get("signs", []):
            candidate = cc.heading_candidates_for_corner(sign.get("sign_location"))
            if candidate is not None:
                heading = candidate
                break
        jobs.append(
            {
                "image_kind": "latest",
                "corner_id": corner.get("corner_id"),
                "lat": corner["latitude"],
                "lon": corner["longitude"],
                "heading": heading,
            }
        )

    for thread in (signs_history or {}).get("threads", []):
        prior = thread.get("prior_to_replacement")
        if prior is None:
            continue
        current_date = datetime.fromisoformat(thread["current"]["order_completed_on_date"]).date()
        jobs.append(
            {
                "image_kind": "prior_to_replacement",
                "corner_id": thread.get("corner_id"),
                "lat": thread["lat_r"],
                "lon": thread["lon_r"],
                "heading": cc.heading_candidates_for_corner(thread.get("sign_location")) or DEFAULT_HEADING,
                "before_date": current_date,
                "sign_code": thread.get("sign_code"),
            }
        )

    return jobs


def job_relative_path(job: dict) -> Path:
    if job["image_kind"] == "center":
        return Path("intersections") / job["intersection_id"] / "center.jpg"
    if job["image_kind"] == "side":
        corner_a, corner_b = job["side_corner_ids"]
        return Path("intersections") / job["intersection_id"] / f"side_{corner_a}_{corner_b}.jpg"
    corner_label = job["corner_id"] or "unmatched"
    if job["image_kind"] == "prior_to_replacement":
        filename = f"prior_to_replacement_{job.get('sign_code', 'unknown')}.jpg"
    else:
        filename = "latest.jpg"
    return Path(corner_label) / filename


def run_job(job: dict, output_dir: Path) -> dict:
    """Executes one fetch job. Never raises -- failures are captured in the
    returned entry's status/error fields so a batch run can continue past a
    bad corner. Skips (without any network call) if the output file already
    exists, so re-running after a partial failure doesn't re-fetch
    already-completed jobs."""
    rel_path = job_relative_path(job)
    out_path = output_dir / rel_path

    entry = {**job, "path": str(rel_path)}

    if out_path.exists():
        return {**entry, "status": "skipped"}

    try:
        if job["image_kind"] == "prior_to_replacement":
            recording_id = cc.find_nearest_recording_at_date(
                job["lat"], job["lon"], before_date=job["before_date"]
            )
        else:
            recording_id = cc.find_nearest_recording(job["lat"], job["lon"])

        if recording_id is None:
            return {**entry, "status": "failed", "error": "No recording found near this location."}

        image_bytes = cc.render_recording(
            recording_id, job["heading"], width=RENDER_WIDTH, height=RENDER_HEIGHT, fov=WIDE_HFOV
        )
    except cc.CyclomediaError as e:
        return {**entry, "status": "failed", "error": str(e)}

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(image_bytes)
    except OSError as e:
        # e.g. a Windows long-path error from an intersection_id that's too
        # long -- MAX_INTERSECTION_ID_LENGTH/the cluster-size cap are meant
        # to prevent this, but this is the last line of defense so a batch
        # run over hundreds of jobs never crashes/loses its manifest over
        # one bad path (see this function's own "never raises" docstring).
        return {**entry, "status": "failed", "error": str(e)}
    return {**entry, "status": "ok", "recording_id": recording_id}


def main(
    signs_data_path: str,
    signs_history_path: str | None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    limit: int | None = None,
    multi_angle: bool = False,
):
    load_dotenv()
    with open(signs_data_path) as f:
        signs_data = json.load(f)
    signs_history = None
    if signs_history_path:
        with open(signs_history_path) as f:
            signs_history = json.load(f)

    jobs = build_fetch_jobs(signs_data, signs_history)
    if multi_angle:
        clusters = cluster_corners_into_intersections(signs_data.get("corners", []))
        jobs += build_intersection_jobs(clusters)
    # --limit caps the FULL combined job list (corner jobs + intersection
    # jobs, in that order), not just the corner jobs -- so --limit N with
    # --multi-angle never exceeds N total API calls. A small --limit will
    # therefore drop intersection jobs entirely (they're appended after
    # the per-corner jobs); that's the safer default for cost control,
    # matching --limit's own "cheap demo pull" purpose.
    if limit is not None:
        jobs = jobs[:limit]
    print(f"Planned {len(jobs)} fetch job(s).")

    results = [run_job(job, output_dir) for job in jobs]

    counts = {"ok": 0, "failed": 0, "skipped": 0}
    for r in results:
        counts[r["status"]] += 1
    print(f"Done: {counts['ok']} fetched, {counts['skipped']} skipped (already had), {counts['failed']} failed.")

    manifest_path = output_dir / "fetch_manifest.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump({"jobs": results}, f, indent=2)
    print(f"Wrote {manifest_path}")


def parse_cli_args(args):
    """args: sys.argv[1:]-shaped list. Returns (signs_data_path,
    signs_history_path, output_dir, limit, multi_angle) -- output_dir/limit
    are None when their flag wasn't passed, so main() falls back to
    DEFAULT_OUTPUT_DIR / no cap; multi_angle is False unless --multi-angle
    was passed. Raises SystemExit for missing signs_data_path, a flag with
    nothing after it, or a non-integer --limit value."""
    if "--output-dir" in args:
        idx = args.index("--output-dir")
        if idx + 1 >= len(args):
            raise SystemExit("--output-dir requires a path argument")
        output_dir = Path(args[idx + 1])
        args = args[:idx] + args[idx + 2:]
    else:
        output_dir = None

    if "--limit" in args:
        idx = args.index("--limit")
        if idx + 1 >= len(args):
            raise SystemExit("--limit requires an integer argument")
        try:
            limit = int(args[idx + 1])
        except ValueError:
            raise SystemExit(f"--limit must be an integer, got {args[idx + 1]!r}")
        args = args[:idx] + args[idx + 2:]
    else:
        limit = None

    if "--multi-angle" in args:
        idx = args.index("--multi-angle")
        multi_angle = True
        args = args[:idx] + args[idx + 1:]
    else:
        multi_angle = False

    if not args:
        raise SystemExit(
            "Usage: python fetch_cyclomedia_panoramas.py <signs_data.json> [signs_history.json] "
            "[--output-dir PATH] [--limit N] [--multi-angle]"
        )
    signs_data_path = args[0]
    signs_history_path = args[1] if len(args) > 1 else None
    return signs_data_path, signs_history_path, output_dir, limit, multi_angle


if __name__ == "__main__":
    signs_data_path, signs_history_path, cli_output_dir, cli_limit, cli_multi_angle = parse_cli_args(sys.argv[1:])
    main(
        signs_data_path,
        signs_history_path,
        output_dir=cli_output_dir if cli_output_dir is not None else DEFAULT_OUTPUT_DIR,
        limit=cli_limit,
        multi_angle=cli_multi_angle,
    )
