const test = require("node:test");
const assert = require("node:assert/strict");
const {
  PHYSICAL_CLASS_NAMES,
  CONF_THRESHOLD,
  computeLetterboxGeometry,
  imageToTensor,
  parseDetections,
} = require("./onnx-predict.js");

test("computeLetterboxGeometry scales a wider-than-tall image to fit width, pads top/bottom", () => {
  // 4x2 source into a 4x4 target: width already fits (scale 1), height needs padding.
  const geom = computeLetterboxGeometry(4, 2, 4);
  assert.equal(geom.scale, 1);
  assert.equal(geom.newWidth, 4);
  assert.equal(geom.newHeight, 2);
  assert.equal(geom.padX, 0);
  assert.equal(geom.padY, 1);
});

test("computeLetterboxGeometry scales a taller-than-wide image to fit height, pads left/right", () => {
  // 2x4 source into a 4x4 target: height already fits (scale 1), width needs padding.
  const geom = computeLetterboxGeometry(2, 4, 4);
  assert.equal(geom.scale, 1);
  assert.equal(geom.newWidth, 2);
  assert.equal(geom.newHeight, 4);
  assert.equal(geom.padX, 1);
  assert.equal(geom.padY, 0);
});

test("computeLetterboxGeometry scales a square image up to exactly fill a larger square target", () => {
  const geom = computeLetterboxGeometry(320, 320, 640);
  assert.equal(geom.scale, 2);
  assert.equal(geom.newWidth, 640);
  assert.equal(geom.newHeight, 640);
  assert.equal(geom.padX, 0);
  assert.equal(geom.padY, 0);
});

test("computeLetterboxGeometry picks the smaller ratio so neither dimension overflows", () => {
  // 1000x500 into 640x640: width ratio 0.64, height ratio 1.28 -- must use 0.64.
  const geom = computeLetterboxGeometry(1000, 500, 640);
  assert.equal(geom.scale, 0.64);
  assert.equal(geom.newWidth, 640);
  assert.equal(geom.newHeight, 320);
  assert.equal(geom.padY, 160);
});

test("imageToTensor on a 2x2 square buffer keeps R/G/B planes contiguous, ordered, and normalized", () => {
  // 2x2 image, row-major: (r0,g0,b0),(r1,g1,b1),(r2,g2,b2),(r3,g3,b3)
  const rgba = new Uint8ClampedArray([
    10, 20, 30, 255,
    40, 50, 60, 255,
    70, 80, 90, 255,
    100, 110, 120, 255,
  ]);
  const tensor = imageToTensor(rgba, 2);
  const f = Math.fround; // tensor is a Float32Array -- compare against float32-rounded expectations
  assert.deepEqual(Array.from(tensor.slice(0, 4)), [f(10 / 255), f(40 / 255), f(70 / 255), f(100 / 255)]);
  assert.deepEqual(Array.from(tensor.slice(4, 8)), [f(20 / 255), f(50 / 255), f(80 / 255), f(110 / 255)]);
  assert.deepEqual(Array.from(tensor.slice(8, 12)), [f(30 / 255), f(60 / 255), f(90 / 255), f(120 / 255)]);
});

test("parseDetections keeps only detections at or above the confidence threshold", () => {
  // Two detections: [x1,y1,x2,y2,conf,cls] rows. Row 0 above threshold (old_design),
  // row 1 below threshold (faded) -- must be filtered out.
  const output = new Float32Array([
    0, 0, 10, 10, 0.9, 0,
    0, 0, 10, 10, 0.1, 1,
  ]);
  const results = parseDetections(output, 2);
  // Float32Array storage rounds 0.9 to its nearest float32 representation.
  assert.deepEqual(results, [{ class_name: "old_design", confidence: Math.fround(0.9) }]);
});

test("parseDetections includes a detection exactly at the threshold", () => {
  const output = new Float32Array([0, 0, 10, 10, CONF_THRESHOLD, 4]);
  const results = parseDetections(output, 1);
  assert.deepEqual(results, [{ class_name: "vandalized", confidence: CONF_THRESHOLD }]);
});

test("parseDetections maps every class id to its name in PHYSICAL_CLASS_NAMES order", () => {
  const rows = PHYSICAL_CLASS_NAMES.map((_, clsId) => [0, 0, 10, 10, 0.5, clsId]).flat();
  const output = new Float32Array(rows);
  const results = parseDetections(output, PHYSICAL_CLASS_NAMES.length);
  assert.deepEqual(
    results.map((r) => r.class_name),
    PHYSICAL_CLASS_NAMES
  );
});

test("parseDetections ignores padding/empty detection slots below threshold", () => {
  // Simulates a fixed 300-row output where only the first row is real.
  const numDetections = 5;
  const output = new Float32Array(numDetections * 6);
  output.set([0, 0, 10, 10, 0.8, 2], 0); // one real bent_damaged detection
  const results = parseDetections(output, numDetections);
  assert.deepEqual(results, [{ class_name: "bent_damaged", confidence: Math.fround(0.8) }]);
});

test("parseDetections skips an unrecognized class id without crashing", () => {
  const output = new Float32Array([0, 0, 10, 10, 0.9, 99]);
  const results = parseDetections(output, 1);
  assert.deepEqual(results, []);
});

test("parseDetections returns an empty array when nothing meets the threshold", () => {
  const output = new Float32Array([0, 0, 10, 10, 0.01, 0]);
  const results = parseDetections(output, 1);
  assert.deepEqual(results, []);
});
