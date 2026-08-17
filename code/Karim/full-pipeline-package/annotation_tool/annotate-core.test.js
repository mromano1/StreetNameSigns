const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("./annotate-core.js");

test("toCanvasCoords converts a client point to native canvas pixels, correcting for CSS scaling", () => {
  // Canvas is natively 2000x1500 but displayed at 1000x750 (2x CSS scale),
  // positioned with its top-left at (50, 20) in the viewport.
  const result = core.toCanvasCoords(
    /* clientX */ 550, /* clientY */ 320,
    /* rectLeft */ 50, /* rectTop */ 20, /* rectWidth */ 1000, /* rectHeight */ 750,
    /* canvasWidth */ 2000, /* canvasHeight */ 1500
  );
  assert.deepEqual(result, { x: 1000, y: 600 });
});

test("rectFromPoints normalizes a drag into a positive-size box regardless of drag direction", () => {
  const dragUpLeft = core.rectFromPoints({ x: 100, y: 100 }, { x: 40, y: 30 });
  assert.deepEqual(dragUpLeft, { x: 40, y: 30, w: 60, h: 70 });

  const dragDownRight = core.rectFromPoints({ x: 40, y: 30 }, { x: 100, y: 100 });
  assert.deepEqual(dragDownRight, { x: 40, y: 30, w: 60, h: 70 });
});

test("isRealBox rejects boxes smaller than the minimum drag threshold", () => {
  assert.equal(core.isRealBox({ x: 0, y: 0, w: 8, h: 8 }), false);
  assert.equal(core.isRealBox({ x: 0, y: 0, w: 9, h: 9 }), true);
});

test("compassFromHeading rounds a heading in degrees to the nearest 8-point compass label", () => {
  assert.equal(core.compassFromHeading(0), "N");
  assert.equal(core.compassFromHeading(44), "NE");
  assert.equal(core.compassFromHeading(90), "E");
  assert.equal(core.compassFromHeading(180), "S");
  assert.equal(core.compassFromHeading(270), "W");
  assert.equal(core.compassFromHeading(315), "NW");
});

test("compassFromHeading wraps negative and >360 headings the same as content.js", () => {
  assert.equal(core.compassFromHeading(-45), "NW");
  assert.equal(core.compassFromHeading(405), "NE");
});

test("compassFromHeading rounds the boundary between N and NW up to N (wraps to slot 0)", () => {
  // 337.5 rounds to slot 8 (360/45), which wraps to index 0 -- matches
  // content.js's `Math.round(h / 45) % 8` behavior exactly.
  assert.equal(core.compassFromHeading(340), "N");
});

test("compassFromSignLocation classifies real corners, not median/mall/offset placements", () => {
  assert.equal(core.compassFromSignLocation("N/E C"), "NE");
  assert.equal(core.compassFromSignLocation("S/W C"), "SW");
  assert.equal(core.compassFromSignLocation("n/e c"), "NE");
  assert.equal(core.compassFromSignLocation("N C"), "N");
  assert.equal(core.compassFromSignLocation("N CURB"), "N");
  assert.equal(core.compassFromSignLocation("N MALL"), null);
  assert.equal(core.compassFromSignLocation("N WSD"), null);
  assert.equal(core.compassFromSignLocation(""), null);
  assert.equal(core.compassFromSignLocation(null), null);
});

test("groupSignsByCorner buckets signs by compass corner, unclassified under 'other'", () => {
  const signs = [
    { order_number: "A", sign_location: "N/E C" },
    { order_number: "B", sign_location: "N/E C" },
    { order_number: "C", sign_location: "S/W C" },
    { order_number: "D", sign_location: "N MALL" },
  ];
  const groups = core.groupSignsByCorner(signs);
  assert.equal(groups.NE.length, 2);
  assert.equal(groups.SW.length, 1);
  assert.equal(groups.other.length, 1);
});

test("toggleDamage: picking a real category toggles it on, clicking again toggles it off", () => {
  let selected = [];
  selected = core.toggleDamage(selected, "faded");
  assert.deepEqual(selected, ["faded"]);
  selected = core.toggleDamage(selected, "vandalized");
  assert.deepEqual(selected, ["faded", "vandalized"]);
  selected = core.toggleDamage(selected, "faded");
  assert.deepEqual(selected, ["vandalized"]);
});

