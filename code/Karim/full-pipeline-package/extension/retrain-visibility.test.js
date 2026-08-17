const test = require("node:test");
const assert = require("node:assert/strict");
const { shouldAnnounceNewRun, formatAccuracyComparison } = require("./retrain-visibility.js");

test("shouldAnnounceNewRun is true the first time (no stored run name yet)", () => {
  assert.equal(shouldAnnounceNewRun(null, { run_name: "run1" }), true);
});

test("shouldAnnounceNewRun is true when the run name changed", () => {
  assert.equal(shouldAnnounceNewRun("run1", { run_name: "run2" }), true);
});

test("shouldAnnounceNewRun is false when the run name matches", () => {
  assert.equal(shouldAnnounceNewRun("run2", { run_name: "run2" }), false);
});

test("shouldAnnounceNewRun is false when there is no last run", () => {
  assert.equal(shouldAnnounceNewRun("run1", null), false);
});

test("formatAccuracyComparison returns null when there is no last run", () => {
  assert.equal(formatAccuracyComparison(null, null), null);
});

test("formatAccuracyComparison shows a positive delta vs the previous run", () => {
  const result = formatAccuracyComparison(
    { run_name: "run2", precision: 0.9, recall: 0.8, map50: 0.85, map50_95: 0.6 },
    { run_name: "run1", precision: 0.7, recall: 0.6, map50: 0.65, map50_95: 0.4 }
  );
  assert.equal(result.runName, "run2");
  assert.equal(result.precisionText, "90.0% (+20.0pp vs previous)");
  assert.equal(result.recallText, "80.0% (+20.0pp vs previous)");
  assert.equal(result.map50Text, "85.0% (+20.0pp vs previous)");
  assert.equal(result.map5095Text, "60.0% (+20.0pp vs previous)");
});

test("formatAccuracyComparison shows a negative delta vs the previous run", () => {
  const result = formatAccuracyComparison(
    { run_name: "run2", precision: 0.5, recall: 0.5, map50: 0.5, map50_95: 0.5 },
    { run_name: "run1", precision: 0.7, recall: 0.7, map50: 0.7, map50_95: 0.7 }
  );
  assert.equal(result.precisionText, "50.0% (-20.0pp vs previous)");
});

test("formatAccuracyComparison omits the delta when there is no previous run", () => {
  const result = formatAccuracyComparison(
    { run_name: "run1", precision: 0.8, recall: 0.7, map50: 0.75, map50_95: 0.5 },
    null
  );
  assert.equal(result.precisionText, "80.0%");
  assert.equal(result.recallText, "70.0%");
});
