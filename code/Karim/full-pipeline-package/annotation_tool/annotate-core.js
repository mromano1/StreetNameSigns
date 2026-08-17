/**
 * Pure, DOM-free logic for the offline annotation tool. Loaded as a plain
 * <script> in the browser (annotate.js calls these as globals) and via
 * require() in annotate-core.test.js (Node's built-in test runner) -- the
 * CommonJS export guard at the bottom is a no-op in the browser, where
 * `module` doesn't exist.
 *
 * Most of this is a faithful, DOM-free port of extension/content.js's
 * proven matching/compass logic (toCanvasCoords, compassFromSignLocation,
 * groupSignsByCorner, the damage-button exclusivity rule) -- see that
 * file's comments for the NYC DOT sign_location vocabulary and the
 * heading/compass conventions this is based on. Only buildRecord/
 * RECORD_COLUMNS/toCsv are genuinely new: this tool persists REAL bounding
 * box geometry per box (content.js discarded its crop rect after cropping),
 * and supports multiple boxes per image instead of one crop per capture.
 */

const MIN_DRAG_PX = 8; // matches content.js's `rect.w > 8 && rect.h > 8` real-selection threshold

function toCanvasCoords(clientX, clientY, rectLeft, rectTop, rectWidth, rectHeight, canvasWidth, canvasHeight) {
  const scaleX = canvasWidth / rectWidth;
  const scaleY = canvasHeight / rectHeight;
  return {
    x: (clientX - rectLeft) * scaleX,
    y: (clientY - rectTop) * scaleY,
  };
}

function rectFromPoints(start, point) {
  return {
    x: Math.min(start.x, point.x),
    y: Math.min(start.y, point.y),
    w: Math.abs(point.x - start.x),
    h: Math.abs(point.y - start.y),
  };
}

function isRealBox(rect) {
  return rect.w > MIN_DRAG_PX && rect.h > MIN_DRAG_PX;
}

function hitTestBox(box, point, margin) {
  const left = box.x, right = box.x + box.w, top = box.y, bottom = box.y + box.h;
  const nearLeft = Math.abs(point.x - left) <= margin;
  const nearRight = Math.abs(point.x - right) <= margin;
  const nearTop = Math.abs(point.y - top) <= margin;
  const nearBottom = Math.abs(point.y - bottom) <= margin;
  const withinX = point.x >= left - margin && point.x <= right + margin;
  const withinY = point.y >= top - margin && point.y <= bottom + margin;

  if (nearTop && nearLeft) return "nw";
  if (nearTop && nearRight) return "ne";
  if (nearBottom && nearLeft) return "sw";
  if (nearBottom && nearRight) return "se";
  if (nearTop && withinX) return "n";
  if (nearBottom && withinX) return "s";
  if (nearLeft && withinY) return "w";
  if (nearRight && withinY) return "e";
  if (point.x >= left && point.x <= right && point.y >= top && point.y <= bottom) return "move";
  return null;
}

function moveBox(box, dx, dy) {
  return { x: box.x + dx, y: box.y + dy, w: box.w, h: box.h };
}

function resizeBox(box, handle, point) {
  let left = box.x, top = box.y, right = box.x + box.w, bottom = box.y + box.h;
  if (handle.includes("w")) left = point.x;
  if (handle.includes("e")) right = point.x;
  if (handle.includes("n")) top = point.y;
  if (handle.includes("s")) bottom = point.y;
  return rectFromPoints({ x: left, y: top }, { x: right, y: bottom });
}

function cursorForHit(hit) {
  switch (hit) {
    case "move": return "move";
    case "nw": case "se": return "nwse-resize";
    case "ne": case "sw": return "nesw-resize";
    case "n": case "s": return "ns-resize";
    case "e": case "w": return "ew-resize";
    default: return "crosshair";
  }
}

function compassFromSignLocation(signLocation) {
  const s = (signLocation || "").trim().toUpperCase();
  let m = s.match(/^([NS])\/([EW])\s*C(URB)?\b/);
  if (m) return m[1] + m[2];
  m = s.match(/^([NSEW])\s*C(URB)?\b/);
  if (m) return m[1];
  return null;
}

const COMPASS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

// Same rounding logic as extension/content.js's compassGuessFromHeading():
// the compass point closest to the camera's yaw when the panorama was
// rendered. This is a display label for "which way was the camera facing"
// (fetch_cyclomedia_panoramas.py writes `heading` into each manifest job),
// not the sign-location classification compassFromSignLocation does above.
function compassFromHeading(heading) {
  const h = ((heading % 360) + 360) % 360;
  return COMPASS_8[Math.round(h / 45) % 8];
}

function groupSignsByCorner(signs) {
  const groups = {};
  for (const s of signs) {
    const compass = compassFromSignLocation(s.sign_location) || "other";
    if (!groups[compass]) groups[compass] = [];
    groups[compass].push(s);
  }
  return groups;
}

function toggleDamage(selected, val) {
  if (val === "no damage") {
    return ["no damage"];
  }
  let next = selected.includes("no damage") ? [] : selected.slice();
  if (next.includes(val)) {
    next = next.filter((d) => d !== val);
  } else {
    next.push(val);
  }
  return next;
}

const RECORD_COLUMNS = [
  "source_image", "image_kind", "corner_id", "box_index",
  "bbox_x", "bbox_y", "bbox_w", "bbox_h", "image_width", "image_height",
  "order_number", "sign_code", "sign_location", "damage_category", "notes",
  "tight_crop_path", "flagged", "annotated_at",
];

function buildRecord({
  sourceImage, imageKind, cornerId, boxIndex, box, imageWidth, imageHeight,
  matchedSign, damageCategories, notes, tightCropPath, annotatedAt,
}) {
  return {
    source_image: sourceImage,
    image_kind: imageKind,
    corner_id: cornerId,
    box_index: boxIndex,
    bbox_x: box.x,
    bbox_y: box.y,
    bbox_w: box.w,
    bbox_h: box.h,
    image_width: imageWidth,
    image_height: imageHeight,
    order_number: matchedSign ? matchedSign.order_number : "",
    sign_code: matchedSign ? matchedSign.sign_code : "",
    sign_location: matchedSign ? matchedSign.sign_location : "",
    damage_category: damageCategories.join(";"),
    notes: notes || "",
    tight_crop_path: tightCropPath || "",
    flagged: "",
    annotated_at: annotatedAt,
  };
}

function buildFlaggedRecord({ sourceImage, imageKind, cornerId, annotatedAt }) {
  return {
    source_image: sourceImage,
    image_kind: imageKind,
    corner_id: cornerId,
    box_index: "",
    bbox_x: "", bbox_y: "", bbox_w: "", bbox_h: "",
    image_width: "", image_height: "",
    order_number: "", sign_code: "", sign_location: "",
    damage_category: "", notes: "",
    tight_crop_path: "",
    flagged: "true",
    annotated_at: annotatedAt,
  };
}

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const s = String(value);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function toCsv(records) {
  const lines = [RECORD_COLUMNS.join(",")];
  for (const record of records) {
    lines.push(RECORD_COLUMNS.map((col) => csvEscape(record[col])).join(","));
  }
  return lines.join("\n") + "\n";
}

const api = {
  toCanvasCoords,
  rectFromPoints,
  isRealBox,
  hitTestBox,
  moveBox,
  resizeBox,
  cursorForHit,
  compassFromSignLocation,
  compassFromHeading,
  groupSignsByCorner,
  toggleDamage,
  RECORD_COLUMNS,
  buildRecord,
  buildFlaggedRecord,
  csvEscape,
  toCsv,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = api;
}
