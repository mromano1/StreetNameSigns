import json
import math

import pytest

import tight_crop_lib as lib


def test_box_to_heading_fov_center_box_has_zero_offset():
    # image_width=3200, image_height=2400, hfov=120, box centered exactly on
    # the image center (1600, 1200).
    box = {"x": 1590, "y": 1190, "w": 20, "h": 20}
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    assert result["heading"] == pytest.approx(45.0, abs=1e-6)
    assert result["hfov"] > 0
    assert result["height"] > 0


def test_box_to_heading_fov_off_center_right_increases_heading():
    box = {"x": 1990, "y": 1190, "w": 20, "h": 20}  # center at pixel 2000, right of image center
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    # Expected via the same rectilinear formula, computed independently here.
    x_frac = (2000 - 1600) / 1600
    expected_offset = math.degrees(math.atan(x_frac * math.tan(math.radians(60))))
    assert result["heading"] == pytest.approx((45.0 + expected_offset) % 360, abs=1e-6)
    assert result["heading"] > 45.0


def test_box_to_heading_fov_off_center_left_decreases_heading():
    box = {"x": 1190, "y": 1190, "w": 20, "h": 20}  # center at pixel 1200, left of image center
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    assert result["heading"] < 45.0


def test_box_to_heading_fov_new_fov_scales_with_box_width():
    narrow = {"x": 1590, "y": 1190, "w": 20, "h": 20}
    wide = {"x": 1400, "y": 1190, "w": 400, "h": 20}
    narrow_result = lib.box_to_heading_fov(narrow, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    wide_result = lib.box_to_heading_fov(wide, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    assert wide_result["hfov"] > narrow_result["hfov"]


def test_box_to_heading_fov_respects_minimum_fov():
    tiny_box = {"x": 1599, "y": 1199, "w": 2, "h": 2}
    result = lib.box_to_heading_fov(tiny_box, 3200, 2400, original_heading=45.0, original_hfov=120.0, min_fov=5.0)
    assert result["hfov"] == pytest.approx(5.0)


def test_box_to_heading_fov_wraps_heading_past_360():
    box = {"x": 1990, "y": 1190, "w": 20, "h": 20}
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=355.0, original_hfov=120.0)
    assert 0.0 <= result["heading"] < 360.0


# --- Vertical framing: no pitch parameter exists in the Cyclomedia render
# API (confirmed empirically 2026-08-14: a box near the top of a wide
# capture came back showing ground-level content, not the top of the
# frame -- the render is always centered on the same level pitch as the
# original capture, regardless of where the box is vertically). Since we
# can't aim vertically at the box, the only way to keep it in frame is to
# request tall enough output that the box's vertical extent -- however far
# off-center -- still falls within a pitch-unchanged, symmetric view. These
# tests are about the requested *size* being big enough, not direction --
# unlike heading, there's no "wrong sign" risk here, only "not tall enough".
# top_angle/bottom_angle (also returned) are the box's own RAW vertical
# bounds, unpadded -- used by vertical_crop_pixels() to crop the delivered
# (deliberately oversized) render back down to just the box afterward.

def test_box_to_heading_fov_vertically_centered_tiny_box_is_square():
    # A tiny box exactly at both horizontal and vertical center clamps to
    # min_fov in both directions -- when hfov == vfov, height/width == 1
    # (aspect ratio directly follows tan(vfov/2)/tan(hfov/2)), so the
    # requested output is square at RENDER_WIDTH regardless of the
    # original capture's own (wider) 3200x2400 aspect ratio.
    box = {"x": 1599, "y": 1199, "w": 2, "h": 2}
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=45.0, original_hfov=120.0, min_fov=5.0)
    assert result["hfov"] == pytest.approx(5.0)
    assert result["height"] == pytest.approx(3200, rel=1e-6)


