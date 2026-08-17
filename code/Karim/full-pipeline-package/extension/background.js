importScripts('retrain-visibility.js');

// Opens welcome.html on a fresh install only -- not on every extension
// update/reload, which would otherwise interrupt an in-progress capture
// session every time the extension is reloaded during development.
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    chrome.tabs.create({ url: chrome.runtime.getURL('welcome.html') });
  }
});

let signsDataCache = null;
const PREDICT_SERVER_URL = 'http://127.0.0.1:8765';

// Karim's server, preferred: always reflects his latest retrain, while the
// bundled ONNX file (extension/model/damage_model.onnx) is a static
// snapshot from whenever the extension was last packaged. Rejects on
// connection failure (the stakeholder package's permanent state -- it ships
// with no server at all) or a non-ok response, same as before.
function fetchServerPrediction(imageDataUrl) {
  return fetch(imageDataUrl)
    .then((r) => r.blob())
    .then((blob) => {
      const formData = new FormData();
      formData.append('file', blob, 'crop.jpg');
      return fetch(`${PREDICT_SERVER_URL}/predict`, {
        method: 'POST',
        body: formData,
        signal: AbortSignal.timeout(3000),
      });
    })
    .then((r) => {
      if (!r.ok) throw new Error(`predict server returned ${r.status}`);
      return r.json();
    })
    .then((data) => ({ ok: true, classes: data.classes }));
}

// ONNX inference can't run in this service worker at all -- ort.wasm.min.js
// (loaded by offscreen.html, not here anymore) uses a dynamic import()
// internally to load its wasm glue module, and import() is banned inside
// ServiceWorkerGlobalScope per the HTML spec:
// https://github.com/w3c/ServiceWorker/issues/1356. This isn't a packaging
// mistake or something a code tweak in this file can fix -- it's a hard
// Chromium platform restriction. The documented fix is an MV3 offscreen
// document: a hidden real page the extension controls, which has an actual
// DOM/page context instead of ServiceWorkerGlobalScope. predictDamageViaOnnx
// now lives in offscreen.js; this function only makes sure that document
// exists, then relays the predict_damage call to it below.
//
// Cache document creation as a promise (same pattern onnx-predict.js's
// getOnnxSession uses for its own session cache) so concurrent
// predict_damage calls don't race and both try to create an offscreen
// document -- chrome.offscreen.createDocument() throws if one already
// exists (or is mid-creation).
let offscreenDocumentPromise = null;

async function ensureOffscreenDocument() {
  if (offscreenDocumentPromise) return offscreenDocumentPromise;

  offscreenDocumentPromise = (async () => {
    // chrome.runtime.getContexts() is the modern, non-deprecated way to
    // check for an existing offscreen document (chrome.offscreen.hasDocument()
    // is older and shouldn't be used for new code). Reused here in case the
    // worker was killed and restarted with the offscreen document still
    // alive from an earlier predict_damage call -- avoids a redundant (and
    // throwing) createDocument() call in that case.
    const existingContexts = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
    });
    if (existingContexts.length > 0) return;

    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      // BLOBS: ort.wasm.min.js's module loader does
      // `URL.createObjectURL(await (await fetch(wasmGlueUrl)).blob())`
      // immediately before the import() call that fails in a service
      // worker -- BLOBS is the Reason enum value that actually matches
      // what this code does (verified against the chrome.offscreen.Reason
      // enum in @types/chrome, which mirrors Chrome's own API surface;
      // there's no enum value specific to "dynamic import" or "WASM").
      reasons: ['BLOBS'],
      justification:
        'onnxruntime-web needs a real DOM/page context to dynamically import its WASM glue module for client-side damage-category inference when the predict server is unreachable; that import() call is disallowed inside the background service worker.',
    });
  })().catch((err) => {
    offscreenDocumentPromise = null; // don't cache a failed creation -- allow the next call to retry
    throw err;
  });

  return offscreenDocumentPromise;
}

