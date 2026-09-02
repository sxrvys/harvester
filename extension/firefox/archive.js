"use strict";

const fields = Object.fromEntries(["indexed", "waiting", "complete", "deferred", "retired"].map((id) => [id, document.querySelector(`#${id}`)]));
const archiveList = document.querySelector("#archive-list");
const archiveForm = document.querySelector("#archive-form");
const archiveUrl = document.querySelector("#archive-url");
const archiveName = document.querySelector("#archive-name");
const archiveFormStatus = document.querySelector("#archive-form-status");
const workspace = document.querySelector("#archive-workspace");
const selectedName = document.querySelector("#selected-name");
const selectedUrl = document.querySelector("#selected-url");
const lastScan = document.querySelector("#last-scan");
const status = document.querySelector("#status");
const scan = document.querySelector("#scan");
const batch = document.querySelector("#batch");
const failureLog = document.querySelector("#failure-log");
const count = document.querySelector("#count");
const minDelay = document.querySelector("#min-delay");
const maxDelay = document.querySelector("#max-delay");
const recentBatch = document.querySelector("#recent-batch");
let archives = [];
let selectedArchiveId = null;
let loadedBatchPath = null;
let editingArchiveId = null;

function native(command, payload = {}) {
  return browser.runtime.sendNativeMessage("com.harvester.native", {
    version: 1, command, request_id: crypto.randomUUID(), payload
  });
}

function selectedArchive() {
  return archives.find((archive) => archive.id === selectedArchiveId) || null;
}

async function loadArchives(preferredId = selectedArchiveId) {
  const response = await browser.runtime.sendMessage({command: "list_archives"});
  archives = response && response.ok && response.result && response.result.archives || [];
  if (!archives.some((archive) => archive.id === preferredId)) preferredId = archives[0] && archives[0].id;
  selectedArchiveId = preferredId || null;
  renderArchiveList();
  renderSelectedArchive();
  if (selectedArchiveId) await refresh();
}

function renderArchiveList() {
  archiveList.textContent = "";
  if (!archives.length) {
    archiveList.append(Object.assign(document.createElement("p"), {className: "muted", textContent: "No archives added yet."}));
    return;
  }
  for (const archive of archives) {
    const button = Object.assign(document.createElement("button"), {type: "button", className: "archive-choice"});
    button.setAttribute("aria-current", archive.id === selectedArchiveId ? "true" : "false");
    const label = document.createElement("span");
    label.textContent = `${archive.id === selectedArchiveId ? "✓  " : ""}${archive.name}`;
    const detail = document.createElement("span");
    detail.className = "muted";
    detail.textContent = archive.source_url || "Add Instagram URL";
    button.append(label, detail);
    button.addEventListener("click", async () => {
      selectedArchiveId = archive.id;
      loadedBatchPath = null;
      renderArchiveList();
      renderSelectedArchive();
      await refresh();
    });
    archiveList.append(button);
  }
}

function renderSelectedArchive() {
  const archive = selectedArchive();
  workspace.hidden = !archive;
  if (!archive) return;
  selectedName.textContent = archive.name;
  selectedUrl.textContent = archive.source_url || "Add the Instagram Saved-page URL to scan this existing archive again.";
  scan.disabled = !archive.source_url;
  document.querySelector("#open-instagram").disabled = !archive.source_url;
}

function showArchiveForm(archive = null) {
  editingArchiveId = archive && archive.id || null;
  archiveUrl.value = archive && archive.source_url || "";
  archiveName.value = archive && archive.name || "";
  archiveForm.querySelector("button[type=submit]").textContent = archive ? "Save archive" : "Add archive";
  archiveFormStatus.textContent = "";
  archiveForm.hidden = false;
  archiveUrl.focus();
}

