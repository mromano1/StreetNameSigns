const test = require("node:test");
const assert = require("node:assert/strict");
const { isLocationFresh, MAX_FALLBACK_LOCATION_AGE_MS } = require("./location-freshness.js");

test("isLocationFresh is true for a location recorded just now", () => {
  assert.equal(isLocationFresh(1000, 1000, MAX_FALLBACK_LOCATION_AGE_MS), true);
});

test("isLocationFresh is true right at the age boundary", () => {
  assert.equal(isLocationFresh(1000, 1000 + MAX_FALLBACK_LOCATION_AGE_MS, MAX_FALLBACK_LOCATION_AGE_MS), true);
});

test("isLocationFresh is false just past the age boundary", () => {
  assert.equal(isLocationFresh(1000, 1000 + MAX_FALLBACK_LOCATION_AGE_MS + 1, MAX_FALLBACK_LOCATION_AGE_MS), false);
});

test("isLocationFresh is false for a location recorded minutes ago", () => {
  assert.equal(isLocationFresh(1000, 1000 + 5 * 60 * 1000, MAX_FALLBACK_LOCATION_AGE_MS), false);
});

test("isLocationFresh is false when nothing has ever been recorded", () => {
  assert.equal(isLocationFresh(null, 1000, MAX_FALLBACK_LOCATION_AGE_MS), false);
});
