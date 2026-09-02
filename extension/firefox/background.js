"use strict";

const NATIVE_APPLICATION = "com.harvester.native";
let harvestState = {state: "idle", message: "Local companion ready"};
let archivalState = {state: "idle", message: "Archival Harvest ready"};
let pickerTimeout = null;
let pickerTabId = null;
let lastFailureTabId = null;
const MAX_FIREFOX_DIAGNOSTICS = 100;
const stateReady = browser.storage.local.get("harvestState").then((stored) => {
  if (stored.harvestState && typeof stored.harvestState === "object") {
    if (stored.harvestState.state === "selecting") {
      harvestState = {state: "idle", message: "Local companion ready"};
      return browser.storage.local.set({harvestState});
    }
    if (stored.harvestState.state === "running") {
      harvestState = {state: "failed", message: "Previous harvest was interrupted by extension reload"};
      return browser.storage.local.set({harvestState});
    }
    harvestState = stored.harvestState;
  }
  return undefined;
});
const archivalStateReady = browser.storage.local.get("archivalState").then((stored) => {
  if (stored.archivalState && typeof stored.archivalState === "object") {
    archivalState = stored.archivalState.state === "running"
      ? {state: "failed", message: "Previous archival operation was interrupted by extension reload"}
      : stored.archivalState;
    return browser.storage.local.set({archivalState});
  }
  return undefined;
});

function setHarvestState(value) {
  harvestState = value;
  return browser.storage.local.set({harvestState: value});
}

function setArchivalState(value) {
  archivalState = value;
  return browser.storage.local.set({archivalState: value});
}

function anyOperationRunning() {
  return ["running", "selecting"].includes(harvestState.state) || archivalState.state === "running";
}

function stopPickerTimeout() {
  if (pickerTimeout !== null) clearTimeout(pickerTimeout);
  pickerTimeout = null;
}

async function cancelPickerForTab(tabId, message) {
  if (pickerTabId !== tabId || harvestState.state !== "selecting") return;
  stopPickerTimeout();
  pickerTabId = null;
  await setHarvestState({state: "idle", message});
}

function requestId() {
  return crypto.randomUUID();
}

function sendNative(command, payload) {
  return browser.runtime.sendNativeMessage(NATIVE_APPLICATION, {
    version: 1,
    command,
    request_id: requestId(),
    payload
  });
}

async function recordFirefoxFailure(operation, code, message, tabId = null) {
  try {
    const stored = await browser.storage.local.get("firefoxDiagnostics");
    const events = Array.isArray(stored.firefoxDiagnostics) ? stored.firefoxDiagnostics : [];
    events.push({
      recorded_at: new Date().toISOString(),
      operation: String(operation).slice(0, 80),
      code: String(code).slice(0, 80),
      message: String(message).replace(/[\r\n]+/g, " ").slice(0, 500),
      application_version: browser.runtime.getManifest().version
    });
    lastFailureTabId = Number.isInteger(tabId) ? tabId : lastFailureTabId;
    await browser.storage.local.set({firefoxDiagnostics: events.slice(-MAX_FIREFOX_DIAGNOSTICS)});
  } catch (error) {
    // Diagnostics are best-effort and must never interfere with the requested operation.
  }
}

function sanitizedPageUrl(raw) {
  try {
    const value = new URL(raw);
    if (!["http:", "https:"].includes(value.protocol)) return null;
    value.username = "";
    value.password = "";
    value.search = "";
    value.hash = "";
    return value.toString();
  } catch (error) {
    return null;
  }
}

async function runHarvest(url) {
  await setHarvestState({state: "running", message: "Harvesting… Keep Firefox open."});
  try {
    const response = await sendNative("harvest_url", {url});
    if (response && response.ok) {
      await setHarvestState({
        state: "complete",
        message: "Harvest complete",
        output_path: response.result && response.result.output_path
      });
    } else {
      const failure = response && response.error || {};
      await recordFirefoxFailure("harvest_url", failure.code || "harvest_failed", failure.message || "Harvest failed safely");
      await setHarvestState({
        state: "failed",
        message: response && response.error && response.error.message || "Harvest failed safely"
      });
    }
  } catch (error) {
    await recordFirefoxFailure("harvest_url", "companion_unavailable", "Local companion became unavailable");
    await setHarvestState({state: "failed", message: "Local companion became unavailable"});
  }
}

