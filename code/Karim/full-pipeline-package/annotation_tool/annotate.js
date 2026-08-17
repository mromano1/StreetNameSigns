/**
 * DOM wiring for the annotation tool. Thin glue around annotate-core.js's
 * tested pure functions and queue.js's persistence -- this file itself is
 * not unit-tested (no DOM test runner in this project; see annotate-core
 * for the logic that IS tested).
 *
 * Assumes it's served from ML Project's root (e.g. `python -m http.server`
 * run in `ML Project/`, opening http://localhost:8000/annotation_tool/),
 * so that both this tool and ../data/cyclomedia_panoramas/ (images +
 * fetch_manifest.json, written by fetch_cyclomedia_panoramas.py) and
 * ../extension/signs_data.json are reachable under one origin -- serving
 * from this folder alone can't reach either.
 */
(function () {
  const DATASETS_URL = "/data/cyclomedia_panoramas/datasets.json";
  const DEFAULT_MANIFEST_URL = "/data/cyclomedia_panoramas/fetch_manifest.json";
  const DEFAULT_SIGNS_URL = "/extension/signs_data.json";
  const SELECTED_DATASET_KEY = "ssc_selected_dataset";
  const TIGHT_CROP_URL = "http://127.0.0.1:8766/tight-crop";
  const PHYSICAL_PREDICT_URL = "http://127.0.0.1:8765/predict";

  // manifestUrl/imageBase re-derived from the selected dataset by
  // selectDataset() -- IMAGE_BASE is just the manifest's own directory, so
  // job.path (relative to wherever fetch_cyclomedia_panoramas.py's
  // --output-dir was) resolves under the right collection's folder.
  // signsUrlByManifest comes from datasets.json's "signs" field -- each
  // pulled collection has its own corner_ids, so the SIMS data it matches
  // against has to switch with it too, not stay pinned to one file.
  let manifestUrl = DEFAULT_MANIFEST_URL;
  let imageBase = DEFAULT_MANIFEST_URL.replace(/[^/]*$/, "");
  let signsUrlByManifest = { [DEFAULT_MANIFEST_URL]: DEFAULT_SIGNS_URL };

  const datasetSelectEl = document.getElementById("ssc-dataset-select");
  const canvas = document.getElementById("ssc-canvas");
  const ctx = canvas.getContext("2d");
  const canvasWrap = document.getElementById("ssc-canvas-wrap");
  const boxListEl = document.getElementById("ssc-box-list");
  const boxEditorEl = document.getElementById("ssc-box-editor");
  const progressEl = document.getElementById("ssc-progress");
  const zoomLevelEl = document.getElementById("ssc-zoom-level");
  const headingEl = document.getElementById("ssc-heading");
  const tightCropPreviewEl = document.getElementById("ssc-tight-crop-preview");

  // Zoom scales the canvas's CSS display size only -- canvas.width/height
  // (the drawing buffer, set to the image's native resolution in
  // goToImage) never change, so stored box coordinates (already in that
  // same space via toCanvasCoords reading the live bounding rect) stay
  // correct at any zoom level with no extra conversion.
  const ZOOM_STEP = 1.25;
  const ZOOM_MAX_NATURAL_MULT = 6; // cap: 6x the image's native pixel width

  let cornersById = {};
  let img = new Image();
  let boxes = []; // { x, y, w, h, matchedSign, damages: [], notes }
  let activeBoxIndex = null;
  let dragStart = null;
  let dragMode = null; // null | "new" | "move" | "resize"
  let dragHandle = null; // resize handle string, only set when dragMode === "resize"
  let dragOrigin = null; // canvas-space point where the current drag started
  let dragOriginalBox = null; // snapshot of the active box before the current drag
  const HANDLE_MARGIN = 8;

  function signsForJob(job) {
    // "latest"/"prior_to_replacement" jobs carry a single corner_id;
    // "center"/"side" jobs (multi-angle intersection capture) carry
    // corner_ids (plural) instead, since one shot can show signs from
    // every corner in that intersection -- merge all of them so the
    // sign-picker offers every candidate, not just the first corner's.
    if (job.corner_id) {
      const corner = cornersById[job.corner_id];
      return corner ? corner.signs || [] : [];
    }
    if (job.corner_ids) {
      return job.corner_ids.flatMap((id) => {
        const corner = cornersById[id];
        return corner ? corner.signs || [] : [];
      });
    }
    return [];
  }

  function redraw() {
    ctx.drawImage(img, 0, 0);
    boxes.forEach((b, i) => {
      ctx.strokeStyle = i === activeBoxIndex ? "#4a9eff" : "#ff3b30";
      ctx.lineWidth = 3;
      ctx.strokeRect(b.x, b.y, b.w, b.h);
    });
  }

  function renderBoxList() {
    boxListEl.innerHTML = "";
    boxes.forEach((b, i) => {
      const li = document.createElement("li");
      li.className = i === activeBoxIndex ? "ssc-active" : "";
      const label = b.matchedSign ? b.matchedSign.sign_description : "(unmatched)";
      const damage = b.damages.length ? b.damages.join(";") + (b.suggested ? " (suggested)" : "") : "(untagged)";
      li.innerHTML = `Box ${i + 1}: ${label} - ${damage} <span class="ssc-box-remove">&times;</span>`;
      li.addEventListener("click", (e) => {
        if (e.target.classList.contains("ssc-box-remove")) {
          boxes.splice(i, 1);
          activeBoxIndex = null;
          renderBoxList();
          renderEditor();
          redraw();
          return;
        }
        activeBoxIndex = i;
        renderBoxList();
        renderEditor();
        redraw();
        updateTightCropPreview();
      });
      boxListEl.appendChild(li);
    });
  }

  const DAMAGE_VALUES = [
    "missing", "bent", "hanging", "faded", "vandalized",
    "wrong-direction", "white-border", "all-caps", "no damage",
  ];

  function renderEditor() {
    if (activeBoxIndex === null || !boxes[activeBoxIndex]) {
      boxEditorEl.innerHTML = '<p id="ssc-no-box">Drag a box on the image, or select one above.</p>';
      return;
    }
    const box = boxes[activeBoxIndex];
    const job = Queue.current();
    const groups = groupSignsByCorner(signsForJob(job));

    let optionsHtml = '<option value="">-- no SIMS match --</option>';
    Object.keys(groups).forEach((compass) => {
      optionsHtml += `<optgroup label="${compass}">`;
      groups[compass].forEach((s, idx) => {
        const value = `${compass}:${idx}`;
        const selected = box.matchedSign === s ? "selected" : "";
        optionsHtml += `<option value="${value}" ${selected}>${s.sign_description} (${s.sign_code})</option>`;
      });
      optionsHtml += "</optgroup>";
    });

    boxEditorEl.innerHTML = `
      <label>Matched SIMS sign</label>
      <select id="ssc-sign-select">${optionsHtml}</select>
      <label>Damage category</label>
      <div id="ssc-damage-buttons" class="ssc-btn-group">
        ${DAMAGE_VALUES.map((v) => {
          const selected = box.damages.includes(v);
          const cls = [selected ? "ssc-selected" : "", selected && box.suggested ? "ssc-suggested" : ""].join(" ");
          return `<button type="button" data-val="${v}" class="${cls}">${v}</button>`;
        }).join("")}
      </div>
      <label>Notes</label>
      <textarea id="ssc-notes" rows="2">${box.notes || ""}</textarea>
    `;

    boxEditorEl.querySelector("#ssc-sign-select").addEventListener("change", (e) => {
      const val = e.target.value;
      if (!val) {
        box.matchedSign = null;
        return;
      }
      const [compass, idx] = val.split(":");
      box.matchedSign = groups[compass][parseInt(idx, 10)];
      renderBoxList();
    });

    boxEditorEl.querySelectorAll("#ssc-damage-buttons button").forEach((b) => {
      b.addEventListener("click", () => {
        box.damages = toggleDamage(box.damages, b.dataset.val);
        box.suggested = false;
        renderEditor();
        renderBoxList();
      });
    });

    boxEditorEl.querySelector("#ssc-notes").addEventListener("input", (e) => {
      box.notes = e.target.value;
    });
  }

  canvas.addEventListener("mousedown", (e) => {
    const r = canvas.getBoundingClientRect();
    const p = toCanvasCoords(e.clientX, e.clientY, r.left, r.top, r.width, r.height, canvas.width, canvas.height);
    const active = activeBoxIndex !== null ? boxes[activeBoxIndex] : null;
    const hit = active ? hitTestBox(active, p, HANDLE_MARGIN) : null;

    if (hit === "move") {
      dragMode = "move";
      dragOrigin = p;
      dragOriginalBox = { ...active };
    } else if (hit) {
      dragMode = "resize";
      dragHandle = hit;
      dragOriginalBox = { ...active };
    } else {
      dragMode = "new";
      dragStart = p;
    }
  });

  canvas.addEventListener("mousemove", (e) => {
    const r = canvas.getBoundingClientRect();
    const p = toCanvasCoords(e.clientX, e.clientY, r.left, r.top, r.width, r.height, canvas.width, canvas.height);

    if (dragMode === "move") {
      const box = boxes[activeBoxIndex];
      const moved = moveBox(dragOriginalBox, p.x - dragOrigin.x, p.y - dragOrigin.y);
      Object.assign(box, moved);
      redraw();
      return;
    }
    if (dragMode === "resize") {
      const box = boxes[activeBoxIndex];
      Object.assign(box, resizeBox(dragOriginalBox, dragHandle, p));
      redraw();
      return;
    }
    if (dragMode === "new") {
      if (!dragStart) return;
      const rect = rectFromPoints(dragStart, p);
      redraw();
      ctx.strokeStyle = "#ff3b30";
      ctx.lineWidth = 3;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      return;
    }

    const active = activeBoxIndex !== null ? boxes[activeBoxIndex] : null;
    const hit = active ? hitTestBox(active, p, HANDLE_MARGIN) : null;
    canvas.style.cursor = cursorForHit(hit);
  });

  window.addEventListener("mouseup", (e) => {
    if (dragMode === "move" || dragMode === "resize") {
      const box = boxes[activeBoxIndex];
      const editedIndex = activeBoxIndex;
      dragMode = null;
      dragHandle = null;
      dragOriginalBox = null;
      box.tightCropPath = null;
      box.tightCropDataUrl = null;
      box.suggested = false;
      renderBoxList();
      updateTightCropPreview();
      requestTightCropAndSuggestion(box, editedIndex);
      redraw();
      return;
    }
    if (dragMode === "new") {
      if (!dragStart) return;
      const r = canvas.getBoundingClientRect();
      const p = toCanvasCoords(e.clientX, e.clientY, r.left, r.top, r.width, r.height, canvas.width, canvas.height);
      const rect = rectFromPoints(dragStart, p);
      dragStart = null;
      dragMode = null;
      if (isRealBox(rect)) {
        boxes.push({ ...rect, matchedSign: null, damages: [], notes: "", suggested: false, tightCropPath: null });
        activeBoxIndex = boxes.length - 1;
        renderBoxList();
        renderEditor();
        updateTightCropPreview();
        requestTightCropAndSuggestion(boxes[activeBoxIndex], activeBoxIndex);
      }
      redraw();
    }
  });

  function saveCurrentImage() {
    const job = Queue.current();
    if (!job) return;
    const untagged = boxes.filter((b) => b.damages.length === 0);
    if (untagged.length) {
      alert(`${untagged.length} box(es) have no damage category selected. Tag every box before saving.`);
      return;
    }
    const annotatedAt = new Date().toISOString();
    const records = boxes.map((b, i) =>
      buildRecord({
        sourceImage: job.path,
        imageKind: job.image_kind,
        // "latest"/"prior_to_replacement" jobs carry corner_id; "center"/
        // "side" jobs (multi-angle intersection capture) carry
        // intersection_id instead (see signsForJob above) -- fall back to
        // it so the exported CSV shows a meaningful value instead of a
        // blank/undefined corner_id for those rows.
        cornerId: job.corner_id || job.intersection_id || "",
        boxIndex: i,
        box: { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.w), h: Math.round(b.h) },
        imageWidth: img.naturalWidth,
        imageHeight: img.naturalHeight,
        matchedSign: b.matchedSign,
        damageCategories: b.damages,
        notes: b.notes,
        tightCropPath: b.tightCropPath,
        annotatedAt,
      })
    );
    Queue.addRecords(records);
    goToImage(Queue.next());
  }

  function base64ToBlob(base64, mime) {
    const bytes = atob(base64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    return new Blob([arr], { type: mime });
  }

  function updateTightCropPreview() {
    const box = activeBoxIndex !== null ? boxes[activeBoxIndex] : null;
    if (box && box.tightCropDataUrl) {
      tightCropPreviewEl.src = box.tightCropDataUrl;
      tightCropPreviewEl.classList.add("ssc-visible");
    } else {
      tightCropPreviewEl.src = "";
      tightCropPreviewEl.classList.remove("ssc-visible");
    }
  }

  // Fires on every box create/move/resize. Never blocks the UI -- the box
  // is already visible and editable before this resolves. Guards every
  // continuation against the box having been deleted or the image having
  // changed (via boxes.includes(box), not index equality -- an index can
  // point at a *different* box after another box earlier in the array was
  // deleted, so checking identity is the only way to avoid attaching a
  // stale response to the wrong box).
  async function requestTightCropAndSuggestion(box, boxIndexAtRequestTime) {
    const job = Queue.current();
    if (!job || !box) return;
    try {
      const cropResp = await fetch(TIGHT_CROP_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // job.corner_id is undefined for "center"/"side" jobs (see
          // signsForJob above), which JSON.stringify drops entirely,
          // triggering a 422 from the server's required corner_id field
          // instead of a clean "no job found". Falling back to
          // intersection_id keeps this a well-formed request that still
          // correctly fails to find a match (tight_crop_lib.find_job looks
          // up strictly by corner_id -- extending that lookup to
          // intersection_id/corner_ids is a deliberate non-goal, see
          // docs/superpowers/specs/2026-08-14-multi-angle-intersection-
          // capture-design.md) -- same clean 404 this already produces for
          // corner_id="", not a new failure mode.
          corner_id: job.corner_id || job.intersection_id || "",
          image_kind: job.image_kind,
          box_index: boxIndexAtRequestTime,
          box: { x: box.x, y: box.y, w: box.w, h: box.h },
        }),
      });
      if (!cropResp.ok || !boxes.includes(box)) return;
      const { path, image_base64 } = await cropResp.json();
      box.tightCropPath = path;
      box.tightCropDataUrl = `data:image/jpeg;base64,${image_base64}`;
      if (boxes[activeBoxIndex] === box) updateTightCropPreview();

      const blob = base64ToBlob(image_base64, "image/jpeg");
      const fd = new FormData();
      fd.append("file", blob, "crop.jpg");
      const predictResp = await fetch(PHYSICAL_PREDICT_URL, { method: "POST", body: fd });
      if (!predictResp.ok || !boxes.includes(box) || box.damages.length > 0) return;
      const { classes } = await predictResp.json();
      if (classes && classes.length > 0) {
        box.damages = [classes[0].class_name];
        box.suggested = true;
        renderBoxList();
        if (boxes[activeBoxIndex] === box) renderEditor();
      }
    } catch (e) {
      console.warn("Tight-crop/damage-suggestion unavailable:", e);
    }
  }

  function updateProgress() {
    const job = Queue.current();
    const total = Queue.total();
    const idx = Queue.getIndex();
    const annotated = job ? Queue.isAnnotated(job.path) : false;
    progressEl.textContent = `${idx + 1} / ${total}${annotated ? " (already annotated)" : ""}`;
  }

  function updateHeading() {
    const job = Queue.current();
    if (!job || typeof job.heading !== "number") {
      headingEl.textContent = "";
      return;
    }
    headingEl.textContent = `Camera heading: ${compassFromHeading(job.heading)} (${Math.round(job.heading)}°)`;
  }

  function updateZoomLabel() {
    if (!img.naturalWidth) return;
    const rect = canvas.getBoundingClientRect();
    zoomLevelEl.textContent = Math.round((rect.width / img.naturalWidth) * 100) + "%";
  }

  function resetZoom() {
    canvas.style.width = "";
    canvas.style.maxWidth = "100%";
    updateZoomLabel();
  }

  function zoomIn() {
    if (!img.naturalWidth) return;
    const rect = canvas.getBoundingClientRect();
    const maxWidth = img.naturalWidth * ZOOM_MAX_NATURAL_MULT;
    const newWidth = Math.min(rect.width * ZOOM_STEP, maxWidth);
    canvas.style.maxWidth = "none";
    canvas.style.width = newWidth + "px";
    updateZoomLabel();
  }

  function zoomOut() {
    if (!img.naturalWidth) return;
    const rect = canvas.getBoundingClientRect();
    const fitWidth = Math.min(canvasWrap.clientWidth, img.naturalWidth);
    const newWidth = rect.width / ZOOM_STEP;
    if (newWidth <= fitWidth) {
      resetZoom();
    } else {
      canvas.style.width = newWidth + "px";
      updateZoomLabel();
    }
  }

  function goToImage(index) {
    Queue.setIndex(index);
    const job = Queue.current();
    boxes = [];
    activeBoxIndex = null;
    updateTightCropPreview();
    if (!job) {
      progressEl.textContent = "No images to annotate.";
      headingEl.textContent = "";
      return;
    }
    img = new Image();
    img.onload = () => {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      resetZoom();
      redraw();
    };
    img.src = imageBase + job.path;
    renderBoxList();
    renderEditor();
    updateProgress();
    updateHeading();
  }

  document.getElementById("ssc-save").addEventListener("click", saveCurrentImage);
  document.getElementById("ssc-prev").addEventListener("click", () => goToImage(Queue.getIndex() - 1));
  document.getElementById("ssc-next").addEventListener("click", () => goToImage(Queue.getIndex() + 1));
  document.getElementById("ssc-zoom-in").addEventListener("click", zoomIn);
  document.getElementById("ssc-zoom-out").addEventListener("click", zoomOut);
  canvasWrap.addEventListener(
    "wheel",
    (e) => {
      if (!img.naturalWidth) return;
      e.preventDefault();

      if (e.deltaX !== 0) {
        canvasWrap.scrollLeft += e.deltaX;
      }
      if (e.deltaY === 0) return;

      const beforeRect = canvas.getBoundingClientRect();
      const fracX = (e.clientX - beforeRect.left) / beforeRect.width;
      const fracY = (e.clientY - beforeRect.top) / beforeRect.height;
      const oldWidth = beforeRect.width;

      if (e.deltaY < 0) {
        const maxWidth = img.naturalWidth * ZOOM_MAX_NATURAL_MULT;
        const newWidth = Math.min(oldWidth * ZOOM_STEP, maxWidth);
        canvas.style.maxWidth = "none";
        canvas.style.width = newWidth + "px";
      } else {
        const fitWidth = Math.min(canvasWrap.clientWidth, img.naturalWidth);
        const newWidth = oldWidth / ZOOM_STEP;
        if (newWidth <= fitWidth) {
          resetZoom();
        } else {
          canvas.style.width = newWidth + "px";
        }
      }
      updateZoomLabel();

      const afterRect = canvas.getBoundingClientRect();
      const desiredLeft = e.clientX - fracX * afterRect.width;
      const desiredTop = e.clientY - fracY * afterRect.height;
      canvasWrap.scrollLeft += afterRect.left - desiredLeft;
      canvasWrap.scrollTop += afterRect.top - desiredTop;
    },
    { passive: false }
  );
  document.getElementById("ssc-export").addEventListener("click", () => {
    const csv = toCsv(Queue.getRecords());
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `annotations_${Date.now()}.csv`;
    a.click();
  });

  // Ctrl/Cmd+Enter saves the current image without reaching for the mouse.
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") saveCurrentImage();
  });

  // Missing/absent signs file (a collection with no signs_data.json
  // generated for it yet) means matching is simply unavailable, not an
  // error -- goes quiet (empty cornersById, every box shows "no SIMS
  // match") rather than failing init() or silently reusing a mismatched
  // dataset's corner_ids.
  async function loadSignsData(url) {
    if (!url) {
      cornersById = {};
      return;
    }
    try {
      // no-store: same staleness reason as queue.js's manifest fetch --
      // signs_data.json gets regenerated during a work session too.
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) {
        console.warn(`No SIMS data at ${url} (${resp.status}) -- matching disabled for this dataset.`);
        cornersById = {};
        return;
      }
      const signsData = await resp.json();
      cornersById = Object.fromEntries((signsData.corners || []).map((c) => [c.corner_id, c]));
    } catch (e) {
      console.warn(`Failed to load SIMS data from ${url}:`, e);
      cornersById = {};
    }
  }

  // Switches to a different pulled dataset/neighborhood collection: reloads
  // the queue against its manifest, re-derives imageBase from that
  // manifest's own folder, reloads that collection's own SIMS data (see
  // loadSignsData), and jumps to wherever that dataset's progress
  // (per-dataset, via queue.js's indexKey) last left off.
  async function selectDataset(url) {
    manifestUrl = url;
    imageBase = url.replace(/[^/]*$/, "");
    localStorage.setItem(SELECTED_DATASET_KEY, url);
    await Queue.load(manifestUrl, manifestUrl === DEFAULT_MANIFEST_URL);
    await loadSignsData(signsUrlByManifest[url]);
    goToImage(Queue.getIndex());
  }

  async function populateDatasetDropdown() {
    let datasets;
    try {
      // no-store: same staleness reason as the manifest/signs_data fetches
      // -- list_panorama_datasets.py can be re-run mid-session after a new
      // pull, and a stale cached copy would hide the new collection.
      const resp = await fetch(DATASETS_URL, { cache: "no-store" });
      datasets = resp.ok ? (await resp.json()).datasets || [] : [];
    } catch (e) {
      datasets = [];
    }
    if (datasets.length === 0) {
      // datasets.json missing or empty (e.g. list_panorama_datasets.py
      // never run) -- fall back to the single hardcoded default manifest
      // rather than leaving the dropdown empty/broken.
      datasets = [{ label: "original", manifest: DEFAULT_MANIFEST_URL, signs: DEFAULT_SIGNS_URL }];
    }

    signsUrlByManifest = Object.fromEntries(datasets.map((d) => [d.manifest, d.signs || null]));

    datasetSelectEl.innerHTML = datasets
      .map((d) => `<option value="${d.manifest}">${d.label}</option>`)
      .join("");

    const remembered = localStorage.getItem(SELECTED_DATASET_KEY);
    const initial = datasets.some((d) => d.manifest === remembered)
      ? remembered
      : datasets[0].manifest;
    datasetSelectEl.value = initial;
    manifestUrl = initial;
    imageBase = initial.replace(/[^/]*$/, "");

    datasetSelectEl.addEventListener("change", (e) => {
      selectDataset(e.target.value).catch((err) => {
        progressEl.textContent = "Failed to load: " + err.message;
      });
    });
  }

  async function init() {
    await populateDatasetDropdown();
    await Queue.load(manifestUrl, manifestUrl === DEFAULT_MANIFEST_URL);
    await loadSignsData(signsUrlByManifest[manifestUrl]);
    goToImage(Queue.getIndex());
  }

  init().catch((err) => {
    progressEl.textContent = "Failed to load: " + err.message;
  });
})();