// Relays the ONNX fallback to the offscreen document (see
// ensureOffscreenDocument above for why it can't run here directly).
// offscreen.js's own onMessage handler always resolves (never rejects) with
// an {ok, ...} envelope, even on failure -- rethrow here on ok: false so the
// predict_damage handler's existing .catch((onnxErr) => ...) below still
// fires and logs the error, same as when predictDamageViaOnnx used to run
// (and reject) directly in this file.
function predictDamageViaOnnx(imageDataUrl) {
  return ensureOffscreenDocument()
    .then(() => chrome.runtime.sendMessage({ type: 'offscreen_predict_damage', imageDataUrl }))
    .then((result) => {
      if (!result || !result.ok) throw new Error((result && result.error) || 'offscreen predict_damage failed');
      return result;
    });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'get_signs_data') {
    if (signsDataCache) {
      sendResponse({ ok: true, data: signsDataCache });
      return true;
    }
    fetch(chrome.runtime.getURL('signs_data.json'))
      .then((r) => r.json())
      .then((data) => {
        signsDataCache = data;
        sendResponse({ ok: true, data });
      })
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === 'capture') {
    chrome.tabs.captureVisibleTab(sender.tab.windowId, { format: 'png' }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      sendResponse({ ok: true, dataUrl });
    });
    return true; // keep the message channel open for the async response
  }

  if (msg.type === 'save') {
    const { imageDataUrl, filename, record } = msg;

    chrome.downloads.download(
      {
        url: imageDataUrl,
        filename: `manual_capture/${filename}`,
        saveAs: false,
      },
      (downloadId) => {
        if (chrome.runtime.lastError) {
          console.error('download failed:', chrome.runtime.lastError.message);
        } else {
          console.log('download started, id=', downloadId);
        }
      }
    );

    chrome.storage.local.get({ captures: [] }, ({ captures }) => {
      captures.push(record);
      chrome.storage.local.set({ captures }, () => sendResponse({ ok: true }));
    });
    return true;
  }

  if (msg.type === 'predict_damage') {
    fetchServerPrediction(msg.imageDataUrl)
      .catch((serverErr) => {
        // Expected on the stakeholder package (no server at all) -- logged
        // at info level, not error, so it doesn't look like a real failure
        // in a fresh console. The ONNX failure below is the one that
        // matters if suggestions aren't showing up.
        console.log('predict_damage: server unreachable, falling back to ONNX:', String(serverErr));
        return predictDamageViaOnnx(msg.imageDataUrl).catch((onnxErr) => {
          console.error('predict_damage: ONNX fallback failed:', onnxErr);
          throw onnxErr;
        });
      })
      .then((result) => sendResponse(result))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === 'get_retrain_status') {
    fetch(`${PREDICT_SERVER_URL}/retrain-status`)
      .then((r) => {
        if (!r.ok) throw new Error(`retrain-status server returned ${r.status}`);
        return r.json();
      })
      .then((data) => sendResponse({ ok: true, ...data }))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === 'trigger_retrain') {
    fetch(`${PREDICT_SERVER_URL}/retrain`, { method: 'POST' })
      .then((r) => {
        if (!r.ok) {
          return r.json().then((body) => {
            throw new Error(body.detail || `retrain failed (${r.status})`);
          });
        }
        return r.json();
      })
      .then((data) => sendResponse({ ok: true, ...data }))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === 'open_report') {
    if (!msg.runName) return;
    chrome.tabs.create({ url: `${PREDICT_SERVER_URL}/report/${encodeURIComponent(msg.runName)}` });
  }
});

const RETRAIN_STATUS_ALARM = 'retrain-status-check';
chrome.alarms.get(RETRAIN_STATUS_ALARM, (existing) => {
  if (!existing) {
    chrome.alarms.create(RETRAIN_STATUS_ALARM, { periodInMinutes: 1 });
  }
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== RETRAIN_STATUS_ALARM) return;
  fetch(`${PREDICT_SERVER_URL}/retrain-status`)
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (!data || !data.last_run) return;
      chrome.storage.local.get({ lastSeenRunName: null }, ({ lastSeenRunName }) => {
        if (shouldAnnounceNewRun(lastSeenRunName, data.last_run)) {
          chrome.action.setBadgeText({ text: '✓' });
          chrome.action.setBadgeBackgroundColor({ color: '#1e8e3e' });
        }
      });
    })
    .catch(() => {
      // Local model server isn't running -- silently skip this tick, same
      // as the popup's existing "unavailable" handling.
    });
});