test("toggleDamage: 'no damage' is exclusive with every real category", () => {
  let selected = ["faded", "vandalized"];
  selected = core.toggleDamage(selected, "no damage");
  assert.deepEqual(selected, ["no damage"]);
});

test("toggleDamage: picking a real category cancels a prior 'no damage'", () => {
  let selected = ["no damage"];
  selected = core.toggleDamage(selected, "hanging");
  assert.deepEqual(selected, ["hanging"]);
});

test("buildRecord assembles the exact documented column set for one annotated box", () => {
  const record = core.buildRecord({
    sourceImage: "10001_000/latest.jpg",
    imageKind: "latest",
    cornerId: "10001_000",
    boxIndex: 0,
    box: { x: 10, y: 20, w: 100, h: 50 },
    imageWidth: 1600,
    imageHeight: 1200,
    matchedSign: { order_number: "ST01", sign_code: "SN-1A", sign_location: "N/E C" },
    damageCategories: ["faded", "vandalized"],
    notes: "hard to read",
    tightCropPath: "10001_000/tight_latest_0.jpg",
    annotatedAt: "2026-07-28T00:00:00.000Z",
  });

  assert.deepEqual(record, {
    source_image: "10001_000/latest.jpg",
    image_kind: "latest",
    corner_id: "10001_000",
    box_index: 0,
    bbox_x: 10,
    bbox_y: 20,
    bbox_w: 100,
    bbox_h: 50,
    image_width: 1600,
    image_height: 1200,
    order_number: "ST01",
    sign_code: "SN-1A",
    sign_location: "N/E C",
    damage_category: "faded;vandalized",
    notes: "hard to read",
    tight_crop_path: "10001_000/tight_latest_0.jpg",
    flagged: "",
    annotated_at: "2026-07-28T00:00:00.000Z",
  });
});

test("buildRecord handles an unmatched box (no SIMS sign picked)", () => {
  const record = core.buildRecord({
    sourceImage: "10001_000/latest.jpg",
    imageKind: "latest",
    cornerId: "10001_000",
    boxIndex: 1,
    box: { x: 1, y: 2, w: 3, h: 4 },
    imageWidth: 1600,
    imageHeight: 1200,
    matchedSign: null,
    damageCategories: ["no damage"],
    notes: "",
    tightCropPath: "",
    annotatedAt: "2026-07-28T00:00:00.000Z",
  });
  assert.equal(record.order_number, "");
  assert.equal(record.sign_code, "");
  assert.equal(record.sign_location, "");
  assert.equal(record.tight_crop_path, "");
  assert.equal(record.flagged, "");
});

test("RECORD_COLUMNS matches the documented, versioned export schema exactly", () => {
  assert.deepEqual(core.RECORD_COLUMNS, [
    "source_image", "image_kind", "corner_id", "box_index",
    "bbox_x", "bbox_y", "bbox_w", "bbox_h", "image_width", "image_height",
    "order_number", "sign_code", "sign_location", "damage_category", "notes",
    "tight_crop_path", "flagged", "annotated_at",
  ]);
});

test("csvEscape quotes values containing commas, quotes, or newlines", () => {
  assert.equal(core.csvEscape("plain"), "plain");
  assert.equal(core.csvEscape("has,comma"), '"has,comma"');
  assert.equal(core.csvEscape('has"quote'), '"has""quote"');
  assert.equal(core.csvEscape("has\nnewline"), '"has\nnewline"');
  assert.equal(core.csvEscape(42), "42");
  assert.equal(core.csvEscape(null), "");
  assert.equal(core.csvEscape(undefined), "");
});

test("toCsv renders the header from RECORD_COLUMNS and one row per record, in column order", () => {
  const records = [
    core.buildRecord({
      sourceImage: "a.jpg", imageKind: "latest", cornerId: "C1", boxIndex: 0,
      box: { x: 1, y: 2, w: 3, h: 4 }, imageWidth: 100, imageHeight: 200,
      matchedSign: { order_number: "O1", sign_code: "SC1", sign_location: "N C" },
      damageCategories: ["faded"], notes: "note, with comma", tightCropPath: "", annotatedAt: "T1",
    }),
  ];
  const csv = core.toCsv(records);
  const lines = csv.trim().split("\n");
  assert.equal(lines[0], core.RECORD_COLUMNS.join(","));
  assert.equal(lines[1], 'a.jpg,latest,C1,0,1,2,3,4,100,200,O1,SC1,N C,faded,"note, with comma",,,T1');
});