async function runMediaHarvest(mediaUrl, pageUrl) {
  await setHarvestState({state: "running", message: "Harvesting selected media… Keep Firefox open."});
  try {
    const response = await sendNative("harvest_media_url", {
      media_url: mediaUrl,
      page_url: pageUrl
    });
    if (response && response.ok) {
      await setHarvestState({
        state: "complete",
        message: "Selected media harvest complete",
        output_path: response.result && response.result.output_path
      });
    } else {
      const failure = response && response.error || {};
      await recordFirefoxFailure("harvest_media_url", failure.code || "selected_media_failed", failure.message || "Selected media failed safely", lastFailureTabId);
      await setHarvestState({
        state: "failed",
        message: response && response.error && response.error.message || "Selected media failed safely"
      });
    }
  } catch (error) {
    await recordFirefoxFailure("harvest_media_url", "companion_unavailable", "Local companion became unavailable", lastFailureTabId);
    await setHarvestState({state: "failed", message: "Local companion became unavailable"});
  }
}

async function runArchivalOperation(command, payload, runningMessage, completeMessage) {
  await setArchivalState({state: "running", message: runningMessage});
  try {
    const response = await sendNative(command, payload);
    if (response && response.ok) {
      const result = response.result || {};
      const message = command === "harvest_archival_batch"
        ? archivalBatchCompleteMessage(result)
        : completeMessage;
      await setArchivalState({
        state: "complete", message, result
      });
    } else {
      await setArchivalState({
        state: "failed",
        message: response && response.error && response.error.message || "Archival operation failed safely"
      });
    }
  } catch (error) {
    await setArchivalState({state: "failed", message: "Local companion became unavailable"});
  }
}

function waitForTabComplete(tabId) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      browser.tabs.onUpdated.removeListener(updated);
      reject(new Error("Instagram page took too long to load"));
    }, 30000);
    function updated(updatedId, changeInfo) {
      if (updatedId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timeout);
      browser.tabs.onUpdated.removeListener(updated);
      resolve();
    }
    browser.tabs.onUpdated.addListener(updated);
    browser.tabs.get(tabId).then((tab) => {
      if (tab.status === "complete") {
        clearTimeout(timeout);
        browser.tabs.onUpdated.removeListener(updated);
        resolve();
      }
    }).catch(reject);
  });
}

async function runConfiguredArchiveScan(archiveId) {
  await setArchivalState({state: "running", message: "Opening the configured Instagram archive…"});
  let scanTabId = null;
  try {
    const contextResponse = await sendNative("get_archive_scan_context", {archive_id: archiveId});
    if (!contextResponse || !contextResponse.ok) throw new Error(contextResponse && contextResponse.error && contextResponse.error.message || "Archive unavailable");
    const context = contextResponse.result;
    const tab = await browser.tabs.create({url: context.archive.source_url, active: true});
    scanTabId = tab.id;
    await waitForTabComplete(tab.id);
    await browser.tabs.executeScript(tab.id, {file: "archive-scanner.js", allFrames: false});
    const scanResult = await browser.tabs.sendMessage(tab.id, {
      command: "scan_instagram_archive_page",
      known_source_ids: context.known_source_ids
    });
    if (!scanResult || !Array.isArray(scanResult.items)) throw new Error("Instagram archive could not be read");
    if (!scanResult.items.length) {
      throw new Error(`No post links found after examining ${scanResult.examined_links || 0} page links and ${scanResult.examined_tiles || 0} visible tiles`);
    }
    const response = await sendNative("sync_archive_items", {archive_id: archiveId, items: scanResult.items});
    if (!response || !response.ok) throw new Error(response && response.error && response.error.message || "Saved-page scan failed safely");
    await setArchivalState({state: "complete", message: "Saved-post scan complete", result: response.result});
    await browser.tabs.remove(scanTabId).catch(() => undefined);
  } catch (error) {
    await recordFirefoxFailure("scan_saved_posts", "scan_failed", error && error.message || "Saved-page scan failed safely");
    await setArchivalState({state: "failed", message: error && error.message || "Saved-page scan failed safely"});
  }
}

