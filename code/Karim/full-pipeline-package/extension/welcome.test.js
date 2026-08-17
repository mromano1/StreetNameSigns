const test = require("node:test");
const assert = require("node:assert/strict");
const { ZIP_AREA_LABELS, summarizeDataExtent, renderDataExtentHtml } = require("./welcome.js");

test("summarizeDataExtent counts corners and dedupes area labels", () => {
  const signsData = {
    zip: ["11237", "11206", "11385"],
    corners: [{}, {}, {}],
  };

  const summary = summarizeDataExtent(signsData, ZIP_AREA_LABELS);

  assert.equal(summary.cornerCount, 3);
  assert.deepEqual(summary.zips, ["11237", "11206", "11385"]);
  assert.deepEqual(summary.areas, ["Bushwick", "Ridgewood/Glendale"]);
});

test("summarizeDataExtent labels an unmapped zip as unlisted area", () => {
  const summary = summarizeDataExtent({ zip: ["99999"], corners: [] }, ZIP_AREA_LABELS);
  assert.deepEqual(summary.areas, ["unlisted area"]);
});

test("summarizeDataExtent handles missing zip/corners keys without crashing", () => {
  const summary = summarizeDataExtent({}, ZIP_AREA_LABELS);
  assert.equal(summary.cornerCount, 0);
  assert.deepEqual(summary.zips, []);
  assert.deepEqual(summary.areas, []);
});

test("renderDataExtentHtml includes corner count, areas, and zip list", () => {
  const html = renderDataExtentHtml({
    cornerCount: 3605,
    areas: ["Bushwick", "South Bronx"],
    zips: ["11237", "10451"],
  });

  assert.match(html, /3,605/);
  assert.match(html, /Bushwick, South Bronx/);
  assert.match(html, /11237, 10451/);
});