def test_box_to_heading_fov_box_near_top_requests_much_taller_output():
    # Same horizontal position/size (same hfov) as a vertically-centered
    # box, but moved to the very top of the frame -- since the render can't
    # tilt up to follow it, the only way to keep it in frame is to request
    # a much taller output.
    centered = {"x": 1590, "y": 1190, "w": 20, "h": 20}
    near_top = {"x": 1590, "y": 10, "w": 20, "h": 20}
    centered_result = lib.box_to_heading_fov(centered, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    top_result = lib.box_to_heading_fov(near_top, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    assert top_result["hfov"] == pytest.approx(centered_result["hfov"], abs=1e-6)  # same horizontal position/size -> same hfov
    assert top_result["height"] > centered_result["height"] * 5  # dramatically taller to still include the box


def test_box_to_heading_fov_box_spanning_across_vertical_center():
    # A box whose top is above center and bottom is below center: the
    # required extent is governed by whichever edge is angularly farther
    # from center, not by the box's own (small) height.
    box = {"x": 1590, "y": 100, "w": 20, "h": 2200}  # spans nearly the whole frame vertically
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    small_centered = {"x": 1590, "y": 1190, "w": 20, "h": 20}
    small_result = lib.box_to_heading_fov(small_centered, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    assert result["height"] > small_result["height"] * 5


def test_box_to_heading_fov_returns_raw_top_and_bottom_angles():
    # A vertically-centered box's raw top/bottom angles should straddle
    # zero (roughly symmetric), independent of any padding applied to
    # "height" -- these are the unpadded box bounds, not a padded FOV.
    box = {"x": 1590, "y": 1190, "w": 20, "h": 20}
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    assert result["top_angle"] < 0 < result["bottom_angle"]
    assert result["top_angle"] == pytest.approx(-result["bottom_angle"], abs=1e-6)


def test_box_to_heading_fov_top_angle_negative_for_box_near_top_of_frame():
    box = {"x": 1590, "y": 10, "w": 20, "h": 20}  # entirely near the top -- both edges above center
    result = lib.box_to_heading_fov(box, 3200, 2400, original_heading=45.0, original_hfov=120.0)
    assert result["top_angle"] < 0
    assert result["bottom_angle"] < 0


def test_vertical_crop_pixels_centers_on_a_vertically_centered_box():
    # rendered_height/rendered_hfov describe an already-received render
    # whose own vertical center is the same pitch=0 reference as top_angle/
    # bottom_angle were computed against.
    crop_top, crop_bottom = lib.vertical_crop_pixels(
        top_angle=-2.0, bottom_angle=2.0, rendered_width=3200, rendered_height=3200, rendered_hfov=10.0,
    )
    center_px = (crop_top + crop_bottom) / 2
    assert center_px == pytest.approx(1600, abs=2)  # rendered_height/2


def test_vertical_crop_pixels_shifts_for_an_off_center_box():
    # A box entirely above center (both angles negative) should crop to a
    # pixel range entirely above the rendered image's own vertical center.
    crop_top, crop_bottom = lib.vertical_crop_pixels(
        top_angle=-30.0, bottom_angle=-25.0, rendered_width=3200, rendered_height=8192, rendered_hfov=10.0,
    )
    assert crop_bottom < 4096  # above rendered_height/2


def test_vertical_crop_pixels_clamps_to_image_bounds():
    crop_top, crop_bottom = lib.vertical_crop_pixels(
        top_angle=-89.0, bottom_angle=-88.0, rendered_width=3200, rendered_height=200, rendered_hfov=170.0,
    )
    assert 0 <= crop_top <= 200
    assert 0 <= crop_bottom <= 200


def test_vertical_crop_pixels_top_is_always_above_bottom():
    crop_top, crop_bottom = lib.vertical_crop_pixels(
        top_angle=5.0, bottom_angle=10.0, rendered_width=3200, rendered_height=3200, rendered_hfov=10.0,
    )
    assert crop_top < crop_bottom


def _solid_color_jpeg(width, height, top_half_color=(255, 0, 0), bottom_half_color=(0, 0, 255)):
    from PIL import Image
    import io as _io
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for y in range(height):
        color = top_half_color if y < height / 2 else bottom_half_color
        for x in range(width):
            pixels[x, y] = color
    buf = _io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_crop_image_vertically_produces_the_requested_dimensions():
    from PIL import Image
    import io as _io
    original = _solid_color_jpeg(100, 200)
    cropped_bytes = lib.crop_image_vertically(original, top_px=50, bottom_px=150)
    cropped = Image.open(_io.BytesIO(cropped_bytes))
    assert cropped.size == (100, 100)


def test_crop_image_vertically_falls_back_to_uncropped_when_the_range_is_degenerate():
    # If crop_top/crop_bottom (computed against an EXPECTED height) don't
    # match the ACTUAL delivered image's real size -- e.g. a test double,
    # or the real API returning something unexpected -- clamping both to
    # the same boundary would otherwise produce a zero-height crop and
    # crash. Degrade to returning the image unchanged instead of failing
    # the whole request over a framing nicety.
    original = _solid_color_jpeg(20, 20)
    cropped_bytes = lib.crop_image_vertically(original, top_px=5000, bottom_px=5010)
    from PIL import Image
    import io as _io
    result = Image.open(_io.BytesIO(cropped_bytes))
    assert result.size == (20, 20)  # unchanged, not a crash or an empty image


def test_crop_image_vertically_keeps_the_correct_region():
    # Top half red, bottom half blue -- cropping to just the bottom half
    # should leave (predominantly) blue pixels.
    from PIL import Image
    import io as _io
    original = _solid_color_jpeg(20, 200, top_half_color=(255, 0, 0), bottom_half_color=(0, 0, 255))
    cropped_bytes = lib.crop_image_vertically(original, top_px=150, bottom_px=200)
    cropped = Image.open(_io.BytesIO(cropped_bytes)).convert("RGB")
    r, g, b = cropped.getpixel((10, 25))
    assert b > r  # solidly in the blue (bottom) region


def test_find_job_matches_corner_and_image_kind():
    manifest = {
        "jobs": [
            {"corner_id": "A", "image_kind": "latest", "status": "ok", "recording_id": "R1"},
            {"corner_id": "B", "image_kind": "latest", "status": "ok", "recording_id": "R2"},
        ]
    }
    job = lib.find_job(manifest, "B", "latest")
    assert job["recording_id"] == "R2"


def test_find_job_returns_none_when_no_match():
    manifest = {"jobs": [{"corner_id": "A", "image_kind": "latest", "status": "ok"}]}
    assert lib.find_job(manifest, "Z", "latest") is None


def test_find_job_skips_failed_status():
    manifest = {
        "jobs": [
            {"corner_id": "A", "image_kind": "latest", "status": "failed", "recording_id": "R1"},
        ]
    }
    assert lib.find_job(manifest, "A", "latest") is None


def test_find_job_matches_skipped_status():
    # "skipped" means fetch_cyclomedia_panoramas.py found the file already
    # on disk from an earlier run and didn't re-fetch it -- the file is
    # just as real and annotatable as an "ok" one, it just has no
    # recording_id cached (that's only ever set on the fresh-fetch path).
    manifest = {
        "jobs": [
            {"corner_id": "A", "image_kind": "latest", "status": "skipped", "lat": 40.7, "lon": -73.9},
        ]
    }
    job = lib.find_job(manifest, "A", "latest")
    assert job is not None
    assert job.get("recording_id") is None


def test_tight_crop_relative_path_format():
    assert lib.tight_crop_relative_path("10001_000", "latest", 2) == "10001_000/tight_latest_2.jpg"


def _write_manifest(dir_path, jobs):
    dir_path.mkdir(parents=True, exist_ok=True)
    manifest_path = dir_path / "fetch_manifest.json"
    manifest_path.write_text(json.dumps({"jobs": jobs}))
    return manifest_path


def test_discover_manifest_paths_finds_root_and_subfolder_manifests(tmp_path):
    _write_manifest(tmp_path, [])
    _write_manifest(tmp_path / "demo_cb301", [])

    paths = lib.discover_manifest_paths(tmp_path)

    assert set(paths) == {tmp_path / "fetch_manifest.json", tmp_path / "demo_cb301" / "fetch_manifest.json"}


def test_discover_manifest_paths_skips_missing_root(tmp_path):
    _write_manifest(tmp_path / "demo_cb301", [])

    paths = lib.discover_manifest_paths(tmp_path)

    assert paths == [tmp_path / "demo_cb301" / "fetch_manifest.json"]


def test_find_job_and_output_dir_searches_every_manifest_for_a_match(tmp_path):
    _write_manifest(tmp_path, [{"corner_id": "A", "image_kind": "latest", "status": "ok", "recording_id": "R_root"}])
    _write_manifest(
        tmp_path / "demo_cb301",
        [{"corner_id": "cb301_000", "image_kind": "latest", "status": "ok", "recording_id": "R_cb301"}],
    )
    manifest_paths = lib.discover_manifest_paths(tmp_path)

    job, output_dir = lib.find_job_and_output_dir(manifest_paths, "cb301_000", "latest")

    assert job["recording_id"] == "R_cb301"
    assert output_dir == tmp_path / "demo_cb301"


def test_find_job_and_output_dir_returns_none_none_when_no_manifest_matches(tmp_path):
    _write_manifest(tmp_path, [{"corner_id": "A", "image_kind": "latest", "status": "ok"}])
    manifest_paths = lib.discover_manifest_paths(tmp_path)

    job, output_dir = lib.find_job_and_output_dir(manifest_paths, "MISSING", "latest")

    assert job is None
    assert output_dir is None
