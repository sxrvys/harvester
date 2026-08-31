"use strict";

const NATIVE_APPLICATION = "com.harvester.native";
const form = document.querySelector("#settings-form");
const archiveRoot = document.querySelector("#archive-root");
const firefoxProfile = document.querySelector("#firefox-profile");
const audioPreset = document.querySelector("#audio-preset");
const chooseOutput = document.querySelector("#choose-output");
const save = document.querySelector("#save");
const status = document.querySelector("#status");

function requestId() {
  return crypto.randomUUID();
}

async function send(command, payload) {
  return browser.runtime.sendNativeMessage(NATIVE_APPLICATION, {
    version: 1,
    command,
    request_id: requestId(),
    payload
  });
}

async function initialize() {
  try {
    const response = await send("get_settings", {});
    if (!response || !response.ok) throw new Error("Local companion returned an error");
    archiveRoot.value = response.result.archive_root || "";
    firefoxProfile.value = response.result.firefox_profile || "";
    audioPreset.value = response.result.audio_preset || "wav_48k_24";
    status.textContent = response.result.configured ? "Settings are valid" : "Choose an output folder";
  } catch (error) {
    status.textContent = "Local companion unavailable";
    save.disabled = true;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  save.disabled = true;
  status.textContent = "Saving…";
  try {
    const response = await send("update_settings", {
      archive_root: archiveRoot.value.trim(),
      firefox_profile: firefoxProfile.value.trim(),
      audio_preset: audioPreset.value
    });
    if (response && response.ok) {
      status.textContent = "Settings saved and verified";
    } else {
      status.textContent = response && response.error && response.error.message || "Settings were not saved";
    }
  } catch (error) {
    status.textContent = "Local companion unavailable";
  } finally {
    save.disabled = false;
  }
});

chooseOutput.addEventListener("click", async () => {
  chooseOutput.disabled = true;
  status.textContent = "Opening folder picker…";
  try {
    const response = await send("choose_output_folder", {});
    if (response && response.ok && response.result.selected) {
      archiveRoot.value = response.result.path;
      status.textContent = "Folder selected — save settings to apply";
    } else if (response && response.ok) {
      status.textContent = "Folder selection cancelled";
    } else {
      status.textContent = response && response.error && response.error.message || "Folder picker unavailable";
    }
  } catch (error) {
    status.textContent = "Local companion unavailable";
  } finally {
    chooseOutput.disabled = false;
  }
});

initialize();
