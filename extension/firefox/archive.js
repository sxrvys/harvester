"use strict";

const fields = {
  indexed: document.querySelector("#indexed"), waiting: document.querySelector("#waiting"),
  complete: document.querySelector("#complete"), deferred: document.querySelector("#deferred"),
  retired: document.querySelector("#retired")
};
const lastScan = document.querySelector("#last-scan");
const status = document.querySelector("#status");
const scan = document.querySelector("#scan");
const batch = document.querySelector("#batch");
const failureLog = document.querySelector("#failure-log");
const count = document.querySelector("#count");
const minDelay = document.querySelector("#min-delay");
const maxDelay = document.querySelector("#max-delay");
const recentBatch = document.querySelector("#recent-batch");
let loadedBatchPath = null;

function native(command, payload = {}) {
  return browser.runtime.sendNativeMessage("com.harvester.native", {
    version: 1, command, request_id: crypto.randomUUID(), payload
  });
}

async function loadRecentBatch() {
  const response = await native("get_latest_batch_review");
  if (!response || !response.ok) return;
  recentBatch.textContent = "";
  const items = response.result && response.result.items || [];
  if (!items.length) {
    recentBatch.append(Object.assign(document.createElement("p"), {textContent: "No archival batch has been recorded yet."}));
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "batch-item";
    const preview = item.thumbnail ? document.createElement("img") : document.createElement("div");
    if (item.thumbnail) {
      preview.src = item.thumbnail;
      preview.alt = "";
    } else {
      preview.className = "thumbnail-placeholder";
    }
    const detail = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = item.title || item.bundle || "Instagram post";
    const outcome = document.createElement("p");
    outcome.textContent = item.lifecycle_status === "retired-deleted" ? "Moved to Trash" :
      item.batch_status === "complete" ? "Downloaded" : "Skipped";
    detail.append(heading, outcome);
    if (item.duration_seconds !== null) {
      const duration = document.createElement("p");
      duration.className = "muted";
      duration.textContent = `${Math.round(item.duration_seconds)} seconds`;
      detail.append(duration);
    }
    const actions = document.createElement("div");
    actions.className = "batch-actions";
    const reveal = Object.assign(document.createElement("button"), {type: "button", textContent: "Reveal in Finder"});
    const rename = Object.assign(document.createElement("button"), {type: "button", textContent: "Rename"});
    const remove = Object.assign(document.createElement("button"), {type: "button", textContent: "Move to Trash"});
    remove.className = "danger";
    const present = Boolean(item.archive_present);
    reveal.disabled = !present;
    rename.disabled = !present;
    remove.disabled = !present;
    reveal.addEventListener("click", async () => {
      const result = await native("reveal_archival_item", {source_id: item.source_id});
      status.textContent = result && result.ok ? "Archived item revealed" : "Archived item unavailable";
    });
    rename.addEventListener("click", async () => {
      const requested = prompt("Choose a short title. The archival-order number stays unchanged.", heading.textContent);
      if (requested === null) return;
      rename.disabled = true;
      const result = await native("rename_archival_item", {source_id: item.source_id, title: requested});
      status.textContent = result && result.ok ? "Archived item renamed" :
        result && result.error && result.error.message || "Archived item was not renamed";
      await loadRecentBatch();
    });
    remove.addEventListener("click", async () => {
      if (!confirm(`Move “${heading.textContent}” to Trash and retire it from the archive queue?`)) return;
      remove.disabled = true;
      const result = await native("delete_archival_item", {source_id: item.source_id});
      status.textContent = result && result.ok ? "Archived item moved to Trash" :
        result && result.error && result.error.message || "Archived item was not deleted";
      await refresh();
      await loadRecentBatch();
    });
    actions.append(reveal, rename, remove);
    card.append(preview, detail, actions);
    recentBatch.append(card);
  });
}