test("buildFlaggedRecord produces a minimal record with every box field empty and flagged set", () => {
  const record = core.buildFlaggedRecord({
    sourceImage: "10001_000/latest.jpg",
    imageKind: "latest",
    cornerId: "10001_000",
    annotatedAt: "2026-08-12T00:00:00.000Z",
  });
  assert.deepEqual(record, {
    source_image: "10001_000/latest.jpg",
    image_kind: "latest",
    corner_id: "10001_000",
    box_index: "",
    bbox_x: "", bbox_y: "", bbox_w: "", bbox_h: "",
    image_width: "", image_height: "",
    order_number: "", sign_code: "", sign_location: "",
    damage_category: "", notes: "",
    tight_crop_path: "",
    flagged: "true",
    annotated_at: "2026-08-12T00:00:00.000Z",
  });
});

test("hitTestBox returns 'move' when the point is inside the box body, away from edges", () => {
  const box = { x: 100, y: 100, w: 50, h: 50 };
  assert.equal(core.hitTestBox(box, { x: 125, y: 125 }, 8), "move");
});

test("hitTestBox detects each corner handle within the margin", () => {
  const box = { x: 100, y: 100, w: 50, h: 50 };
  assert.equal(core.hitTestBox(box, { x: 100, y: 100 }, 8), "nw");
  assert.equal(core.hitTestBox(box, { x: 150, y: 100 }, 8), "ne");
  assert.equal(core.hitTestBox(box, { x: 100, y: 150 }, 8), "sw");
  assert.equal(core.hitTestBox(box, { x: 150, y: 150 }, 8), "se");
});

test("hitTestBox detects each edge handle within the margin, away from corners", () => {
  const box = { x: 100, y: 100, w: 50, h: 50 };
  assert.equal(core.hitTestBox(box, { x: 125, y: 100 }, 8), "n");
  assert.equal(core.hitTestBox(box, { x: 125, y: 150 }, 8), "s");
  assert.equal(core.hitTestBox(box, { x: 100, y: 125 }, 8), "w");
  assert.equal(core.hitTestBox(box, { x: 150, y: 125 }, 8), "e");
});

test("hitTestBox returns null when the point is well outside the box", () => {
  const box = { x: 100, y: 100, w: 50, h: 50 };
  assert.equal(core.hitTestBox(box, { x: 0, y: 0 }, 8), null);
});

test("moveBox translates x/y by the given delta, keeping w/h unchanged", () => {
  const box = { x: 100, y: 100, w: 50, h: 30 };
  assert.deepEqual(core.moveBox(box, 10, -5), { x: 110, y: 95, w: 50, h: 30 });
});

test("resizeBox from the 'se' handle moves only the bottom-right corner", () => {
  const box = { x: 100, y: 100, w: 50, h: 50 };
  const resized = core.resizeBox(box, "se", { x: 170, y: 180 });
  assert.deepEqual(resized, { x: 100, y: 100, w: 70, h: 80 });
});

test("resizeBox from the 'nw' handle moves only the top-left corner", () => {
  const box = { x: 100, y: 100, w: 50, h: 50 };
  const resized = core.resizeBox(box, "nw", { x: 80, y: 90 });
  assert.deepEqual(resized, { x: 80, y: 90, w: 70, h: 60 });
});

test("resizeBox from an edge handle only moves that one edge", () => {
  const box = { x: 100, y: 100, w: 50, h: 50 };
  assert.deepEqual(core.resizeBox(box, "e", { x: 200, y: 999 }), { x: 100, y: 100, w: 100, h: 50 });
  assert.deepEqual(core.resizeBox(box, "s", { x: 999, y: 200 }), { x: 100, y: 100, w: 50, h: 100 });
});

test("cursorForHit maps each hit-test result to the matching CSS cursor value", () => {
  assert.equal(core.cursorForHit("move"), "move");
  assert.equal(core.cursorForHit("nw"), "nwse-resize");
  assert.equal(core.cursorForHit("se"), "nwse-resize");
  assert.equal(core.cursorForHit("ne"), "nesw-resize");
  assert.equal(core.cursorForHit("sw"), "nesw-resize");
  assert.equal(core.cursorForHit("n"), "ns-resize");
  assert.equal(core.cursorForHit("s"), "ns-resize");
  assert.equal(core.cursorForHit("e"), "ew-resize");
  assert.equal(core.cursorForHit("w"), "ew-resize");
  assert.equal(core.cursorForHit(null), "crosshair");
});
