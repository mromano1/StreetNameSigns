// Runs inside offscreen.html -- a real page/DOM context, not
// ServiceWorkerGlobalScope. Moved here verbatim from background.js because
// onnxruntime-web's WASM backend uses a dynamic import() internally
// (ort.wasm.min.js's blob-URL module loader) to load its wasm glue module,
// and import() is banned inside service workers per the HTML spec:
// https://github.com/w3c/ServiceWorker/issues/1356. background.js relays
// predict_damage's ONNX fallback here via chrome.runtime.sendMessage; see
// ensureOffscreenDocument() there for the document-lifecycle side of this.
const ONNX_INPUT_SIZE = 640;
const ONNX_PAD_VALUE = 114; // gray padding, matching ultralytics' own letterbox convention

// Client-side fallback used only when the server is unreachable. Letterbox-
// resizes into a 640x640 gray-padded frame via OffscreenCanvas (available in
// this offscreen-document context too, same as it was in the service
// worker) -- the pure geometry math (scale/pad computation) lives in
// onnx-predict.js's computeLetterboxGeometry so it's unit-testable without a
// real canvas; this function just carries out the actual pixel draw with
// those numbers, then hands the padded pixels to onnx-predict.js's session
// wrapper (loaded via <script src> above, same file as before).
async function predictDamageViaOnnx(imageDataUrl) {
  const blob = await (await fetch(imageDataUrl)).blob();
  const bitmap = await createImageBitmap(blob);
  const { newWidth, newHeight, padX, padY } = computeLetterboxGeometry(
    bitmap.width,
    bitmap.height,
    ONNX_INPUT_SIZE
  );

  const canvas = new OffscreenCanvas(ONNX_INPUT_SIZE, ONNX_INPUT_SIZE);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = `rgb(${ONNX_PAD_VALUE}, ${ONNX_PAD_VALUE}, ${ONNX_PAD_VALUE})`;
  ctx.fillRect(0, 0, ONNX_INPUT_SIZE, ONNX_INPUT_SIZE);
  ctx.drawImage(bitmap, 0, 0, bitmap.width, bitmap.height, padX, padY, newWidth, newHeight);

  const imageData = ctx.getImageData(0, 0, ONNX_INPUT_SIZE, ONNX_INPUT_SIZE);
  const classes = await predictDamageOnnx(imageData.data, ONNX_INPUT_SIZE);
  return { ok: true, classes };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'offscreen_predict_damage') {
    predictDamageViaOnnx(msg.imageDataUrl)
      .then((result) => sendResponse(result))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true; // keep the message channel open for the async response
  }
});