function renderStatus(result) {
  const summary = result.summary || {};
  fields.indexed.textContent = result.indexed || summary.total || 0;
  fields.waiting.textContent = summary.discovered || 0;
  fields.complete.textContent = summary.complete || 0;
  fields.deferred.textContent = summary.deferred || 0;
  fields.retired.textContent = (summary["retired-used"] || 0) + (summary["retired-deleted"] || 0);
  if (result.last_scan_at) {
    const detail = result.last_scan || {};
    const added = Number.isInteger(detail.new_count) ? ` — ${detail.new_count} newly indexed` : "";
    lastScan.textContent = `Last scan: ${new Date(result.last_scan_at).toLocaleString()}${added}`;
  }
  return result.latest_batch || null;
}

function batchCompleteMessage(result) {
  if (result && Number.isInteger(result.complete) && Number.isInteger(result.failed)) {
    const downloadedLabel = result.complete === 1 ? "post" : "posts";
    const skippedLabel = result.failed === 1 ? "post" : "posts";
    return `Archival batch complete — ${result.complete} ${downloadedLabel} downloaded, ${result.failed} ${skippedLabel} skipped`;
  }
  return null;
}

function operationMessage(operation, latestBatch) {
  const storedResult = operation && operation.state === "complete"
    ? batchCompleteMessage(operation.result)
    : null;
  if (storedResult) return storedResult;
  const durableResult = latestBatch && latestBatch.running === 0 && latestBatch.pending === 0
    ? batchCompleteMessage(latestBatch)
    : null;
  return durableResult || operation.message;
}

async function refresh() {
  try {
    const [response, operation] = await Promise.all([
      browser.runtime.sendMessage({command: "get_archival_status"}),
      browser.runtime.sendMessage({command: "get_archival_operation"})
    ]);
    const progress = response && response.ok ? renderStatus(response.result) : null;
    if (progress && progress.batch_path !== loadedBatchPath && progress.running === 0 && progress.pending === 0) {
      loadedBatchPath = progress.batch_path;
      void loadRecentBatch();
    }
    status.textContent = operation.state === "running" && progress
      ? `${operation.message} ${progress.complete + progress.failed}/${progress.count} finished.`
      : operationMessage(operation, progress);
    const running = operation.state === "running";
    scan.disabled = running;
    batch.disabled = running;
    if (!running && operation.result) renderStatus({
      indexed: fields.indexed.textContent, summary: operation.result.summary || {}
    });
  } catch (error) {
    status.textContent = "Local companion unavailable";
    scan.disabled = true;
    batch.disabled = true;
  }
}

scan.addEventListener("click", async () => {
  const response = await browser.runtime.sendMessage({command: "start_saved_scan"});
  status.textContent = response && response.accepted ? "Scanning saved posts… Keep Firefox open." : "Another operation is running";
  await refresh();
});

batch.addEventListener("click", async () => {
  const values = [count.valueAsNumber, minDelay.valueAsNumber, maxDelay.valueAsNumber];
  if (!Number.isInteger(values[0]) || values[0] < 1 || values[0] > 25
      || values[1] < 10 || values[2] < values[1] || values[2] > 300) {
    status.textContent = "Use a batch size from 1–25 and delays satisfying 10 ≤ minimum ≤ maximum ≤ 300";
    return;
  }
  const response = await browser.runtime.sendMessage({
    command: "start_archival_batch", count: values[0], min_delay: values[1], max_delay: values[2]
  });
  status.textContent = response && response.accepted ? "Harvesting oldest saved batch… Keep Firefox open." : "Another operation is running";
  await refresh();
});

failureLog.addEventListener("click", async () => {
  failureLog.disabled = true;
  try {
    const response = await browser.runtime.sendNativeMessage("com.harvester.native", {
      version: 1, command: "open_failure_log", request_id: crypto.randomUUID(), payload: {}
    });
    status.textContent = response && response.ok
      ? "Failure log opened"
      : response && response.error && response.error.message || "Failure log unavailable";
  } catch (error) {
    status.textContent = "Local companion unavailable";
  } finally {
    failureLog.disabled = false;
  }
});

setInterval(refresh, 1000);
refresh();
loadRecentBatch().catch(() => { recentBatch.textContent = "Recent batch unavailable"; });
