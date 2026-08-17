"""Local FastAPI server that turns an annotation-tool box into a tighter
Cyclomedia re-render of the same recording -- for real added detail over
the wide capture setting, confirmed empirically (see
docs/superpowers/specs/2026-08-12-annotation-tool-ml-assist-design.md).
Binds 127.0.0.1 only.

Usage:
    python serve_tight_crop.py
"""
import base64
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import cyclomedia_client as cc  # noqa: E402
import tight_crop_lib as lib  # noqa: E402
from fetch_cyclomedia_panoramas import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    WIDE_HFOV,
)

HOST = "127.0.0.1"
PORT = 8766
ANNOTATION_TOOL_ORIGIN = "http://localhost:8000"

# The Atlas Render API's own hard limit -- confirmed live (2026-08-14): a
# request above this gets rejected with "The field Height must be between
# 0 and 8192."
MAX_RENDER_HEIGHT = 8192


class BoxModel(BaseModel):
    x: float
    y: float
    w: float
    h: float


class TightCropRequest(BaseModel):
    corner_id: str
    image_kind: str
    box_index: int
    box: BoxModel


def create_app(panoramas_dir, render_fn=None, find_recording_fn=None):
    """Builds the FastAPI app. panoramas_dir/render_fn/find_recording_fn are
    injectable so tests never touch real fetch_manifest.json files, real
    disk output, or make a real Cyclomedia call -- see
    test_serve_tight_crop.py.

    panoramas_dir is the ROOT of all pulled collections (data/cyclomedia_
    panoramas/), not a single dataset's folder -- every request searches
    across the root collection and every subfolder collection (same
    discovery the annotation tool's dataset dropdown uses) for the
    corner_id, since the tool can be annotating any of them. This used to
    be pinned to one manifest_path/output_dir pair, which silently 404'd
    every tight-crop/damage-suggestion request for any dataset besides
    whichever one main() happened to hardcode."""
    render_fn = render_fn or cc.render_recording
    find_recording_fn = find_recording_fn or cc.find_nearest_recording
    panoramas_dir = Path(panoramas_dir)

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ANNOTATION_TOOL_ORIGIN],
        allow_methods=["POST"],
        allow_headers=["*"],
    )

    @app.post("/tight-crop")
    def tight_crop(req: TightCropRequest):
        manifest_paths = lib.discover_manifest_paths(panoramas_dir)
        job, output_dir = lib.find_job_and_output_dir(manifest_paths, req.corner_id, req.image_kind)
        if job is None:
            raise HTTPException(status_code=404, detail="no matching fetch job found")

        # A "skipped" job (file already existed from an earlier run) never
        # called Cyclomedia the first time, so it has no recording_id
        # cached -- resolve one fresh, same lookup fetch_cyclomedia_
        # panoramas.py's run_job would have done originally. An "ok" job
        # already has one; never re-look-up (wastes an API call).
        recording_id = job.get("recording_id")
        if recording_id is None:
            recording_id = find_recording_fn(job["lat"], job["lon"])
            if recording_id is None:
                raise HTTPException(status_code=502, detail="no recording found near this location")

        framing = lib.box_to_heading_fov(
            req.box.model_dump(), RENDER_WIDTH, RENDER_HEIGHT, job["heading"], WIDE_HFOV,
        )
        # Ceiling confirmed against the real API (2026-08-14): a request
        # above 8192 gets rejected outright with "The field Height must be
        # between 0 and 8192." A box drawn near the very edge of a wide
        # capture can call for a very tall output (no pitch parameter means
        # the only way to keep it in frame is a taller image, see
        # box_to_heading_fov's docstring) -- clamp to what the API will
        # actually accept rather than fail the whole request.
        new_height = min(round(framing["height"]), MAX_RENDER_HEIGHT)
        try:
            image_bytes = render_fn(
                recording_id, framing["heading"], width=RENDER_WIDTH, height=new_height, fov=framing["hfov"],
            )
        except cc.CyclomediaError as e:
            raise HTTPException(status_code=502, detail=str(e))

        # The render above is deliberately oversized vertically (padded to
        # guarantee the box is in frame at all, given no pitch parameter --
        # see box_to_heading_fov's docstring) -- crop it down to just the
        # box now that we know exactly what was delivered (new_height,
        # post-clamp, not the pre-clamp ideal).
        crop_top, crop_bottom = lib.vertical_crop_pixels(
            framing["top_angle"], framing["bottom_angle"], RENDER_WIDTH, new_height, framing["hfov"],
        )
        image_bytes = lib.crop_image_vertically(image_bytes, crop_top, crop_bottom)

        rel_within_dataset = lib.tight_crop_relative_path(req.corner_id, req.image_kind, req.box_index)
        out_path = output_dir / rel_within_dataset
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(image_bytes)

        # Relative to panoramas_dir (not just output_dir), so the returned
        # path is unambiguous regardless of which dataset it came from --
        # e.g. "demo_cb301/cb301_000/tight_latest_0.jpg", not just
        # "cb301_000/tight_latest_0.jpg" (which looks identical in shape to
        # a root-collection path).
        returned_path = str(out_path.relative_to(panoramas_dir))

        return {"path": returned_path, "image_base64": base64.b64encode(image_bytes).decode("ascii")}

    return app


def main():
    load_dotenv(SCRIPT_DIR.parent / ".env")
    app = create_app(DEFAULT_OUTPUT_DIR)
    print(f"Serving on http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
