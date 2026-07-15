(function () {
  const BTN_ID = 'ssc-launch-btn';
  if (document.getElementById(BTN_ID)) return; // avoid double-inject on SPA route changes

  let signsData = null;

  function loadSignsData() {
    if (signsData) return Promise.resolve(signsData);
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: 'get_signs_data' }, (resp) => {
        if (resp && resp.ok) {
          signsData = resp.data;
          resolve(signsData);
        } else {
          resolve(null);
        }
      });
    });
  }

  function parseLocationFromUrl() {
    // Matches .../@40.7509,-73.9807,3a,75y,120h,90t/...
    const m = window.location.href.match(/@(-?\d+\.\d+),(-?\d+\.\d+),.*?(\d+(?:\.\d+)?)h/);
    if (!m) return null;
    return { lat: parseFloat(m[1]), lon: parseFloat(m[2]), heading: parseFloat(m[3]) };
  }

  const MANHATTAN_GRID_OFFSET = 29; // degrees east of true north that the avenues run

  function toGridHeading(trueHeading) {
    return ((trueHeading - MANHATTAN_GRID_OFFSET) % 360 + 360) % 360;
  }

  function gridCompassLabel(h) {
    const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    return dirs[Math.round(h / 45) % 8];
  }

  const COMPASS_POINTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

  function makeCompassHud() {
    const tickHtml = COMPASS_POINTS.map(
      (pt) =>
        `<div class="ssc-compass-tick ssc-compass-tick-${pt.toLowerCase()}${pt === 'N' ? ' ssc-compass-tick-primary' : ''}">${pt}</div>`
    ).join('');

    const hud = document.createElement('div');
    hud.id = 'ssc-compass';
    hud.title = 'Heading relative to the Manhattan street grid, not true north';
    hud.innerHTML = `
      <div class="ssc-compass-dial">
        ${tickHtml}
        <div class="ssc-compass-needle"></div>
      </div>
      <div class="ssc-compass-label">grid --</div>
    `;
    document.body.appendChild(hud);

    const needle = hud.querySelector('.ssc-compass-needle');
    const label = hud.querySelector('.ssc-compass-label');

    function update() {
      const loc = parseLocationFromUrl();
      if (!loc) {
        hud.style.display = 'none';
        return;
      }
      hud.style.display = 'flex';
      const gridHeading = toGridHeading(loc.heading);
      needle.style.transform = `rotate(${gridHeading}deg)`;
      label.textContent = `grid ${gridCompassLabel(gridHeading)}`;
    }
    update();
    setInterval(update, 400);
  }

  function cleanStreetName(s) {
    return (s || '').replace(/\s+/g, ' ').trim();
  }

  const COMPASS_LABELS = {
    N: 'N corner', NE: 'NE corner', E: 'E corner', SE: 'SE corner',
    S: 'S corner', SW: 'SW corner', W: 'W corner', NW: 'NW corner',
  };

  function compassFromSignLocation(signLocation) {
    // Per the NYC DOT SIMS data dictionary, sign_location distinguishes actual
    // "Corner" placements ("N/E C" = Northeast Corner, "N C"/"N CURB" = North Corner)
    // from median/mall/apex/island placements ("N CML", "N MALL", "E APEX", "W ISL")
    // and offset-from-intersection placements ("N WSD" = north of the intersection,
    // on the west side; "E SSD" = east of the intersection, on the south side).
    // Only real corners map to a compass direction here -- everything else isn't a
    // "which corner" answer at all, so it's left unclassified (falls to 'other').
    const s = (signLocation || '').trim().toUpperCase();
    // diagonal corner: "N/E C", "S/W C"
    let m = s.match(/^([NS])\/([EW])\s*C(URB)?\b/);
    if (m) return m[1] + m[2];
    // single-cardinal corner: "N C", "N CURB", "E C", "W CURB"
    m = s.match(/^([NSEW])\s*C(URB)?\b/);
    if (m) return m[1];
    return null;
  }

  const COMPASS_8 = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

  function compassGuessFromHeading(heading) {
    // heading = compass direction you're facing; treat the corner "ahead of you" as
    // whichever of the 8 compass points that heading falls closest to. A rough guess,
    // meant to pre-select a default, not to be authoritative.
    const h = ((heading % 360) + 360) % 360;
    return COMPASS_8[Math.round(h / 45) % 8];
  }

  // Lookup table mapping every 2-degree heading step (0-358) to a compass quadrant,
  // for the manual override input -- same quadrant logic as compassGuessFromHeading,
  // just pre-computed as a table since headings typed by hand should resolve exactly
  // the same way the automatic guess does.
  const DEGREE_TABLE = [];
  for (let d = 0; d < 360; d += 2) {
    DEGREE_TABLE.push({ deg: d, corner: compassGuessFromHeading(d) });
  }

  function cornerFromTypedDegree(rawDeg) {
    const h = ((rawDeg % 360) + 360) % 360;
    const step = Math.round(h / 2) % 180;
    return DEGREE_TABLE[step].corner;
  }

  function groupSignsByCorner(signs) {
    const groups = {};
    for (const s of signs) {
      const compass = compassFromSignLocation(s.sign_location) || 'other';
      if (!groups[compass]) groups[compass] = [];
      groups[compass].push(s);
    }
    return groups;
  }

  function nearestCorner(lat, lon, corners) {
    let best = null;
    let bestD = Infinity;
    for (const c of corners) {
      const d = (c.latitude - lat) ** 2 + (c.longitude - lon) ** 2;
      if (d < bestD) {
        bestD = d;
        best = c;
      }
    }
    return best;
  }

  function makeButton() {
    const btn = document.createElement('button');
    btn.id = BTN_ID;
    btn.textContent = '📷 Capture Sign';
    btn.addEventListener('click', startCapture);
    document.body.appendChild(btn);
  }

  function showHint(text, ms) {
    const hint = document.createElement('div');
    hint.id = 'ssc-hint';
    hint.textContent = text;
    document.body.appendChild(hint);
    if (ms) setTimeout(() => hint.remove(), ms);
    return hint;
  }

  function startCapture() {
    const btn = document.getElementById(BTN_ID);
    btn.disabled = true;
    btn.textContent = 'Capturing...';

    chrome.runtime.sendMessage({ type: 'capture' }, (resp) => {
      btn.disabled = false;
      btn.textContent = '📷 Capture Sign';
      if (!resp || !resp.ok) {
        alert('Capture failed: ' + (resp && resp.error));
        return;
      }
      openOverlay(resp.dataUrl);
    });
  }

  function openOverlay(dataUrl) {
    const overlay = document.createElement('div');
    overlay.id = 'ssc-overlay';
    const canvas = document.createElement('canvas');
    overlay.appendChild(canvas);
    document.body.appendChild(overlay);

    const hint = showHint('Drag a box around the sign. Esc to cancel.');

    function onKey(e) {
      if (e.key === 'Escape') {
        overlay.remove();
        hint.remove();
        document.removeEventListener('keydown', onKey);
      }
    }
    document.addEventListener('keydown', onKey);

    const img = new Image();
    img.onload = () => {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);

      let start = null;
      let rect = null;

      function toCanvasCoords(evt) {
        const r = canvas.getBoundingClientRect();
        const scaleX = canvas.width / r.width;
        const scaleY = canvas.height / r.height;
        return {
          x: (evt.clientX - r.left) * scaleX,
          y: (evt.clientY - r.top) * scaleY,
        };
      }

      function redraw() {
        ctx.drawImage(img, 0, 0);
        if (rect) {
          ctx.strokeStyle = '#ff3b30';
          ctx.lineWidth = 3;
          ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
        }
      }

      canvas.addEventListener('mousedown', (e) => {
        start = toCanvasCoords(e);
        rect = { x: start.x, y: start.y, w: 0, h: 0 };
      });
      canvas.addEventListener('mousemove', (e) => {
        if (!start) return;
        const p = toCanvasCoords(e);
        rect = {
          x: Math.min(start.x, p.x),
          y: Math.min(start.y, p.y),
          w: Math.abs(p.x - start.x),
          h: Math.abs(p.y - start.y),
        };
        redraw();
      });
      window.addEventListener('mouseup', function onUp() {
        if (!start) return;
        start = null;
        if (rect && rect.w > 8 && rect.h > 8) {
          hint.remove();
          document.removeEventListener('keydown', onKey);
          ctx.drawImage(img, 0, 0); // erase the red selection stroke before cropping
          finishSelection(canvas, rect, overlay);
        }
      });
    };
    img.src = dataUrl;
  }

  async function finishSelection(canvas, rect, overlay) {
    const cropCanvas = document.createElement('canvas');
    cropCanvas.width = rect.w;
    cropCanvas.height = rect.h;
    cropCanvas
      .getContext('2d')
      .drawImage(canvas, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h);
    const croppedDataUrl = cropCanvas.toDataURL('image/jpeg', 0.92);

    const loc = parseLocationFromUrl();
    const data = await loadSignsData();
    const match = loc && data ? nearestCorner(loc.lat, loc.lon, data.corners) : null;

    overlay.remove();
    showMetadataPanel(croppedDataUrl, loc, match);
  }

  function showMetadataPanel(croppedDataUrl, loc, match) {
    const panel = document.createElement('div');
    panel.id = 'ssc-panel';
    panel.style.top = '80px';
    panel.style.right = '24px';

    const preview = document.createElement('img');
    preview.src = croppedDataUrl;
    preview.style.width = '100%';
    preview.style.borderRadius = '4px';
    panel.appendChild(preview);

    const cornerGroups = match ? groupSignsByCorner(match.signs) : {};
    const cornerKeys = Object.keys(cornerGroups);
    const guess = loc ? compassGuessFromHeading(loc.heading) : null;
    const hasGuess = guess && cornerGroups[guess];

    const cornerButtons = cornerKeys
      .map((key) => {
        const label = COMPASS_LABELS[key] || key;
        const count = cornerGroups[key].length;
        const isGuess = key === guess;
        return `<button type="button" class="ssc-corner-btn${isGuess ? ' ssc-selected' : ''}" data-key="${key}">
          ${label}${count > 1 ? ` (${count} signs)` : ''}${isGuess ? ' (likely)' : ''}
        </button>`;
      })
      .join('');

    const onStreetName = cleanStreetName(match ? match.on_street : '');
    const fromStreetName = cleanStreetName(match ? match.from_street : '');

    panel.insertAdjacentHTML(
      'beforeend',
      `
      <h3>Confirm sign details</h3>
      <label>On street</label>
      <input id="ssc-on-street" value="${onStreetName}">
      <label>From street</label>
      <input id="ssc-from-street" value="${fromStreetName}">
      <label>Which street name is printed on this sign? <span class="ssc-required">*</span></label>
      <div id="ssc-street-name-buttons" class="ssc-btn-group">
        ${onStreetName ? `<button type="button" data-val="${onStreetName}">${onStreetName}</button>` : ''}
        ${fromStreetName ? `<button type="button" data-val="${fromStreetName}">${fromStreetName}</button>` : ''}
        <button type="button" data-val="not sure">Not sure</button>
      </div>
      <input type="text" id="ssc-street-name-custom" placeholder="Or type the street name printed on the sign...">
      <label>Which corner is this sign on? <span class="ssc-required">*</span></label>
      <div id="ssc-corner-buttons" class="ssc-btn-group">
        ${cornerButtons}
        <button type="button" class="ssc-corner-btn${hasGuess ? '' : ' ssc-selected'}" data-key="none">Not sure</button>
      </div>
      <input type="text" id="ssc-corner-custom" placeholder="Or type the corner directly (e.g. NE)...">
      <div class="ssc-degree-override">
        <label>None of those right? Type the heading you're facing (0-359°):</label>
        <input type="number" id="ssc-corner-degree" min="0" max="359" placeholder="e.g. 137">
        <div id="ssc-corner-degree-result"></div>
      </div>
      <label>Intersection type <span class="ssc-required">*</span></label>
      <div id="ssc-intersection-buttons" class="ssc-btn-group">
        <button type="button" data-val="4-leg">4-Leg</button>
        <button type="button" data-val="t-intersection">T-intersection</button>
        <button type="button" data-val="dog-leg">Dog-leg</button>
        <button type="button" data-val="complicated">Complicated</button>
        <button type="button" data-val="not sure">Not sure</button>
      </div>
      <label>Damage category <span class="ssc-required">*</span></label>
      <div id="ssc-damage-buttons" class="ssc-btn-group">
        <button type="button" data-val="missing">Missing</button>
        <button type="button" data-val="bent">Bent</button>
        <button type="button" data-val="hanging">Hanging</button>
        <button type="button" data-val="faded">Faded</button>
        <button type="button" data-val="vandalized">Vandalized</button>
        <button type="button" data-val="wrong-direction">Wrong-dir</button>
        <button type="button" data-val="white-border">White border</button>
        <button type="button" data-val="all-caps">All-caps</button>
        <button type="button" data-val="no damage">No damage</button>
      </div>
      <label>Notes</label>
      <textarea id="ssc-notes" rows="2"></textarea>
      <div id="ssc-validation-error"></div>
      <div class="ssc-actions">
        <button class="ssc-cancel">Cancel</button>
        <button class="ssc-save">Save</button>
      </div>
    `
    );
    document.body.appendChild(panel);

    let selectedSignText = '';
    const streetNameButtons = panel.querySelectorAll('#ssc-street-name-buttons button');
    const streetNameCustomInput = panel.querySelector('#ssc-street-name-custom');
    streetNameButtons.forEach((b) => {
      b.addEventListener('click', () => {
        selectedSignText = b.dataset.val;
        streetNameButtons.forEach((other) => other.classList.remove('ssc-selected'));
        b.classList.add('ssc-selected');
        streetNameCustomInput.value = '';
      });
    });
    streetNameCustomInput.addEventListener('input', () => {
      const typed = streetNameCustomInput.value.trim();
      if (!typed) return;
      selectedSignText = typed;
      streetNameButtons.forEach((other) => other.classList.remove('ssc-selected'));
    });

    let selectedIntersectionType = '';
    const intersectionButtons = panel.querySelectorAll('#ssc-intersection-buttons button');
    intersectionButtons.forEach((b) => {
      b.addEventListener('click', () => {
        selectedIntersectionType = b.dataset.val;
        intersectionButtons.forEach((other) => other.classList.remove('ssc-selected'));
        b.classList.add('ssc-selected');
      });
    });

    let selectedDamage = '';
    const damageButtons = panel.querySelectorAll('#ssc-damage-buttons button');
    damageButtons.forEach((b) => {
      b.addEventListener('click', () => {
        selectedDamage = b.dataset.val;
        damageButtons.forEach((other) => other.classList.remove('ssc-selected'));
        b.classList.add('ssc-selected');
      });
    });

    let selectedCorner = hasGuess ? guess : 'none';
    const cornerButtonEls = panel.querySelectorAll('#ssc-corner-buttons button');
    const cornerCustomInput = panel.querySelector('#ssc-corner-custom');
    const degreeInput = panel.querySelector('#ssc-corner-degree');
    const degreeResult = panel.querySelector('#ssc-corner-degree-result');

    cornerButtonEls.forEach((b) => {
      b.addEventListener('click', () => {
        selectedCorner = b.dataset.key;
        cornerButtonEls.forEach((other) => other.classList.remove('ssc-selected'));
        b.classList.add('ssc-selected');
        cornerCustomInput.value = '';
        degreeInput.value = '';
        degreeResult.textContent = '';
      });
    });

    cornerCustomInput.addEventListener('input', () => {
      const typed = cornerCustomInput.value.trim().toUpperCase();
      if (!typed) return;
      selectedCorner = typed;
      cornerButtonEls.forEach((other) => other.classList.remove('ssc-selected'));
      const matchingBtn = Array.from(cornerButtonEls).find((b) => b.dataset.key === typed);
      if (matchingBtn) matchingBtn.classList.add('ssc-selected');
      degreeInput.value = '';
      degreeResult.textContent = '';
    });

    degreeInput.addEventListener('input', () => {
      const deg = parseFloat(degreeInput.value);
      if (Number.isNaN(deg) || deg < 0 || deg > 359) {
        degreeResult.textContent = '';
        return;
      }
      const corner = cornerFromTypedDegree(deg);
      selectedCorner = corner;
      cornerCustomInput.value = '';
      cornerButtonEls.forEach((other) => other.classList.remove('ssc-selected'));
      const matchingBtn = Array.from(cornerButtonEls).find((b) => b.dataset.key === corner);
      if (matchingBtn) matchingBtn.classList.add('ssc-selected');
      const count = cornerGroups[corner] ? cornerGroups[corner].length : 0;
      degreeResult.textContent = `-> ${COMPASS_LABELS[corner] || corner}${count ? ` (${count} signs)` : ' (no signs recorded there)'}`;
    });

    panel.querySelector('.ssc-cancel').addEventListener('click', () => {
      panel.remove();
    });

    panel.querySelector('.ssc-save').addEventListener('click', () => {
      const errorEl = panel.querySelector('#ssc-validation-error');
      const missing = [];
      if (!selectedSignText) missing.push({ label: 'street name', group: streetNameButtons });
      if (!selectedIntersectionType) missing.push({ label: 'intersection type', group: intersectionButtons });
      if (!selectedDamage) missing.push({ label: 'damage category', group: damageButtons });
      // corner always has a value (guess or "none"), included for completeness/consistency
      if (!selectedCorner) missing.push({ label: 'corner', group: cornerButtonEls });

      panel.querySelectorAll('.ssc-btn-group').forEach((g) => g.classList.remove('ssc-group-error'));
      if (missing.length) {
        missing.forEach((m) => m.group[0] && m.group[0].closest('.ssc-btn-group').classList.add('ssc-group-error'));
        errorEl.textContent = `Missing: ${missing.map((m) => m.label).join(', ')}.`;
        errorEl.style.display = 'block';
        return;
      }
      errorEl.style.display = 'none';

      const pickedSigns = selectedCorner !== 'none' ? cornerGroups[selectedCorner] || [] : [];

      const onStreet = panel.querySelector('#ssc-on-street').value;
      const safeStreet = (onStreet || 'unknown').replace(/[^a-z0-9]+/gi, '_');
      const filename = `${Date.now()}_${safeStreet}.jpg`;

      const record = {
        filename,
        timestamp: new Date().toISOString(),
        latitude: loc ? loc.lat : null,
        longitude: loc ? loc.lon : null,
        heading: loc ? loc.heading : null,
        on_street: onStreet,
        from_street: panel.querySelector('#ssc-from-street').value,
        sign_text: selectedSignText,
        intersection_type: selectedIntersectionType,
        corner_id: match ? match.corner_id : '',
        corner_side: selectedCorner !== 'none' ? selectedCorner : '',
        order_numbers: pickedSigns.map((s) => s.order_number).join(';'),
        sign_codes: pickedSigns.map((s) => s.sign_code).join(';'),
        supports: pickedSigns.map((s) => s.support).join(';'),
        damage_category: selectedDamage,
        notes: panel.querySelector('#ssc-notes').value,
      };

      chrome.runtime.sendMessage(
        { type: 'save', imageDataUrl: croppedDataUrl, filename, record },
        (resp) => {
          panel.remove();
          if (resp && resp.ok) {
            showHint('Saved ✓', 1500);
          } else {
            alert('Save failed');
          }
        }
      );
    });
  }

  makeButton();
  makeCompassHud();
})();
