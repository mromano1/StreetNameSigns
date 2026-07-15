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
