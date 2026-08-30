"use strict";

const page = document.querySelector("#page");
const status = document.querySelector("#status");
const harvest = document.querySelector("#harvest");
const settings = document.querySelector("#settings");
const openOutput = document.querySelector("#open-output");
const selectMedia = document.querySelector("#select-media");
let currentUrl = null;
let currentTabId = null;
let unsupportedPage = false;
let companionConfigured = false;

function isSupportedUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
    if ((parsed.hostname === "instagram.com" || parsed.hostname === "www.instagram.com")
        && /^\/(p|reel|reels)\/[A-Za-z0-9_-]+\/?$/.test(parsed.pathname)) return true;
    return (parsed.hostname === "youtube.com" || parsed.hostname === "www.youtube.com")
      && parsed.pathname === "/watch"
      && /^[A-Za-z0-9_-]{11}$/.test(parsed.searchParams.get("v") || "");
  } catch (error) {
    return false;
  }
}

function displayUrl(parsed) {
  if ((parsed.hostname === "youtube.com" || parsed.hostname === "www.youtube.com")
      && parsed.pathname === "/watch") {
    const videoId = parsed.searchParams.get("v");
    if (/^[A-Za-z0-9_-]{11}$/.test(videoId || "")) {
      return `${parsed.host}/watch?v=${videoId}`;
    }
  }
  return `${parsed.host}${parsed.pathname}`;
}

async function initialize() {
  try {
    const tabs = await browser.tabs.query({active: true, currentWindow: true});
    const url = tabs[0] && tabs[0].url;
    currentTabId = tabs[0] && tabs[0].id;
    if (url) {
      const parsed = new URL(url);
      page.textContent = displayUrl(parsed);
      page.title = url;
      if (isSupportedUrl(url)) {
        currentUrl = url;
      } else if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        unsupportedPage = true;
        selectMedia.hidden = false;
      }
    }

    const response = await browser.runtime.sendMessage({command: "get_companion_status"});
    if (response && response.ok) {
      const configured = Boolean(response.result && response.result.configured);
      companionConfigured = configured;
      const operation = await browser.runtime.sendMessage({command: "get_harvest_state"});
      harvest.disabled = !configured || !currentUrl || ["running", "selecting"].includes(operation.state);
      selectMedia.disabled = !configured || !unsupportedPage || ["running", "selecting"].includes(operation.state);
      status.textContent = configured
        ? operation.message
        : "Configure output and Firefox profile in local settings";
    } else {
      status.textContent = "Local companion returned an error";
    }
  } catch (error) {
    const detail = String(error && error.message || "").toLowerCase();
    if (detail.includes("no such native application")) {
      status.textContent = "Local companion not registered";
    } else if (detail.includes("exited") || detail.includes("failed to start")) {
      status.textContent = "Local companion could not start";
    } else {
      const safeDetail = String(error && error.message || "unknown error")
        .replace(/[\r\n]+/g, " ")
        .slice(0, 160);
      status.textContent = `Local companion unavailable: ${safeDetail}`;
    }
  }
}

harvest.addEventListener("click", async () => {
  if (!currentUrl || harvest.disabled) return;
  harvest.disabled = true;
  status.textContent = "Harvesting… Keep Firefox open.";
  try {
    const response = await browser.runtime.sendMessage({
      command: "start_harvest",
      url: currentUrl
    });
    if (response && response.accepted) {
      status.textContent = "Harvesting… Keep Firefox open.";
    } else {
      status.textContent = response && response.state && response.state.message || "Harvest already running";
      harvest.disabled = false;
    }
  } catch (error) {
    status.textContent = "Local companion became unavailable";
    harvest.disabled = false;
  }
});

settings.addEventListener("click", () => browser.runtime.openOptionsPage());
selectMedia.addEventListener("click", async () => {
  if (!currentTabId || selectMedia.disabled) return;
  const response = await browser.runtime.sendMessage({command: "start_picker", tab_id: currentTabId});
  if (response && response.accepted) {
    status.textContent = "Click one visible video or audio element; press Escape to cancel";
    window.close();
  } else {
    status.textContent = response && response.state && response.state.message || "Media picker unavailable";
  }
});
openOutput.addEventListener("click", async () => {
  const response = await browser.runtime.sendMessage({command: "open_output_folder"});
  if (!response || !response.ok) {
    status.textContent = response && response.error && response.error.message || "Output folder unavailable";
  }
});

setInterval(async () => {
  if (!companionConfigured) return;
  try {
    const operation = await browser.runtime.sendMessage({command: "get_harvest_state"});
    status.textContent = operation.message;
    harvest.disabled = !currentUrl || ["running", "selecting"].includes(operation.state);
    selectMedia.disabled = !unsupportedPage || ["running", "selecting"].includes(operation.state);
  } catch (error) {
    // initialize() owns companion availability messaging.
  }
}, 1000);

initialize();
