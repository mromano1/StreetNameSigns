const test = require("node:test");
const assert = require("node:assert/strict");
const { newestOrderDate } = require("./date-utils.js");

test("newestOrderDate returns the latest order_completed_on_date among signs", () => {
  const signs = [
    { order_completed_on_date: "2021-05-01" },
    { order_completed_on_date: "2024-03-06" },
    { order_completed_on_date: "2023-09-04" },
  ];
  assert.equal(newestOrderDate(signs), "2024-03-06");
});

test("newestOrderDate ignores signs with no date (pre-backfill data)", () => {
  const signs = [
    { order_completed_on_date: null },
    { order_completed_on_date: "2022-01-01" },
    {},
  ];
  assert.equal(newestOrderDate(signs), "2022-01-01");
});

test("newestOrderDate returns null when no sign has a date", () => {
  assert.equal(newestOrderDate([{ order_completed_on_date: null }, {}]), null);
});

test("newestOrderDate returns null for an empty signs list", () => {
  assert.equal(newestOrderDate([]), null);
});