async function loadRecentBatch() {
  if (!selectedArchiveId) return;
  const response = await native("get_latest_batch_review", {archive_id: selectedArchiveId});
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
    if (item.thumbnail) { preview.src = item.thumbnail; preview.alt = ""; } else preview.className = "thumbnail-placeholder";
    const detail = document.createElement("div");
    const heading = Object.assign(document.createElement("h3"), {textContent: item.title || item.bundle || "Instagram post"});
    const outcome = document.createElement("p");
    outcome.textContent = item.lifecycle_status === "retired-deleted" ? "Moved to Trash" : item.batch_status === "complete" ? "Downloaded" : "Skipped";
    detail.append(heading, outcome);
    if (item.duration_seconds !== null) detail.append(Object.assign(document.createElement("p"), {className: "muted", textContent: `${Math.round(item.duration_seconds)} seconds`}));
    const actions = Object.assign(document.createElement("div"), {className: "batch-actions"});
    const reveal = Object.assign(document.createElement("button"), {type: "button", textContent: "Reveal in Finder", disabled: !item.archive_present});
    const rename = Object.assign(document.createElement("button"), {type: "button", textContent: "Rename", disabled: !item.archive_present});
    const remove = Object.assign(document.createElement("button"), {type: "button", textContent: "Move to Trash", disabled: !item.archive_present, className: "danger"});
    reveal.addEventListener("click", async () => {
      const result = await native("reveal_archival_item", {archive_id: selectedArchiveId, source_id: item.source_id});
      status.textContent = result && result.ok ? "Archived item revealed" : "Archived item unavailable";
    });
    rename.addEventListener("click", async () => {
      const requested = prompt("Choose a short title. The archival-order number stays unchanged.", heading.textContent);
      if (requested === null) return;
      const result = await native("rename_archival_item", {archive_id: selectedArchiveId, source_id: item.source_id, title: requested});
      status.textContent = result && result.ok ? "Archived item renamed" : result && result.error && result.error.message || "Archived item was not renamed";
      await loadRecentBatch();
    });
    remove.addEventListener("click", async () => {
      if (!confirm(`Move “${heading.textContent}” to Trash and retire it from this archive?`)) return;
      const result = await native("delete_archival_item", {archive_id: selectedArchiveId, source_id: item.source_id});
      status.textContent = result && result.ok ? "Archived item moved to Trash" : result && result.error && result.error.message || "Archived item was not deleted";
      await refresh();
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
    lastScan.textContent = `Last scan: ${new Date(result.last_scan_at).toLocaleString()}${Number.isInteger(detail.new_count) ? ` — ${detail.new_count} newly indexed` : ""}`;
  } else lastScan.textContent = "This archive has not been scanned yet.";
  return result.latest_batch || null;
}

function batchMessage(result) {
  if (!result || !Number.isInteger(result.complete) || !Number.isInteger(result.failed)) return null;
  return `Archival batch complete — ${result.complete} ${result.complete === 1 ? "post" : "posts"} downloaded, ${result.failed} ${result.failed === 1 ? "post" : "posts"} skipped`;
}

async function refresh() {
  if (!selectedArchiveId) return;
  try {
    const [response, operation] = await Promise.all([
      browser.runtime.sendMessage({command: "get_archival_status", archive_id: selectedArchiveId}),
      browser.runtime.sendMessage({command: "get_archival_operation"})
    ]);
    const progress = response && response.ok ? renderStatus(response.result) : null;
    if (progress && progress.batch_path !== loadedBatchPath && progress.running === 0 && progress.pending === 0) {
      loadedBatchPath = progress.batch_path;
      void loadRecentBatch();
    }
    status.textContent = operation.state === "running" && progress
      ? `${operation.message}${progress.count ? ` ${progress.complete + progress.failed}/${progress.count} finished.` : ""}`
      : batchMessage(operation.result) || operation.message;
    const running = operation.state === "running";
    scan.disabled = running || !selectedArchive().source_url;
    batch.disabled = running || !(response && response.ok && response.result.available);
  } catch (error) {
    status.textContent = "Local companion unavailable";
    scan.disabled = true;
    batch.disabled = true;
  }
}

document.querySelector("#add-archive").addEventListener("click", () => showArchiveForm());
document.querySelector("#cancel-archive").addEventListener("click", () => { archiveForm.hidden = true; });
document.querySelector("#use-current-page").addEventListener("click", async () => {
  const tabs = await browser.tabs.query({currentWindow: true});
  const tab = tabs.find((candidate) => candidate.url && candidate.url.includes("instagram.com") && candidate.url.includes("/saved"));
  if (!tab) {
    archiveFormStatus.textContent = "Open an Instagram Saved page in this window first.";
    return;
  }
  archiveUrl.value = tab.url;
});
archiveForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await browser.runtime.sendMessage({command: "save_archive_source", archive_id: editingArchiveId, name: archiveName.value, source_url: archiveUrl.value});
  if (!response || !response.ok) {
    archiveFormStatus.textContent = response && response.error && response.error.message || "Archive was not saved";
    return;
  }
  archiveForm.hidden = true;
  await loadArchives(response.result.id);
});
document.querySelector("#open-instagram").addEventListener("click", () => {
  const archive = selectedArchive();
  if (archive && archive.source_url) browser.tabs.create({url: archive.source_url});
});
document.querySelector("#edit-archive").addEventListener("click", () => {
  const archive = selectedArchive();
  if (archive) showArchiveForm(archive);
});
document.querySelector("#rename-archive").addEventListener("click", async () => {
  const archive = selectedArchive();
  const name = archive && prompt("Rename this archive", archive.name);
  if (!name) return;
  const response = await browser.runtime.sendMessage({command: "rename_archive_source", archive_id: archive.id, name});
  if (response && response.ok) await loadArchives(archive.id);
});
document.querySelector("#remove-archive").addEventListener("click", async () => {
  const archive = selectedArchive();
  if (!archive || !confirm(`Remove “${archive.name}” from Harvester? Its queue and scan history will be removed. Harvested files will stay on your Mac.`)) return;
  const response = await browser.runtime.sendMessage({command: "remove_archive_source", archive_id: archive.id});
  if (response && response.ok) await loadArchives(null);
});
selectedUrl.addEventListener("click", () => { const archive = selectedArchive(); if (archive && !archive.source_url) showArchiveForm(archive); });
scan.addEventListener("click", async () => {
  const response = await browser.runtime.sendMessage({command: "start_saved_scan", archive_id: selectedArchiveId});
  status.textContent = response && response.accepted ? "Opening and scanning the configured Instagram archive…" : "Another operation is running";
});
batch.addEventListener("click", async () => {
  const values = [count.valueAsNumber, minDelay.valueAsNumber, maxDelay.valueAsNumber];
  if (!Number.isInteger(values[0]) || values[0] < 1 || values[0] > 25 || values[1] < 10 || values[2] < values[1] || values[2] > 300) {
    status.textContent = "Use a batch size from 1–25 and delays satisfying 10 ≤ minimum ≤ maximum ≤ 300";
    return;
  }
  const response = await browser.runtime.sendMessage({command: "start_archival_batch", archive_id: selectedArchiveId, count: values[0], min_delay: values[1], max_delay: values[2]});
  status.textContent = response && response.accepted ? "Harvesting oldest saved batch… Keep Firefox open." : "Another operation is running";
});
failureLog.addEventListener("click", async () => {
  const response = await native("open_failure_log", {archive_id: selectedArchiveId});
  status.textContent = response && response.ok ? "Failure log opened" : response && response.error && response.error.message || "Failure log unavailable";
});

setInterval(() => { if (selectedArchiveId) refresh(); }, 1000);
loadArchives().catch(() => { archiveList.textContent = "Local companion unavailable"; });
