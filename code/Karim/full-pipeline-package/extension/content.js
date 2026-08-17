(function () {
  const BTN_ID = 'ssc-launch-btn';
  // A previous injection's elements (from an SPA route change, OR -- the
  // real culprit confirmed live 2026-07-21 -- an extension reload that
  // silently left an old script instance's DOM behind) are removed rather
  // than treated as "already set up, nothing to do." That old guard was
  // bailing out on sight of a leftover button, which meant a reloaded
  // extension could keep running genuinely stale code indefinitely -- this
  // makes each injection self-healing instead of trusting whatever's already
  // there. Any dangling setInterval from that old instance keeps ticking
  // harmlessly against elements that no longer exist once removed here.
  ['ssc-launch-btn', 'ssc-compass', 'ssc-oob-warning', 'ssc-streetsmart-hint', 'ssc-overlay', 'ssc-panel', 'ssc-hint'].forEach((id) => {
    document.getElementById(id)?.remove();
  });

  let signsData = null;

  // On Street Smart, clicking Capture Sign itself closes the info panel
  // (confirmed live 2026-07-20), so by the time finishSelection() runs, a
  // fresh getCurrentLocation() finds nothing to read. The compass HUD's
  // 400ms poll (see makeCompassHud) keeps this updated whenever a location
  // IS available, so the capture flow can fall back to "whatever we last
  // saw" instead of "nothing, because the panel just closed."
  //
  // lastKnownLocationAt (bug found 2026-08-04) bounds how long that fallback
  // stays trustworthy: without it, navigating to a new position without
  // reopening the info panel there left this pointing at the *previous*
  // position indefinitely, silently matching the wrong corner at capture
  // time (right intersection, wrong street number) until the panel was
  // reopened. See location-freshness.js -- the fallback is only used within
  // MAX_FALLBACK_LOCATION_AGE_MS of being recorded.
  let lastKnownLocation = null;
  let lastKnownLocationAt = null;

  // Reloading the extension in chrome://extensions kills the connection for
  // any tab that already had this content script injected -- chrome.runtime
  // calls from that orphaned instance either throw synchronously or never
  // call back, which is exactly what left the Capture button stuck on
  // "Capturing...". Checking chrome.runtime.id (it goes undefined once the
  // context is invalidated) lets every call site fail fast with a clear
  // message instead of hanging.
  function isExtensionContextValid() {
    return !!(chrome.runtime && chrome.runtime.id);
  }

  function loadSignsData() {
    if (signsData) return Promise.resolve(signsData);
    if (!isExtensionContextValid()) return Promise.resolve(null);
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: 'get_signs_data' }, (resp) => {
          if (resp && resp.ok) {
            signsData = resp.data;
            resolve(signsData);
          } else {
            resolve(null);
          }
        });
      } catch (e) {
        resolve(null);
      }
    });
  }

  function getDamagePrediction(croppedDataUrl) {
    if (!isExtensionContextValid()) return Promise.resolve(null);
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: 'predict_damage', imageDataUrl: croppedDataUrl }, (resp) => {
          if (resp && resp.ok) {
            resolve(resp.classes);
          } else {
            resolve(null);
          }
        });
      } catch (e) {
        resolve(null);
      }
    });
  }

  function parseLocationFromUrl() {
    // Matches .../@40.7509,-73.9807,3a,75y,120h,90t/...
    const m = window.location.href.match(/@(-?\d+\.\d+),(-?\d+\.\d+),.*?(\d+(?:\.\d+)?)h/);
    if (!m) return null;
    return { system: 'wgs84', lat: parseFloat(m[1]), lon: parseFloat(m[2]), heading: parseFloat(m[3]) };
  }

  function isStreetSmartSite() {
    return window.location.hostname.endsWith('cyclomedia.com');
  }

  // Street Smart's panorama info panel (the "i" button dropdown) renders rows
  // like "X (US ft)  1005439.29 (± 0.02)". Confirmed live 2026-07-20: it IS a
  // <table>, but label and value don't reliably show up as two clean sibling
  // <td> cells (a flex-laid-out cell combining both is more likely, per the
  // "StripedTableCell { display:flex }" CSS seen earlier) -- a per-cell
  // lookup silently found nothing. Matching against the page's flattened text
  // sidesteps needing to know the exact cell structure.
  //
  // Also confirmed live: the number isn't always immediately adjacent to its
  // label -- "Y (US ft)"/"Yaw (deg)" had their value right after, but "X (US
  // ft)" didn't (something else -- a copy-icon button, maybe -- likely sits
  // between them on that row only). So instead of requiring the number right
  // after the label, this finds the label then takes the first number-looking
  // token within a short window after it.
  //
  // ASSUMPTION NOT YET VERIFIED: that "Yaw (deg)" uses the same 0=North/
  // clockwise convention as Google's heading. If the compass HUD points the
  // wrong way on Street Smart, check this first.
  function findLabeledNumber(text, labelPattern) {
    const m = labelPattern.exec(text);
    if (!m) return null;
    const windowText = text.slice(m.index + m[0].length, m.index + m[0].length + 60);
    const numMatch = windowText.match(/-?\d+(?:\.\d+)?/);
    return numMatch ? parseFloat(numMatch[0]) : null;
  }

  function parseStreetSmartInfoPanel() {
    const text = document.body.textContent || '';
    // No leading \b: confirmed live 2026-07-21 that the preceding row's value
    // often sits with zero whitespace against the next label in flattened
    // textContent (e.g. "...3:09 PMX (US ft)1005439.29..." -- "PM" glued
    // directly to "X"), which fails a word-boundary check since both sides
    // are word characters. The "(us ft)"/"(deg)" suffix requirement already
    // provides enough specificity without needing a boundary before the letter.
    const xVal = findLabeledNumber(text, /x\s*\(us\s*ft\)/i);
    const yVal = findLabeledNumber(text, /y\s*\(us\s*ft\)/i);
    const yawVal = findLabeledNumber(text, /yaw\s*\(deg\)/i);
    if (!Number.isFinite(xVal) || !Number.isFinite(yVal) || !Number.isFinite(yawVal)) return null;
    return { system: 'spcs2263', x: xVal, y: yVal, heading: yawVal };
  }

  function getCurrentLocation() {
    return isStreetSmartSite() ? parseStreetSmartInfoPanel() : parseLocationFromUrl();
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
      <div id="ssc-newest-order-date"></div>
    `;
    document.body.appendChild(hud);

    const oobWarning = document.createElement('div');
    oobWarning.id = 'ssc-oob-warning';
    document.body.appendChild(oobWarning);

    // On Street Smart, position can ONLY be read from the "i" info panel's
    // rendered text (there's no URL fallback like Google Maps has) -- see
    // parseStreetSmartInfoPanel(). Without this hint, a user who never
    // discovers that panel gets total silence (no compass, no OOB warning,
    // nothing) and every capture fails to match, with no clue why. Found
    // 2026-08-05: a stakeholder tester hit exactly this -- SIMS matching
    // "just didn't work" on Street Smart while Google Maps was fine, purely
    // because the info panel was never opened.
    const streetSmartHint = document.createElement('div');
    streetSmartHint.id = 'ssc-streetsmart-hint';
    streetSmartHint.textContent =
      'Click the ⓘ info icon in Street Smart to enable sign matching (this tool reads your position from it).';
    document.body.appendChild(streetSmartHint);

    const needle = hud.querySelector('.ssc-compass-needle');
    const label = hud.querySelector('.ssc-compass-label');
    const newestOrderEl = hud.querySelector('#ssc-newest-order-date');

    function refreshOobWarning(loc) {
      if (!signsData || !signsData.corners) {
        oobWarning.style.display = 'none';
        return;
      }
      const match = findMatch(loc, signsData.corners);
      const outOfBounds = !match || match._outOfBounds;
      if (!outOfBounds) {
        oobWarning.style.display = 'none';
        return;
      }
      const dist = formatNearestCornerDistance(match, loc);
      oobWarning.textContent = dist
        ? `Outside your loaded SIMS data area (nearest known corner is ${dist} away), this corner won't have a sign match`
        : "Outside your loaded SIMS data area, this corner won't have a sign match";
      oobWarning.style.display = 'block';
    }

    // Live "which year should I check" hint, so finding a sign's
    // pre-replacement (likely damaged) state doesn't require manually
    // flipping through every year of Cyclomedia imagery. Uses the same
    // distance-based corner match as the OOB warning, just reads the dates
    // instead. signs missing order_completed_on_date (pre-backfill data,
    // see StreetNameSigns/code/Karim/scripts/03_add_order_dates.py) are
    // silently skipped by newestOrderDate(), not treated as an error.
    function refreshNewestOrderDate(loc) {
      if (!signsData || !signsData.corners) {
        newestOrderEl.style.display = 'none';
        return;
      }
      const match = findMatch(loc, signsData.corners);
      const date = match ? newestOrderDate(match.signs) : null;
      if (!date) {
        newestOrderEl.style.display = 'none';
        return;
      }
      newestOrderEl.textContent = `Newest order: ${date} — try imagery before this for damage`;
      newestOrderEl.style.display = 'block';
    }

    function update() {
      const loc = getCurrentLocation();
      if (!loc) {
        hud.style.display = 'none';
        oobWarning.style.display = 'none';
        streetSmartHint.style.display = isStreetSmartSite() ? 'block' : 'none';
        return;
      }
      streetSmartHint.style.display = 'none';
      lastKnownLocation = loc;
      lastKnownLocationAt = Date.now();
      hud.style.display = 'flex';
      const gridHeading = toGridHeading(loc.heading);
      needle.style.transform = `rotate(${gridHeading}deg)`;
      label.textContent = `grid ${gridCompassLabel(gridHeading)}`;

      if (signsData) {
        refreshOobWarning(loc);
        refreshNewestOrderDate(loc);
      } else {
        loadSignsData().then(() => {
          refreshOobWarning(loc);
          refreshNewestOrderDate(loc);
        });
      }
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

  // Rough threshold for "you've wandered outside the loaded SIMS data area."
  // ~0.0011 degrees is about 120m -- comfortably bigger than corner-to-corner
  // spacing along a worked avenue (median ~74m, max ~165m in zip 10001) but
  // tight enough to flag a wrong nearest-corner guess 2-4 blocks away instead
  // of silently prefilling it. (Was 0.004/~400m, which was too loose to catch
  // that case -- see the E 10th/11th St data-coverage gap.)
  const MAX_MATCH_DISTANCE_DEG = 0.0011;

  // Same threshold as MAX_MATCH_DISTANCE_DEG, expressed in feet (State Plane,
  // EPSG:2263) for the Street Smart matching path: 120m =~ 394ft, rounded.
  const MAX_MATCH_DISTANCE_FT = 400;

  function nearestCorner(lat, lon, corners) {
    let best = null;
    let bestD = Infinity;
    for (const c of corners) {
      if (c.latitude == null || c.longitude == null) continue;
      const d = (c.latitude - lat) ** 2 + (c.longitude - lon) ** 2;
      if (d < bestD) {
        bestD = d;
        best = c;
      }
    }
    if (!best) return null;
    best._distanceDeg = Math.sqrt(bestD);
    best._outOfBounds = best._distanceDeg > MAX_MATCH_DISTANCE_DEG;
    return best;
  }

  // Same idea as nearestCorner, but in State Plane feet (x_2263/y_2263) for
  // locations read from Cyclomedia Street Smart, which reports position in
  // that CRS rather than lat/lon -- see getCurrentLocation().
  function nearestCornerLocal(x, y, corners) {
    let best = null;
    let bestD = Infinity;
    for (const c of corners) {
      if (c.x_2263 == null || c.y_2263 == null) continue;
      const d = (c.x_2263 - x) ** 2 + (c.y_2263 - y) ** 2;
      if (d < bestD) {
        bestD = d;
        best = c;
      }
    }
    if (!best) return null;
    best._distanceFt = Math.sqrt(bestD);
    best._outOfBounds = best._distanceFt > MAX_MATCH_DISTANCE_FT;
    return best;
  }

  function findMatch(loc, corners) {
    if (!loc || !corners) return null;
    return loc.system === 'spcs2263'
      ? nearestCornerLocal(loc.x, loc.y, corners)
      : nearestCorner(loc.lat, loc.lon, corners);
  }

  function isOutOfBounds(loc, corners) {
    if (!corners || !corners.length) return true;
    const match = findMatch(loc, corners);
    return !match || match._outOfBounds;
  }

  // Diagnostic-only: renders the distance to the nearest loaded SIMS corner,
  // so an "outside data area" report comes with a real number instead of a
  // bare yes/no (added 2026-07-27 after a false-positive report during a
  // Cyclomedia demo that couldn't be reproduced from the report alone).
  function formatNearestCornerDistance(match, loc) {
    if (!match) return null;
    if (loc.system === 'spcs2263' && match._distanceFt != null) {
      return `${Math.round(match._distanceFt)} ft`;
    }
    if (match._distanceDeg != null) {
      // Rough deg->meters conversion for display only; matching itself
      // already treats degrees as roughly equivalent, see MAX_MATCH_DISTANCE_DEG.
      return `~${Math.round(match._distanceDeg * 111320)} m`;
    }
    return null;
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

  // Resolves the location to use for a capture. Must be called at click
  // time (see startCapture), not later at finishSelection time -- the
  // screenshot itself is already frozen by chrome.tabs.captureVisibleTab at
  // click time, but the user's subsequent box-drag before mouseup is
  // human-paced and can run well past any short "just clicked" freshness
  // window. Re-deriving this at finishSelection time (bug found 2026-08-04:
  // "outside your loaded SIMS data area" even right after opening the info
  // panel) checks freshness against the wrong reference point -- the info
  // panel closing is tied to the click, not to whenever the user finishes
  // dragging the box.
  function resolveCaptureLocation() {
    return (
      getCurrentLocation() ||
      (isLocationFresh(lastKnownLocationAt, Date.now(), MAX_FALLBACK_LOCATION_AGE_MS) ? lastKnownLocation : null)
    );
  }

  function startCapture() {
    const btn = document.getElementById(BTN_ID);

    if (!isExtensionContextValid()) {
      alert('The extension was reloaded since this page loaded, so it can no longer talk to it. Refresh the page to keep capturing.');
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Capturing...';

    function resetButton() {
      btn.disabled = false;
      btn.textContent = '📷 Capture Sign';
    }

    // Resolved now, before the async capture round-trip and the box-drag
    // that follows it -- see resolveCaptureLocation's comment.
    const capturedLoc = resolveCaptureLocation();

    try {
      chrome.runtime.sendMessage({ type: 'capture' }, (resp) => {
        resetButton();
        if (chrome.runtime.lastError) {
          alert('Capture failed: ' + chrome.runtime.lastError.message + ' -- try refreshing the page.');
          return;
        }
        if (!resp || !resp.ok) {
          alert('Capture failed: ' + (resp && resp.error));
          return;
        }
        openOverlay(resp.dataUrl, capturedLoc);
      });
    } catch (e) {
      resetButton();
      alert('Extension connection lost (probably reloaded). Refresh the page to keep capturing.');
    }
  }

  function openOverlay(dataUrl, capturedLoc) {
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
          finishSelection(canvas, rect, overlay, capturedLoc);
        }
      });
    };
    img.src = dataUrl;
  }

  async function finishSelection(canvas, rect, overlay, loc) {
    const cropCanvas = document.createElement('canvas');
    cropCanvas.width = rect.w;
    cropCanvas.height = rect.h;
    cropCanvas
      .getContext('2d')
      .drawImage(canvas, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h);
    const croppedDataUrl = cropCanvas.toDataURL('image/jpeg', 0.92);

    // loc was resolved by resolveCaptureLocation() back at startCapture()
    // click time, not re-derived here -- see that function's comment for
    // why re-deriving it after the user's (human-paced) box drag was wrong.
    const data = await loadSignsData();
    const match = loc && data ? findMatch(loc, data.corners) : null;
    const damagePrediction = await getDamagePrediction(croppedDataUrl);

    overlay.remove();
    showMetadataPanel(croppedDataUrl, loc, match, damagePrediction);
  }

  const DAMAGE_BUTTONS = [
    { val: 'missing', label: 'Missing' },
    { val: 'bent', label: 'Bent' },
    { val: 'hanging', label: 'Hanging' },
    { val: 'faded', label: 'Faded' },
    { val: 'vandalized', label: 'Vandalized' },
    { val: 'wrong-direction', label: 'Wrong-dir' },
    { val: 'white-border', label: 'White border' },
    { val: 'all-caps', label: 'All-caps' },
  ];

  // "missing"/"wrong-direction" are intersection-rule tags, never guessed by
  // the physical-condition model -- damageGuessPlan has no entry for them,
  // so they always fall through to the plain/default button rendering.
  function damageButtonsHtml(damageGuessPlan) {
    const buttons = DAMAGE_BUTTONS.map(({ val, label }) => {
      const guess = damageGuessPlan[val];
      const isHint = !!(guess && guess.hint);
      const pct = guess && guess.confidence != null ? Math.round(guess.confidence * 100) : null;
      const suffix = isHint && pct != null ? ` (likely, ${pct}%)` : '';
      const cls = isHint ? ' class="ssc-guess-hint"' : '';
      return `<button type="button" data-val="${val}"${cls}>${label}${suffix}</button>`;
    });
    buttons.push('<button type="button" data-val="no damage">No damage</button>');
    // Capture artifact (glitched/wobbly panorama stitching, etc.), not real
    // sign damage -- never guessed by the model, always plain/default.
    buttons.push('<button type="button" data-val="artifact">Artifact</button>');
    return buttons.join('');
  }

  function showMetadataPanel(croppedDataUrl, loc, match, damagePrediction) {
    const panel = document.createElement('div');
    panel.id = 'ssc-panel';
    panel.style.top = '80px';
    panel.style.right = '24px';

    const preview = document.createElement('img');
    preview.src = croppedDataUrl;
    preview.style.width = '100%';
    preview.style.borderRadius = '4px';
    panel.appendChild(preview);

    const outOfBounds = !match || match._outOfBounds;
    if (outOfBounds) {
      const dist = loc ? formatNearestCornerDistance(match, loc) : null;
      const warn = document.createElement('div');
      warn.id = 'ssc-panel-oob-warning';
      warn.textContent = dist
        ? `This location is outside your loaded SIMS data area (nearest known corner is ${dist} away), there's no reliable sign match. Saving will still work, but without a real SIMS order number.`
        : "This location is outside your loaded SIMS data area, there's no reliable sign match. Saving will still work, but without a real SIMS order number.";
      panel.appendChild(warn);
    }

    const cornerGroups = match ? groupSignsByCorner(match.signs) : {};
    const cornerKeys = Object.keys(cornerGroups);
    const guess = loc ? compassGuessFromHeading(loc.heading) : null;
    const hasGuess = guess && cornerGroups[guess];
    const damageGuessPlan =
      typeof buildDamageGuessPlan === 'function' ? buildDamageGuessPlan(damagePrediction) : {};

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
    const newestDate = match ? newestOrderDate(match.signs) : null;

    panel.insertAdjacentHTML(
      'beforeend',
      `
      <h3>Confirm sign details</h3>
      ${newestDate ? `<div id="ssc-newest-order-note">Newest order at this corner: ${newestDate} — check imagery from just before this for a damaged example.</div>` : ''}
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
        ${damageButtonsHtml(damageGuessPlan)}
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

    // Multi-select: a sign can have more than one issue (faded AND vandalized,
    // for example), so damage buttons toggle independently, except "no damage"
    // and "artifact," which are each mutually exclusive with every real
    // damage category (and with each other) -- "no damage" says nothing's
    // wrong with the sign, "artifact" says the image itself can't be trusted
    // to judge that, so neither makes sense combined with a real damage tag.
    const EXCLUSIVE_DAMAGE_VALUES = ['no damage', 'artifact'];
    let selectedDamages = DAMAGE_BUTTONS.filter(({ val }) => damageGuessPlan[val] && damageGuessPlan[val].preselect).map(({ val }) => val);
    const damageButtons = panel.querySelectorAll('#ssc-damage-buttons button');
    damageButtons.forEach((b) => {
      b.addEventListener('click', () => {
        const val = b.dataset.val;
        if (EXCLUSIVE_DAMAGE_VALUES.includes(val)) {
          selectedDamages = [val];
          damageButtons.forEach((other) => other.classList.remove('ssc-selected'));
          b.classList.add('ssc-selected');
          return;
        }
        // picking a real damage category cancels "no damage"/"artifact" if either was active
        const activeExclusive = selectedDamages.find((d) => EXCLUSIVE_DAMAGE_VALUES.includes(d));
        if (activeExclusive) {
          selectedDamages = [];
          const exclusiveBtn = Array.from(damageButtons).find((btn) => btn.dataset.val === activeExclusive);
          if (exclusiveBtn) exclusiveBtn.classList.remove('ssc-selected');
        }
        if (selectedDamages.includes(val)) {
          selectedDamages = selectedDamages.filter((d) => d !== val);
          b.classList.remove('ssc-selected');
        } else {
          selectedDamages.push(val);
          b.classList.add('ssc-selected');
        }
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
      if (!selectedDamages.length) missing.push({ label: 'damage category', group: damageButtons });
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

      // loc.lat/lon only exist for the wgs84 (Google Maps) path -- Street
      // Smart locations are spcs2263 (x/y in State Plane feet, see
      // getCurrentLocation()). Recording coord_system alongside means a
      // reader can tell which pair of fields is populated for a given row,
      // instead of silently getting nulls/undefined for Cyclomedia captures.
      const isLocalCoords = loc && loc.system === 'spcs2263';
      const record = {
        filename,
        timestamp: new Date().toISOString(),
        coord_system: loc ? loc.system : null,
        latitude: loc && !isLocalCoords ? loc.lat : null,
        longitude: loc && !isLocalCoords ? loc.lon : null,
        x_2263: isLocalCoords ? loc.x : null,
        y_2263: isLocalCoords ? loc.y : null,
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
        damage_category: selectedDamages.join(';'),
        notes: panel.querySelector('#ssc-notes').value,
      };

      if (!isExtensionContextValid()) {
        alert('Extension connection lost (probably reloaded) -- this capture was NOT saved. Refresh the page and redo it.');
        return;
      }

      try {
        chrome.runtime.sendMessage(
          { type: 'save', imageDataUrl: croppedDataUrl, filename, record },
          (resp) => {
            if (chrome.runtime.lastError) {
              alert('Save failed: ' + chrome.runtime.lastError.message + ' -- this capture was NOT saved. Refresh the page and redo it.');
              return;
            }
            panel.remove();
            if (resp && resp.ok) {
              showHint('Saved ✓', 1500);
            } else {
              alert('Save failed');
            }
          }
        );
      } catch (e) {
        alert('Extension connection lost (probably reloaded) -- this capture was NOT saved. Refresh the page and redo it.');
      }
    });
  }

  // Temporary debug hook (2026-07-21) -- exposes the actual functions this
  // script uses so they can be called directly from the console instead of
  // reimplementing them there, which has been silently testing a different
  // code path than the real one. Safe to remove once Street Smart matching
  // is confirmed working live.
  window.__sscDebug = {
    getCurrentLocation,
    parseStreetSmartInfoPanel,
    isStreetSmartSite,
    findMatch,
    getLastKnownLocation: () => lastKnownLocation,
    getLastKnownLocationAt: () => lastKnownLocationAt,
    getSignsData: () => signsData,
  };

  makeButton();
  makeCompassHud();
})();
