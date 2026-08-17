/**
 * Manifest queue + progress persistence. Replaces the extension's
 * chrome.storage.local (background.js) with plain localStorage -- same
 * "accumulate locally, export CSV when ready" shape, just no Chrome APIs.
 */
(function () {
  const INDEX_KEY_PREFIX = "ssc_annotate_index:";
  const RECORDS_KEY = "ssc_annotate_records";

  let jobs = [];
  // Reading progress (which image you're on) is per-dataset, so switching
  // the dropdown to a different pulled collection doesn't jump you to
  // whatever index another collection was left on. Defaults to the
  // pre-dropdown single-dataset key so existing progress isn't lost.
  let indexKey = INDEX_KEY_PREFIX + "default";

  // isDefaultDataset: true only for the original/root collection (the one
  // that existed before the dataset dropdown did) -- see the migration
  // comment below. Callers pass this explicitly rather than load()
  // guessing from manifestUrl, since queue.js otherwise has no notion of
  // which dataset is "the" default one.
  async function load(manifestUrl, isDefaultDataset = false) {
    // no-store: fetch_manifest.json changes as more panoramas get fetched
    // during a work session, and the plain http.server this tool is served
    // from sends no cache-control headers, so a default fetch() can (and
    // did, in practice) serve a stale copy even right after a hard reload.
    const resp = await fetch(manifestUrl, { cache: "no-store" });
    if (!resp.ok) throw new Error(`Failed to load ${manifestUrl}: ${resp.status}`);
    const manifest = await resp.json();
    indexKey = INDEX_KEY_PREFIX + manifestUrl;
    // One-time migration: before the dropdown existed, progress lived under
    // the flat "ssc_annotate_index" key with no per-dataset scoping, always
    // meaning a position in what's now the default/root dataset. Only ever
    // migrate it into THAT dataset's key -- migrating it into whichever
    // dataset happens to load first with no key yet (e.g. because it was
    // the last-selected one) would apply an unrelated collection's old
    // position to a dataset it was never a position in.
    if (isDefaultDataset) {
      const legacyIndex = localStorage.getItem("ssc_annotate_index");
      if (legacyIndex !== null && localStorage.getItem(indexKey) === null) {
        localStorage.setItem(indexKey, legacyIndex);
      }
    }
    // Only images with a real file on disk have anything to annotate --
    // "ok" (fetched this run) and "skipped" (fetch_cyclomedia_panoramas.py's
    // status for "the file already existed, so we didn't re-fetch it") both
    // mean that. Rejecting "skipped" was a real bug: main() rewrites the
    // whole manifest from THIS run's results every time, so re-running the
    // fetch step against an already-fully-fetched dataset flips every job's
    // status from "ok" to "skipped" even though nothing about the actual
    // files changed -- and this filter used to treat that as "nothing to
    // annotate," even with hundreds of good images sitting right there.
    // Only "failed" (no recording found / API error -- no file exists) is
    // correctly excluded.
    jobs = (manifest.jobs || []).filter((j) => j.status === "ok" || j.status === "skipped");
    return jobs;
  }

  function total() {
    return jobs.length;
  }

  function getIndex() {
    const raw = localStorage.getItem(indexKey);
    const i = raw ? parseInt(raw, 10) : 0;
    return Math.min(Math.max(i, 0), Math.max(jobs.length - 1, 0));
  }

  function setIndex(i) {
    const clamped = Math.min(Math.max(i, 0), Math.max(jobs.length - 1, 0));
    localStorage.setItem(indexKey, String(clamped));
    return clamped;
  }

  function current() {
    return jobs[getIndex()] || null;
  }

  function next() {
    return setIndex(getIndex() + 1);
  }

  function prev() {
    return setIndex(getIndex() - 1);
  }

  function getRecords() {
    const raw = localStorage.getItem(RECORDS_KEY);
    return raw ? JSON.parse(raw) : [];
  }

  function addRecords(newRecords) {
    const all = getRecords().concat(newRecords);
    localStorage.setItem(RECORDS_KEY, JSON.stringify(all));
    return all;
  }

  function isAnnotated(sourceImage) {
    return getRecords().some((r) => r.source_image === sourceImage);
  }

  window.Queue = { load, total, getIndex, setIndex, current, next, prev, getRecords, addRecords, isAnnotated };
})();
