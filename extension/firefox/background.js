"use strict";

const NATIVE_APPLICATION = "com.harvester.native";
let harvestState = {state: "idle", message: "Local companion ready"};
let pickerTimeout = null;
let pickerTabId = null;
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

function setHarvestState(value) {
  harvestState = value;
  return browser.storage.local.set({harvestState: value});
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
      await setHarvestState({
        state: "failed",
        message: response && response.error && response.error.message || "Harvest failed safely"
      });
    }
  } catch (error) {
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
      await setHarvestState({
        state: "failed",
        message: response && response.error && response.error.message || "Selected media failed safely"
      });
    }
  } catch (error) {
    await setHarvestState({state: "failed", message: "Local companion became unavailable"});
  }
}

browser.runtime.onMessage.addListener(async (message, sender) => {
  await stateReady;
  if (!message || typeof message !== "object") return undefined;
  if (message.command === "get_companion_status") {
    return sendNative("get_status", {});
  }
  if (message.command === "get_harvest_state") {
    return harvestState;
  }
  if (message.command === "start_harvest") {
    if (harvestState.state === "running") {
      return {accepted: false, state: harvestState};
    }
    if (typeof message.url !== "string") {
      return {accepted: false, state: {state: "failed", message: "Invalid URL"}};
    }
    void runHarvest(message.url);
    return {accepted: true};
  }
  if (message.command === "start_picker") {
    if (harvestState.state === "running") {
      return {accepted: false, state: harvestState};
    }
    if (!Number.isInteger(message.tab_id)) {
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
      }, 60000);
      return {accepted: true};
    } catch (error) {
      await setHarvestState({state: "failed", message: "This page does not allow media selection"});
      return {accepted: false, state: harvestState};
    }
  }
  if (message.command === "picker_selection") {
    if (harvestState.state === "running") return {accepted: false};
    stopPickerTimeout();
    pickerTabId = null;
    if (sender.tab && Number.isInteger(sender.tab.id)) {
      await browser.tabs.sendMessage(sender.tab.id, {command: "stop_picker"}).catch(() => undefined);
    }
    if (!message.media_url) {
      await setHarvestState({state: "failed", message: "Selected media has no ordinary URL"});
      return {accepted: false};
    }
    const pageUrl = sender.tab && sender.tab.url;
    if (typeof pageUrl !== "string") return {accepted: false};
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
