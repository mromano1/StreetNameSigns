/**
 * Loaded as a plain <script> before content.js (see manifest.json) and via
 * require() in location-freshness.test.js -- same CommonJS-guard pattern as
 * date-utils.js / damage-prediction.js.
 *
 * On Street Smart, content.js's lastKnownLocation only exists to bridge the
 * moment between clicking "Capture Sign" (which closes the info panel) and
 * finishSelection() running -- a UI-click-to-async-completion gap, not an
 * indefinite cache. Without a freshness check, a location read at one
 * position kept being reused as the fallback for captures at a completely
 * different position navigated to afterward, because nothing ever expired
 * it (bug: "right intersection, wrong street number" unless the info panel
 * was reopened at the new spot first). MAX_FALLBACK_LOCATION_AGE_MS is
 * generous relative to the compass HUD's 400ms poll interval and a normal
 * click-to-callback gap, while still being far too short to survive
 * navigating to a new corner.
 */

const MAX_FALLBACK_LOCATION_AGE_MS = 2000;

function isLocationFresh(recordedAtMs, nowMs, maxAgeMs) {
  return recordedAtMs != null && nowMs - recordedAtMs <= maxAgeMs;
}

// Content scripts listed together in manifest.json share one global scope
// (they are not separate modules), so a top-level `const api` here would
// collide with date-utils.js's own top-level `const api` -- confirmed live
// 2026-08-04: that collision is a parse-time SyntaxError that silently
// aborted this whole file's execution, breaking capture entirely. Inlining
// the export directly avoids naming an intermediate identifier at all, the
// same way damage-prediction.js already does.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { isLocationFresh, MAX_FALLBACK_LOCATION_AGE_MS };
}
