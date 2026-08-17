function csvEscape(val) {
  const s = String(val == null ? '' : val);
  if (/[",\n]/.test(s)) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function toCsv(records) {
  if (records.length === 0) return '';
  const cols = Object.keys(records[0]);
  const lines = [cols.join(',')];
  for (const r of records) {
    lines.push(cols.map((c) => csvEscape(r[c])).join(','));
  }
  return lines.join('\n');
}

function refreshCount() {
  chrome.storage.local.get({ captures: [] }, ({ captures }) => {
    document.getElementById('count').textContent = captures.length;
  });
}

document.getElementById('export').addEventListener('click', () => {
  chrome.storage.local.get({ captures: [] }, ({ captures }) => {
    if (captures.length === 0) {
      alert('No captures yet.');
      return;
    }
    const csv = toCsv(captures);
    const dataUrl = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    chrome.downloads.download({
      url: dataUrl,
      filename: `manual_capture/manifest_${Date.now()}.csv`,
      saveAs: false,
    });
  });
});

document.getElementById('clear').addEventListener('click', () => {
  if (confirm('Clear all captured metadata from this session?')) {
    chrome.storage.local.set({ captures: [] }, refreshCount);
  }
});

refreshCount();

document.getElementById('best-practices').addEventListener('click', () => {
  chrome.tabs.create({ url: chrome.runtime.getURL('best-practices.html') });
});

const RETRAIN_THRESHOLD = 10;
let currentRunName = null;

function renderAccuracyInfo(lastRun, previousRun) {
  const el = document.getElementById('accuracy-info');
  const viewReportBtn = document.getElementById('view-report');
  const comparison = formatAccuracyComparison(lastRun, previousRun);
  currentRunName = lastRun ? lastRun.run_name : null;
  viewReportBtn.disabled = !currentRunName;
  if (!comparison) {
    el.textContent = '';
    return;
  }
  el.innerHTML =
    `<strong>${comparison.runName}</strong><br>` +
    `precision: ${comparison.precisionText}<br>` +
    `recall: ${comparison.recallText}<br>` +
    `mAP50: ${comparison.map50Text}<br>` +
    `mAP50-95: ${comparison.map5095Text}`;
}

function maybeUpdateBadgeState(lastRun) {
  if (!lastRun) return;
  chrome.storage.local.get({ lastSeenRunName: null }, ({ lastSeenRunName }) => {
    if (shouldAnnounceNewRun(lastSeenRunName, lastRun)) {
      chrome.storage.local.set({ lastSeenRunName: lastRun.run_name });
    }
    // Opening the popup and seeing the current accuracy panel is what
    // dismisses the badge -- no separate "mark as read" action needed.
    chrome.action.setBadgeText({ text: '' });
  });
}

function refreshRetrainStatus(errorText) {
  chrome.runtime.sendMessage({ type: 'get_retrain_status' }, (resp) => {
    const mlBlock = document.getElementById('ml-block');
    const statusEl = document.getElementById('retrain-status');
    const retrainBtn = document.getElementById('retrain');
    if (!resp || !resp.ok) {
      // No local model server (the normal, permanent state for a
      // stakeholder package -- see the 2026-08-04 packaging plan). Hiding
      // the whole block instead of showing "Retrain status unavailable"
      // avoids presenting a non-technical user with a broken-looking
      // feature they were never meant to see.
      mlBlock.style.display = 'none';
      return;
    }
    mlBlock.style.display = '';
    if (resp.is_retraining) {
      // A genuinely still-running retrain takes precedence over a stale
      // errorText (e.g. a 409 from a click that raced a running retrain --
      // "already in progress" is less accurate than this).
      statusEl.textContent = 'Training in progress... this can take a while. Safe to close this popup -- training keeps running on the server.';
      retrainBtn.disabled = true;
    } else if (errorText) {
      statusEl.textContent = errorText;
      retrainBtn.disabled = resp.new_since_last_retrain < RETRAIN_THRESHOLD;
    } else {
      statusEl.textContent = `${resp.new_since_last_retrain} new labeled captures since last retrain`;
      retrainBtn.disabled = resp.new_since_last_retrain < RETRAIN_THRESHOLD;
    }
    renderAccuracyInfo(resp.last_run, resp.previous_run);
    maybeUpdateBadgeState(resp.last_run);
  });
}

document.getElementById('retrain').addEventListener('click', () => {
  const retrainBtn = document.getElementById('retrain');
  const statusEl = document.getElementById('retrain-status');
  retrainBtn.disabled = true;
  statusEl.textContent = 'Training... this can take a while. Safe to close this popup -- training keeps running on the server.';
  chrome.runtime.sendMessage({ type: 'trigger_retrain' }, (resp) => {
    if (!resp || !resp.ok) {
      refreshRetrainStatus('Retrain failed: ' + ((resp && resp.error) || 'no response from server'));
      return;
    }
    statusEl.textContent = 'Retrain complete.';
    refreshRetrainStatus();
  });
});

document.getElementById('view-report').addEventListener('click', () => {
  if (!currentRunName) return;
  chrome.runtime.sendMessage({ type: 'open_report', runName: currentRunName });
});

refreshRetrainStatus();

document.getElementById('version').textContent = `v${chrome.runtime.getManifest().version}`;
