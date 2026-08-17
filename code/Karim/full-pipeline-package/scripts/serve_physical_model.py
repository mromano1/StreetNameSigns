"""Local FastAPI inference server for the Physical Condition model --
serves live damage-type predictions to the capture extension and exposes a
manual retrain trigger. Binds 127.0.0.1 only, no external hosting. See
docs/superpowers/specs/2026-07-31-capture-extension-model-feedback-design.md.

Usage:
    python serve_physical_model.py
"""
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import physical_predict_lib as ppl  # noqa: E402
import physical_report_lib as lib  # noqa: E402
import report_physical  # noqa: E402
import retrain_state  # noqa: E402

CONF_THRESHOLD = report_physical.CONF_THRESHOLD
HOST = "127.0.0.1"
PORT = 8765


def _run_retrain_subprocess():
    """Retrains the physical-condition model end to end (dataset prep,
    training, report/shapefile) via three real script subprocesses run in
    sequence, each with inherited stdout/stderr so their output --
    including Ultralytics' native per-epoch training progress -- streams
    live to this server's own terminal, unlike the old single nbconvert
    --execute call, which captured all cell output rather than relaying it
    in real time. Stops at the first failure (subprocess.CalledProcessError)
    or if training exceeds the same 2-hour budget the old nbconvert call
    used (subprocess.TimeoutExpired) -- without this, a wedged GPU
    training run would hold the retrain lock forever, permanently
    disabling further retrains until the server is restarted. Consistent
    with the existing "baseline not advanced on failure"
    behavior. Does not regenerate the notebook's interactive map (Section
    4) -- that still requires running the notebook interactively; the
    map's underlying shapefile data is unaffected, since report_physical.py
    (the third subprocess here) still generates it."""
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "prepare_yolo_dataset_physical.py")],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "train_physical_model.py")],
        check=True,
        timeout=7200,
    )
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "report_physical.py")],
        check=True,
    )


def _format_run_row(row):
    """row: a raw dict from physical_report_lib.load_last_two_runs (or
    None). Returns the JSON-shaped run summary the extension consumes, or
    None if row is missing or malformed."""
    if row is None:
        return None
    try:
        return {
            "run_name": row["run_name"],
            "precision": float(row["precision"]),
            "recall": float(row["recall"]),
            "map50": float(row["mAP50"]),
            "map50_95": float(row["mAP50_95"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def create_app(model, *, state_path=None, retrain_runner=None, count_labeled_rows_fn=None, history_reader_fn=None, reports_dir=None):
    """Builds the FastAPI app. All I/O dependencies are injectable so tests
    never load a real model, run real training, or touch real repo data --
    see test_serve_physical_model.py."""
    retrain_runner = retrain_runner or _run_retrain_subprocess
    count_labeled_rows_fn = count_labeled_rows_fn or retrain_state.current_labeled_row_count
    history_reader_fn = history_reader_fn or (lambda: lib.load_last_two_runs(report_physical.HISTORY_PATH))
    reports_dir = reports_dir or report_physical.REPORTS_DIR
    retrain_lock = threading.Lock()

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000"],
        allow_methods=["POST"],
        allow_headers=["*"],
    )
    app.state.retrain_lock = retrain_lock

    @app.post("/predict")
    async def predict(file: UploadFile = File(...)):
        data = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            predictions = report_physical.predict_image(model, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        return ppl.predictions_to_response(predictions, threshold=CONF_THRESHOLD)

    @app.get("/retrain-status")
    def get_retrain_status():
        current = count_labeled_rows_fn()
        baseline = retrain_state.read_baseline(state_path)
        last_row, previous_row = history_reader_fn()
        return {
            "new_since_last_retrain": retrain_state.compute_delta(current, baseline),
            "total_labeled": current,
            "baseline": baseline,
            "last_run": _format_run_row(last_row),
            "previous_run": _format_run_row(previous_row),
            "is_retraining": retrain_lock.locked(),
        }

    @app.get("/report/{run_name}")
    def get_report(run_name: str):
        report_path = lib.resolve_report_path(reports_dir, run_name)
        if report_path is None:
            raise HTTPException(status_code=404, detail="report not found")
        return FileResponse(report_path, media_type="text/html")

    @app.post("/retrain")
    def trigger_retrain(origin: str | None = Header(default=None)):
        if origin is not None and not origin.startswith("chrome-extension://"):
            raise HTTPException(status_code=403, detail="cross-origin retrain blocked")
        if not retrain_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="a retrain is already in progress")
        try:
            retrain_runner()
            new_baseline = count_labeled_rows_fn()
            retrain_state.write_baseline(new_baseline, state_path)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or str(e))[-2000:]
            raise HTTPException(status_code=500, detail=detail)
        except subprocess.TimeoutExpired as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            retrain_lock.release()
        return {"ok": True, "new_baseline": new_baseline}

    return app


def main():
    run_name = report_physical.latest_run_name()
    model_path = report_physical.RUNS_DIR / run_name / "weights" / "best.pt"
    print(f"Loading model from {model_path}")
    model = YOLO(str(model_path))
    app = create_app(model)
    print(f"Serving on http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
