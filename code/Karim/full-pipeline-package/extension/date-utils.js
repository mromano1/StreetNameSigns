/**
 * Loaded as a plain <script> before content.js (see manifest.json) and via
 * require() in date-utils.test.js (Node's built-in test runner) -- same
 * CommonJS-guard pattern as annotation_tool/annotate-core.js.
 *
 * Lets the live compass HUD show "how recently were the signs near here
 * last worked on," so a manual capturer knows which year of Cyclomedia
 * imagery to check for a sign's pre-replacement (likely damaged) state,
 * instead of flipping through years by hand. Dates come from
 * StreetNameSigns/code/Karim/scripts/03_add_order_dates.py backfilling
 * order_completed_on_date onto signs_data.json -- older data pulls won't
 * have it yet, so this must tolerate missing dates.
 */

function newestOrderDate(signs) {
  const dates = signs
    .map((s) => s.order_completed_on_date)
    .filter((d) => !!d);
  if (!dates.length) return null;
  return dates.reduce((max, d) => (d > max ? d : max), dates[0]);
}

const api = { newestOrderDate };

if (typeof module !== "undefined" && module.exports) {
  module.exports = api;
}
