"""Pure geometry + lookup logic for turning an annotation-tool box into the
inputs needed for a tighter Cyclomedia re-render. Kept separate from
serve_tight_crop.py so it's testable without FastAPI or a real Cyclomedia
call -- same split as physical_predict_lib.py vs serve_physical_model.py.
See docs/superpowers/specs/2026-08-12-annotation-tool-ml-assist-design.md.
"""
import io
import json
import math
from pathlib import Path

from PIL import Image


def box_to_heading_fov(box, image_width, image_height, original_heading, original_hfov, padding_factor=2.5, min_fov=5.0):
    """box: {"x", "y", "w", "h"} in the native pixel space of the original
    render (image_width x image_height pixels, hfov=original_hfov degrees,
    centered on original_heading degrees). Returns a dict:
      {"heading", "hfov", "height", "top_angle", "bottom_angle"}
    "heading"/"hfov" are what to request horizontally. "height" is the
    OUTPUT height to request at RENDER_WIDTH (fixed) and "hfov", so the
    resulting image's implied vertical FOV is wide enough to still include
    the box -- deliberately oversized, not tight, since there's no way to
    aim vertically (see below). "top_angle"/"bottom_angle" are the box's
    own RAW, unpadded vertical bounds (degrees from the render's pitch=0
    center) -- pass these to vertical_crop_pixels() once the real image
    comes back, to crop the oversized render down to just the box.

    Horizontal: uses the rectilinear (pinhole-camera) projection formula --
    angle = atan(x_frac * tan(hfov/2)) -- not a linear pixel-to-degree scale,
    since a wide-hfov rectilinear render compresses angle differently near
    the edges than the center. Confirmed correct against real off-center
    boxes on both sides (2026-08-14: a box on the image's left edge and one
    on the right edge each correctly returned the real content at that
    position, not a mirrored/wrong result).

    Vertical: there is no pitch parameter in the Cyclomedia render API --
    confirmed empirically (2026-08-14) that a box near the top of a wide
    capture came back showing ground-level content instead, because the
    render is always centered on the same level pitch as the original
    capture no matter where the box is vertically. Since we can't aim
    vertically at the box, this instead requests a tall enough output that
    the box's vertical extent -- however far above/below center -- still
    falls within a pitch-unchanged, symmetric-about-center view. This is
    about size, not direction: unlike heading, there's no "wrong sign" risk
    for this half of the calculation."""
    half_hfov_rad = math.radians(original_hfov / 2)
    half_width = image_width / 2

    def angle_at(px):
        x_frac = (px - half_width) / half_width
        return math.degrees(math.atan(x_frac * math.tan(half_hfov_rad)))

    center_angle = angle_at(box["x"] + box["w"] / 2)
    left_angle = angle_at(box["x"])
    right_angle = angle_at(box["x"] + box["w"])

    new_heading = (original_heading + center_angle) % 360
    box_angular_width = abs(right_angle - left_angle)
    new_hfov = max(box_angular_width * padding_factor, min_fov)

    # Vertical FOV implied by the original capture's own hfov + aspect
    # ratio (standard rectilinear relationship: vfov grows/shrinks with hfov
    # at a fixed width:height).
    original_vfov = 2 * math.degrees(math.atan(math.tan(half_hfov_rad) * image_height / image_width))
    half_vfov_rad = math.radians(original_vfov / 2)
    half_height = image_height / 2

    def vertical_angle_at(py):
        y_frac = (py - half_height) / half_height
        return math.degrees(math.atan(y_frac * math.tan(half_vfov_rad)))

    top_angle = vertical_angle_at(box["y"])
    bottom_angle = vertical_angle_at(box["y"] + box["h"])
    # Symmetric about the (unmovable) pitch=0 center -- governed by
    # whichever edge is angularly farther out, not the box's own height.
    max_vertical_offset = max(abs(top_angle), abs(bottom_angle))
    new_vfov = max(max_vertical_offset * padding_factor, min_fov)

    # Back out the output height (at fixed RENDER_WIDTH == image_width and
    # the new_hfov already computed) that delivers this vfov.
    new_height = image_width * math.tan(math.radians(new_vfov / 2)) / math.tan(math.radians(new_hfov / 2))

    return {
        "heading": new_heading,
        "hfov": new_hfov,
        "height": new_height,
        "top_angle": top_angle,
        "bottom_angle": bottom_angle,
    }


