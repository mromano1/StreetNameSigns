let signsDataCache = null;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'get_signs_data') {
    if (signsDataCache) {
      sendResponse({ ok: true, data: signsDataCache });
      return true;
    }
    fetch(chrome.runtime.getURL('signs_data.json'))
      .then((r) => r.json())
      .then((data) => {
        signsDataCache = data;
        sendResponse({ ok: true, data });
      })
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === 'capture') {
    chrome.tabs.captureVisibleTab(sender.tab.windowId, { format: 'png' }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      sendResponse({ ok: true, dataUrl });
    });
    return true; // keep the message channel open for the async response
  }

  if (msg.type === 'save') {
    const { imageDataUrl, filename, record } = msg;

    chrome.downloads.download(
      {
        url: imageDataUrl,
        filename: `manual_capture/${filename}`,
        saveAs: false,
      },
      (downloadId) => {
        if (chrome.runtime.lastError) {
          console.error('download failed:', chrome.runtime.lastError.message);
        } else {
          console.log('download started, id=', downloadId);
        }
      }
    );

    chrome.storage.local.get({ captures: [] }, ({ captures }) => {
      captures.push(record);
      chrome.storage.local.set({ captures }, () => sendResponse({ ok: true }));
    });
    return true;
  }
});
