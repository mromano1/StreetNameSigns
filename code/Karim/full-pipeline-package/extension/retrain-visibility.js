// Decides when the toolbar badge / popup accuracy panel should announce a
// newly finished retrain, and formats the accuracy comparison text. Pure
// logic only -- background.js and popup.js both load this (background.js
// via importScripts, popup.js via a <script> tag) and wire it to
// chrome.storage/chrome.action; see docs/superpowers/specs/
// 2026-08-01-retrain-visibility-design.md.

// lastSeenRunName: the run_name string stored in chrome.storage.local, or
// null if no run has ever been shown. lastRun: {run_name, ...} or null (no
// runs yet / server unreachable).
function shouldAnnounceNewRun(lastSeenRunName, lastRun) {
  if (!lastRun || !lastRun.run_name) return false;
  return lastRun.run_name !== lastSeenRunName;
}

// lastRun/previousRun: {run_name, precision, recall, map50, map50_95}
// (fractions 0-1) or null. Returns null if there's no last run at all;
// otherwise text for each metric, with a "(+/-N.Npp vs previous)" suffix
// when a previous run exists to compare against.
function formatAccuracyComparison(lastRun, previousRun) {
  if (!lastRun) return null;

  const pct = (n) => `${(n * 100).toFixed(1)}%`;
  const withDelta = (curr, prev) => {
    if (prev == null) return pct(curr);
    const deltaPts = (curr - prev) * 100;
    const sign = deltaPts >= 0 ? '+' : '';
    return `${pct(curr)} (${sign}${deltaPts.toFixed(1)}pp vs previous)`;
  };

  return {
    runName: lastRun.run_name,
    precisionText: withDelta(lastRun.precision, previousRun && previousRun.precision),
    recallText: withDelta(lastRun.recall, previousRun && previousRun.recall),
    map50Text: withDelta(lastRun.map50, previousRun && previousRun.map50),
    map5095Text: withDelta(lastRun.map50_95, previousRun && previousRun.map50_95),
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { shouldAnnounceNewRun, formatAccuracyComparison };
}
