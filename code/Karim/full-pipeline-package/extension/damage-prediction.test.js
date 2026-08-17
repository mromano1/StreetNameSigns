const test = require("node:test");
const assert = require("node:assert/strict");
const { buildDamageGuessPlan } = require("./damage-prediction.js");

test("buildDamageGuessPlan hints an unambiguous class, does not pre-select it", () => {
  const plan = buildDamageGuessPlan([{ class_name: "faded", confidence: 0.82 }]);
  assert.deepEqual(plan.faded, { preselect: false, confidence: 0.82, hint: true });
});

test("buildDamageGuessPlan hints both candidates for an ambiguous class", () => {
  const plan = buildDamageGuessPlan([{ class_name: "old_design", confidence: 0.6 }]);
  assert.deepEqual(plan["white-border"], { preselect: false, confidence: 0.6, hint: true });
  assert.deepEqual(plan["all-caps"], { preselect: false, confidence: 0.6, hint: true });
});

test("buildDamageGuessPlan defaults every known button when there are no predictions", () => {
  const plan = buildDamageGuessPlan([]);
  assert.deepEqual(plan.bent, { preselect: false, confidence: null, hint: false });
  assert.deepEqual(plan.hanging, { preselect: false, confidence: null, hint: false });
});

test("buildDamageGuessPlan handles a null predictions list", () => {
  const plan = buildDamageGuessPlan(null);
  assert.deepEqual(plan.vandalized, { preselect: false, confidence: null, hint: false });
});

test("buildDamageGuessPlan ignores an unrecognized class name without crashing", () => {
  const plan = buildDamageGuessPlan([{ class_name: "something_new", confidence: 0.9 }]);
  assert.deepEqual(plan.faded, { preselect: false, confidence: null, hint: false });
});

test("buildDamageGuessPlan handles multiple unambiguous predictions independently", () => {
  const plan = buildDamageGuessPlan([
    { class_name: "faded", confidence: 0.5 },
    { class_name: "vandalized", confidence: 0.9 },
  ]);
  assert.equal(plan.faded.preselect, false);
  assert.equal(plan.faded.hint, true);
  assert.equal(plan.vandalized.preselect, false);
  assert.equal(plan.vandalized.hint, true);
  assert.equal(plan.bent.preselect, false);
  assert.equal(plan.bent.hint, false);
});
