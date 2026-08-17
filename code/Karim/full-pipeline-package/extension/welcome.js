/**
 * Loaded as a plain <script> by welcome.html (see its <script src="welcome.js">
 * tag) and via require() in welcome.test.js -- same CommonJS-guard pattern
 * as date-utils.js / damage-prediction.js / location-freshness.js. NOT part
 * of manifest.json's content_scripts array, so it doesn't share a global
 * scope with content.js's file family -- no collision risk there.
 *
 * Reads the "Data included" section's numbers directly from
 * signs_data.json at page-load time rather than hardcoding them in
 * welcome.html, so this can never drift out of sync with what's actually
 * shipped -- same principle as build_sims_data_hull.py building the
 * coverage shapefile straight from signs_data.json instead of a
 * hand-maintained file.
 */

const ZIP_AREA_LABELS = {
  "11237": "Bushwick", "11206": "Bushwick", "11221": "Bedford-Stuyvesant/Bushwick",
  "11385": "Ridgewood/Glendale",
  "10451": "South Bronx", "10452": "South Bronx", "10454": "South Bronx",
  "10455": "South Bronx", "10456": "South Bronx", "10459": "South Bronx", "10474": "South Bronx",
};

function summarizeDataExtent(signsData, zipAreaLabels) {
  const zips = signsData.zip || [];
  const cornerCount = (signsData.corners || []).length;
  const areas = [...new Set(zips.map((z) => zipAreaLabels[z] || "unlisted area"))];
  return { zips, cornerCount, areas };
}

function renderDataExtentHtml(summary) {
  return (
    `<p><strong>${summary.cornerCount.toLocaleString()}</strong> sign corners loaded, ` +
    `covering <strong>${summary.areas.join(", ")}</strong>.</p>` +
    `<p class="zip-list">Zip codes: ${summary.zips.join(", ")}</p>` +
    `<p>Sign matching only works inside this area -- see "Outside your loaded ` +
    `SIMS data area" in the User Guide.</p>`
  );
}

if (typeof document !== "undefined") {
  fetch("signs_data.json")
    .then((r) => r.json())
    .then((data) => {
      const summary = summarizeDataExtent(data, ZIP_AREA_LABELS);
      document.getElementById("data-extent-body").innerHTML = renderDataExtentHtml(summary);
    })
    .catch(() => {
      document.getElementById("data-extent-body").innerHTML =
        "<p>Could not load signs_data.json to show coverage details.</p>";
    });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { ZIP_AREA_LABELS, summarizeDataExtent, renderDataExtentHtml };
}