function archivalBatchCompleteMessage(result) {
  const downloaded = Number.isInteger(result.complete) ? result.complete : 0;
  const skipped = Number.isInteger(result.failed) ? result.failed : 0;
  const downloadLabel = downloaded === 1 ? "post" : "posts";
  const skipLabel = skipped === 1 ? "post" : "posts";
  return `Archival batch complete — ${downloaded} ${downloadLabel} downloaded, ${skipped} ${skipLabel} skipped`;
}

async function runLocalFileHarvest() {
  await setHarvestState({state: "running", message: "Waiting for local file selection…"});
  try {
    const response = await sendNative("harvest_local_file", {});
    if (response && response.ok && response.result && response.result.state === "cancelled") {
      await setHarvestState({state: "idle", message: "Local file selection cancelled"});
    } else if (response && response.ok) {
      await setHarvestState({
        state: "complete", message: "Local file harvest complete",
        output_path: response.result && response.result.output_path
      });
    } else {
      await setHarvestState({
        state: "failed", message: response && response.error && response.error.message || "Local file failed safely"
      });
    }
  } catch (error) {
    await setHarvestState({state: "failed", message: "Local companion became unavailable"});
  }
}

browser.runtime.onMessage.addListener(async (message, sender) => {
  await stateReady;
  await archivalStateReady;
  if (!message || typeof message !== "object") return undefined;
  if (message.command === "get_companion_status") {
    return sendNative("get_status", {});
  }
  if (message.command === "get_harvest_state") {
    return harvestState;
  }
  if (message.command === "get_archival_operation") return archivalState;
  if (message.command === "get_bug_report_context") {
    const stored = await browser.storage.local.get("firefoxDiagnostics");
    let pageUrl = null;
    if (Number.isInteger(lastFailureTabId)) {
      try {
        pageUrl = sanitizedPageUrl((await browser.tabs.get(lastFailureTabId)).url);
      } catch (error) {
        pageUrl = null;
      }
    }
    let nativeEvents = [];
    try {
      const response = await sendNative("get_diagnostics", {});
      if (response && response.ok && Array.isArray(response.result.events)) nativeEvents = response.result.events;
    } catch (error) {
      // A Firefox-side companion failure is already useful without native events.
    }
    return {
      firefox: Array.isArray(stored.firefoxDiagnostics) ? stored.firefoxDiagnostics : [],
      native: nativeEvents,
      sanitized_page_url: pageUrl
    };
  }
  if (message.command === "list_archives") return sendNative("list_archives", {});
  if (message.command === "save_archive_source") return sendNative("save_archive_source", {
    ...(message.archive_id ? {archive_id: message.archive_id} : {}),
    name: message.name || "", source_url: message.source_url
  });
  if (message.command === "rename_archive_source") return sendNative("rename_archive_source", {
    archive_id: message.archive_id, name: message.name
  });
  if (message.command === "remove_archive_source") return sendNative("remove_archive_source", {archive_id: message.archive_id});
  if (message.command === "get_archival_status") return sendNative("get_archival_status", {archive_id: message.archive_id});
  if (message.command === "start_saved_scan") {
    if (anyOperationRunning()) return {accepted: false, state: archivalState};
    void runConfiguredArchiveScan(message.archive_id);
    return {accepted: true};
  }
  if (message.command === "start_local_file_harvest") {
    if (anyOperationRunning()) return {accepted: false, state: harvestState};
    void runLocalFileHarvest();
    return {accepted: true};
  }
  if (message.command === "start_archival_batch") {
    if (anyOperationRunning()) return {accepted: false, state: archivalState};
    void runArchivalOperation(
      "harvest_archival_batch",
      {archive_id: message.archive_id, count: message.count, min_delay: message.min_delay, max_delay: message.max_delay},
      "Harvesting oldest saved batch… Keep Firefox open.",
      "Archival batch complete"
    );
    return {accepted: true};
  }
  if (message.command === "archive_scan_progress") {
    if (archivalState.state === "running" && Number.isInteger(message.count)) {
      await setArchivalState({
        state: "running",
        message: "Scanning archive… Keep Firefox open."
      });
    }
    return {accepted: true};
  }
  if (message.command === "archive_tile_progress") {
    if (archivalState.state === "running") {
      await setArchivalState({
        state: "running",
        message: `Resolving visible collection tiles… ${Number.isInteger(message.found) ? message.found : 0} of ${Number.isInteger(message.candidates) ? message.candidates : 0} identified.`
      });
    }
    return {accepted: true};
  }
  if (message.command === "start_harvest") {
    if (anyOperationRunning()) {
      return {accepted: false, state: harvestState};
    }
    if (typeof message.url !== "string") {
      return {accepted: false, state: {state: "failed", message: "Invalid URL"}};
    }
    void runHarvest(message.url);
    return {accepted: true};
  }
  if (message.command === "start_picker") {
    if (anyOperationRunning()) {
      return {accepted: false, state: harvestState};
    }
    if (!Number.isInteger(message.tab_id)) {
      await recordFirefoxFailure("media_picker", "invalid_tab", "Media picker unavailable");
      return {accepted: false, state: {state: "failed", message: "Media picker unavailable"}};
    }
    try {
      await browser.tabs.executeScript(message.tab_id, {
        file: "picker.js",
        allFrames: false
      });
      await setHarvestState({
        state: "selecting",
        message: "Media picker ready — click one visible video or audio element"
      });
      stopPickerTimeout();
      pickerTimeout = setTimeout(async () => {
        pickerTimeout = null;
        if (harvestState.state !== "selecting") return;
        pickerTabId = null;
        await browser.tabs.sendMessage(message.tab_id, {command: "stop_picker"}).catch(() => undefined);
        await setHarvestState({
          state: "failed",
          message: "No accessible media was selected"
        });
        await recordFirefoxFailure("media_picker", "selection_timeout", "No accessible media was selected", message.tab_id);
      }, 60000);
      return {accepted: true};
    } catch (error) {
      await recordFirefoxFailure("media_picker", "injection_blocked", "This page does not allow media selection", message.tab_id);
      await setHarvestState({state: "failed", message: "This page does not allow media selection"});
      return {accepted: false, state: harvestState};
    }
  }
  if (message.command === "picker_selection") {
    if (anyOperationRunning() && harvestState.state !== "selecting") return {accepted: false};
    stopPickerTimeout();
    pickerTabId = null;
    if (sender.tab && Number.isInteger(sender.tab.id)) {
      await browser.tabs.sendMessage(sender.tab.id, {command: "stop_picker"}).catch(() => undefined);
    }
    if (!message.media_url) {
      await recordFirefoxFailure("media_picker", "missing_media_url", "Selected media has no ordinary URL", sender.tab && sender.tab.id);
      await setHarvestState({state: "failed", message: "Selected media has no ordinary URL"});
      return {accepted: false};
    }
    const pageUrl = sender.tab && sender.tab.url;
    if (typeof pageUrl !== "string") {
      await recordFirefoxFailure("media_picker", "missing_page_url", "Selected page has no ordinary URL", sender.tab && sender.tab.id);
      return {accepted: false};
    }
    lastFailureTabId = sender.tab && sender.tab.id;
    void runMediaHarvest(message.media_url, pageUrl);
    return {accepted: true};
  }
  if (message.command === "picker_cancelled") {
    stopPickerTimeout();
    pickerTabId = null;
    if (sender.tab && Number.isInteger(sender.tab.id)) {
      await browser.tabs.sendMessage(sender.tab.id, {command: "stop_picker"}).catch(() => undefined);
    }
    await setHarvestState({state: "idle", message: "Media selection cancelled"});
    return {accepted: true};
  }
  if (message.command === "open_output_folder") {
    return sendNative("open_output_folder", {});
  }
  return undefined;
});

browser.tabs.onRemoved.addListener((tabId) => {
  void cancelPickerForTab(tabId, "Media selection cancelled because the page was closed");
});

browser.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    void cancelPickerForTab(tabId, "Media selection cancelled because the page changed");
  }
});
