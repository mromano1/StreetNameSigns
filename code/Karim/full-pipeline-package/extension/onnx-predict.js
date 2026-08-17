// Client-side ONNX fallback for damage-category prediction, used when
// background.js's server fetch to scripts/serve_physical_model.py fails
// (the stakeholder package's permanent state -- it ships with no server at
// all). Loaded into background.js via importScripts, same pattern as
// retrain-visibility.js. See
// docs/superpowers/specs/2026-08-04-onnx-live-suggestions-design.md section 4.4.
//
// Mirrors PHYSICAL_CLASS_NAMES in scripts/physical_report_lib.py -- keep
// both in sync if that class list ever changes. Order matters: it maps the
// ONNX model's output class ids (0-4) back to names.
const PHYSICAL_CLASS_NAMES = ['old_design', 'faded', 'bent_damaged', 'hanging', 'vandalized'];

// Mirrors report_physical.py's CONF_THRESHOLD.
const CONF_THRESHOLD = 0.25;

const ONNX_MODEL_PATH = 'model/damage_model.onnx';
const ONNX_VENDOR_WASM_DIR = 'vendor/onnxruntime-web/';

// ---- Pure, unit-testable ----------------------------------------------

// srcWidth/srcHeight: the source image's natural pixel dimensions.
// targetSize: the model's expected square input size (640).
// Returns the aspect-preserving letterbox geometry (matching ultralytics'
// own preprocessing convention: scale to fit, center with gray padding) --
// NOT the resized pixels themselves. The actual pixel resize happens via
// OffscreenCanvas in background.js (a real canvas can't run inside
// node --test), using these numbers to know where to draw. This is the one
// place a subtle bug would silently skew every prediction, since there's no
// automated parity suite catching it (see the design doc's parity-bar
// section) -- reviewed carefully, tested against synthetic dimensions below.
function computeLetterboxGeometry(srcWidth, srcHeight, targetSize) {
  const scale = Math.min(targetSize / srcWidth, targetSize / srcHeight);
  const newWidth = Math.round(srcWidth * scale);
  const newHeight = Math.round(srcHeight * scale);
  const padX = Math.floor((targetSize - newWidth) / 2);
  const padY = Math.floor((targetSize - newHeight) / 2);
  return { scale, newWidth, newHeight, padX, padY };
}

// rgba: a flat RGBA pixel buffer (Uint8ClampedArray or plain array) of a
// size x size image -- the already letterbox-padded canvas output.
// Returns a Float32Array shaped [3, size, size] (CHW, RGB, normalized to
// 0-1), matching ultralytics' own input tensor convention (BGR->RGB,
// HWC->CHW, /255). Alpha is discarded -- never consumed downstream.
function imageToTensor(rgba, size) {
  const plane = size * size;
  const tensor = new Float32Array(3 * plane);
  for (let i = 0; i < plane; i++) {
    const srcIdx = i * 4;
    tensor[i] = rgba[srcIdx] / 255;
    tensor[plane + i] = rgba[srcIdx + 1] / 255;
    tensor[2 * plane + i] = rgba[srcIdx + 2] / 255;
  }
  return tensor;
}

// outputData: the raw post-NMS [N, 6] tensor data, flattened row-major
// (x1, y1, x2, y2, conf, cls per detection) -- the ONNX model was exported
// end-to-end (see scripts/export_physical_model_onnx.py), so this is
// already the fully decoded/NMS'd detection list, same as
// report_physical.py's predict_image() gets from the .pt model.
// numDetections: number of rows (the model's fixed max-detections dim,
// e.g. 300 -- most rows are typically near-zero-confidence padding).
// Box coordinates are discarded -- only class_name/confidence are consumed
// anywhere downstream (damage-prediction.js's buildDamageGuessPlan).
function parseDetections(outputData, numDetections, classNames = PHYSICAL_CLASS_NAMES, threshold = CONF_THRESHOLD) {
  const results = [];
  for (let i = 0; i < numDetections; i++) {
    const base = i * 6;
    const confidence = outputData[base + 4];
    if (confidence < threshold) continue;
    const clsId = Math.round(outputData[base + 5]);
    const className = classNames[clsId];
    if (className === undefined) continue; // unrecognized class id -- skip, don't crash
    results.push({ class_name: className, confidence });
  }
  return results;
}

// ---- Session glue (not pure, thin) -------------------------------------

// MV3 service workers can be killed when idle and recreated on the next
// event, so this module-level cache can't be assumed to survive between
// calls -- but within one live worker instance, reuse it rather than
// recreating the session on every predict_damage call. Treat creation as
// cheap and idempotent: create-if-missing each time this is called.
let sessionPromise = null;

function getOnnxSession() {
  if (!sessionPromise) {
    ort.env.wasm.wasmPaths = chrome.runtime.getURL(ONNX_VENDOR_WASM_DIR);
    ort.env.wasm.numThreads = 1; // avoid spawning Worker threads -- not reliably supported inside a service worker
    ort.env.wasm.proxy = false;
    sessionPromise = ort.InferenceSession.create(
      chrome.runtime.getURL(ONNX_MODEL_PATH),
      { executionProviders: ['wasm'] }
    ).catch((err) => {
      sessionPromise = null; // don't cache a permanently-broken session -- allow the next call to retry
      throw err;
    });
  }
  return sessionPromise;
}

// letterboxedRgba: a flat RGBA buffer of a size x size image, already
// letterbox-padded by the caller (background.js, via OffscreenCanvas using
// computeLetterboxGeometry's output). Returns [{class_name, confidence}, ...]
// -- the same shape the server's /predict response already provides, so
// content.js/damage-prediction.js require zero changes.
async function predictDamageOnnx(letterboxedRgba, size) {
  const tensorData = imageToTensor(letterboxedRgba, size);
  const session = await getOnnxSession();
  const inputName = session.inputNames[0];
  const outputName = session.outputNames[0];
  const inputTensor = new ort.Tensor('float32', tensorData, [1, 3, size, size]);
  const results = await session.run({ [inputName]: inputTensor });
  const output = results[outputName];
  const numDetections = output.dims[1];
  return parseDetections(output.data, numDetections);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    PHYSICAL_CLASS_NAMES,
    CONF_THRESHOLD,
    computeLetterboxGeometry,
    imageToTensor,
    parseDetections,
    getOnnxSession,
    predictDamageOnnx,
  };
}