def vertical_crop_pixels(top_angle, bottom_angle, rendered_width, rendered_height, rendered_hfov, padding_factor=1.5, min_fov=5.0):
    """Given a box's raw vertical bounds (top_angle/bottom_angle, from
    box_to_heading_fov -- degrees from center) and the dimensions/hfov of
    an ALREADY-RENDERED image, returns (crop_top_px, crop_bottom_px): the
    pixel row range to crop that image down to, so the saved/displayed
    result is tight around the box instead of the full, deliberately
    oversized render.

    The rendered image's own vertical center is the same pitch=0 reference
    top_angle/bottom_angle were computed against -- the render never moves
    pitch, only its height/hfov change, so that reference carries over
    unchanged. Pass the ACTUAL rendered_height (after any clamping, e.g.
    to the Atlas Render API's real size limit) and rendered_hfov -- not
    the pre-clamp ideal values -- since this depends on what was really
    delivered, not what was originally requested."""
    rendered_vfov = 2 * math.degrees(math.atan(
        math.tan(math.radians(rendered_hfov / 2)) * rendered_height / rendered_width
    ))
    half_vfov_rad = math.radians(rendered_vfov / 2)
    half_height = rendered_height / 2

    def px_at(angle):
        return half_height + half_height * (math.tan(math.radians(angle)) / math.tan(half_vfov_rad))

    box_angular_height = abs(bottom_angle - top_angle)
    center_angle = (top_angle + bottom_angle) / 2
    half_crop_vfov = max(box_angular_height / 2 * padding_factor, min_fov / 2)

    crop_top_px = px_at(center_angle - half_crop_vfov)
    crop_bottom_px = px_at(center_angle + half_crop_vfov)
    crop_top_px = max(0, min(rendered_height, crop_top_px))
    crop_bottom_px = max(0, min(rendered_height, crop_bottom_px))
    return round(crop_top_px), round(crop_bottom_px)


def crop_image_vertically(image_bytes, top_px, bottom_px):
    """Crops a JPEG's rows [top_px, bottom_px), keeping full width, and
    re-encodes as JPEG. Turns the API's deliberately oversized render
    (padded to guarantee vertical inclusion, given no pitch parameter --
    see box_to_heading_fov) into a genuinely tight result.

    top_px/bottom_px are computed against an EXPECTED image size (the
    height actually requested from the render API). If the real delivered
    image doesn't match -- a test double, or the API returning something
    unexpected -- clamping both to the same boundary would otherwise
    produce a zero-height crop, which Pillow can't encode at all. Degrade
    to returning the image unchanged rather than failing the whole
    request over a framing nicety."""
    image = Image.open(io.BytesIO(image_bytes))
    width, height = image.size
    top_px = max(0, min(height, top_px))
    bottom_px = max(top_px, min(height, bottom_px))
    if bottom_px <= top_px:
        return image_bytes
    cropped = image.crop((0, top_px, width, bottom_px))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def find_job(manifest, corner_id, image_kind):
    """manifest: parsed fetch_manifest.json dict. Returns the matching job
    dict, or None if no job with that corner_id/image_kind has a real file
    on disk. "ok" (fetched this run) and "skipped" (fetch_cyclomedia_
    panoramas.py found the file already there from an earlier run and
    didn't re-fetch it) both mean that -- only "failed" (no recording
    found / API error, no file exists) is excluded. A "skipped" job has no
    recording_id cached (that's only ever set on the fresh-fetch path);
    the caller has to re-resolve one -- see serve_tight_crop.py."""
    for job in manifest.get("jobs", []):
        if (
            job.get("corner_id") == corner_id
            and job.get("image_kind") == image_kind
            and job.get("status") in ("ok", "skipped")
        ):
            return job
    return None


def tight_crop_relative_path(corner_id, image_kind, box_index):
    return f"{corner_id}/tight_{image_kind}_{box_index}.jpg"


def discover_manifest_paths(panoramas_dir):
    """Root fetch_manifest.json (the original/default collection, if
    present) plus one level of subfolder fetch_manifest.json files (each
    a separate --output-dir pull, e.g. demo_cb301/) -- the same discovery
    pattern list_panorama_datasets.py uses for the dropdown, so every
    dataset the annotation tool can select from is also searchable here."""
    panoramas_dir = Path(panoramas_dir)
    paths = []
    root = panoramas_dir / "fetch_manifest.json"
    if root.exists():
        paths.append(root)
    paths.extend(sorted(panoramas_dir.glob("*/fetch_manifest.json")))
    return paths


def find_job_and_output_dir(manifest_paths, corner_id, image_kind):
    """Searches each manifest in turn for a matching successful job.
    Returns (job, output_dir) for the first match -- output_dir is that
    manifest's own parent directory, so the resulting tight crop gets
    written co-located with its source image, not into some other
    dataset's folder. Returns (None, None) if no manifest has a match."""
    for manifest_path in manifest_paths:
        manifest = json.loads(Path(manifest_path).read_text())
        job = find_job(manifest, corner_id, image_kind)
        if job is not None:
            return job, Path(manifest_path).parent
    return None, None
