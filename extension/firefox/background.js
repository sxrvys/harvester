"use strict";

const NATIVE_APPLICATION = "com.harvester.native";
let harvestState = {state: "idle", message: "Local companion ready"};
const stateReady = browser.storage.local.get("harvestState").then((stored) => {
  if (stored.harvestState && typeof stored.harvestState === "object") {
    harvestState = stored.harvestState;
  }
});

function setHarvestState(value) {
  harvestState = value;
  return browser.storage.local.set({harvestState: value});
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

browser.runtime.onMessage.addListener(async (message) => {
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
  if (message.command === "open_output_folder") {
    return sendNative("open_output_folder", {});
  }
  return undefined;
});
