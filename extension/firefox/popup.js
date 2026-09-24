"use strict";

const page = document.querySelector("#page");
const status = document.querySelector("#status");
const harvest = document.querySelector("#harvest");
const settings = document.querySelector("#settings");
const openOutput = document.querySelector("#open-output");
const archival = document.querySelector("#archival");
const localFile = document.querySelector("#local-file");
const selectMedia = document.querySelector("#select-media");
let currentUrl = null;
let currentTabId = null;
let unsupportedPage = false;
let companionConfigured = false;
let v2Queue = false;
let submitting = false;
let pageUrl = null;
const addQueue = document.querySelector("#add-queue");

function isSupportedUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
    if ((parsed.hostname === "instagram.com" || parsed.hostname === "www.instagram.com")
        && /^\/(p|reel|reels)\/[A-Za-z0-9_-]+\/?$/.test(parsed.pathname)) return true;
    if (parsed.hostname === "www.reddit.com"
        && /^\/r\/[^/?#]+\/comments\/[A-Za-z0-9]+\/[^/?#]+\/?$/.test(parsed.pathname)) return true;
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
      if (["http:", "https:"].includes(parsed.protocol)) pageUrl = url;
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
      v2Queue = Boolean(response.result && response.result.v2_queue) && currentUrl !== null
        && /^(www\.)?(youtube\.com|reddit\.com)$/.test(new URL(currentUrl).hostname);
      if (response.result && response.result.v2_public_pages && pageUrl
          && !/(^|\.)instagram\.com$/.test(new URL(pageUrl).hostname)) {
        currentUrl = pageUrl;
        v2Queue = true;
      }
      document.querySelector("#queue-controls").hidden = !v2Queue;
      addQueue.hidden = !v2Queue;
      if (v2Queue) harvest.textContent = "Harvest now";
      if (v2Queue) openOutput.textContent = "Open Harvester";
      document.querySelector("#picker-note").hidden = !(v2Queue && unsupportedPage);
      const configured = v2Queue || Boolean(response.result && response.result.configured);
      companionConfigured = configured;
      const operation = await browser.runtime.sendMessage({command: "get_harvest_state"});
      harvest.disabled = !configured || !currentUrl || (!v2Queue && ["running", "selecting"].includes(operation.state));
      selectMedia.disabled = !configured || !unsupportedPage || ["running", "selecting"].includes(operation.state);
      status.textContent = v2Queue ? "Ready to try this page. Progress and Send to Chromatron are in Harvester."
        : configured
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
  if (v2Queue) { await submitToQueue(true); return; }
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

async function submitToQueue(start) {
  if (submitting || !currentUrl) return;
  const options = {video_preset: document.querySelector("#video-preset").value,
    audio_preset: document.querySelector("#audio-preset").value};
  try {
    for (const key of ["start", "end"]) {
      const value = document.querySelector(`#clip-${key}`).value.trim();
      if (value) options[key] = parseTime(value);
    }
    if ((options.start || 0) >= 21600 || (options.end !== undefined &&
        (options.end <= (options.start || 0) || options.end > 21600))) throw new Error("range");
  } catch (error) {
    status.textContent = "Use seconds or HH:MM:SS, with end after start and within 6 hours.";
    return;
  }
  submitting = true;
  harvest.disabled = true;
  addQueue.disabled = true;
  status.textContent = "Sending to Harvester 2…";
  try {
    const response = await browser.runtime.sendMessage({command: "enqueue_v2", url: currentUrl,
      name: document.querySelector("#bundle-name").value.trim(), start, options});
    status.textContent = response && response.ok
      ? (response.result.duplicate ? "Already in Harvester 2 — check the app" : start ? "Sent to Harvester 2 — follow progress in the app" : "Added to queue. A running queue picks it up automatically.")
      : response && response.error && response.error.message || "Could not add the video";
  } catch (error) { status.textContent = "Harvester companion unavailable"; }
  finally { submitting = false; harvest.disabled = false; addQueue.disabled = false; }
}
function parseTime(value) {
  const parts = value.split(":");
  if (parts.length > 3 || parts.some(part => !/^\d+(\.\d+)?$/.test(part))) throw new Error("time");
  const numbers = parts.map(Number);
  if (numbers.some(n => !Number.isFinite(n)) || numbers.slice(1).some(n => n >= 60)) throw new Error("time");
  return numbers.reduce((total, n) => total * 60 + n, 0);
}
addQueue.addEventListener("click", () => submitToQueue(false));

settings.addEventListener("click", () => browser.runtime.openOptionsPage());
archival.addEventListener("click", () => browser.tabs.create({url: browser.runtime.getURL("archive.html")}));
localFile.addEventListener("click", async () => {
  const response = await browser.runtime.sendMessage({command: "start_local_file_harvest"});
  if (response && response.accepted) window.close();
  else status.textContent = response && response.state && response.state.message || "Another operation is running";
});
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
  const response = await browser.runtime.sendMessage({command: v2Queue ? "open_v2" : "open_output_folder"});
  if (!response || !response.ok) {
    status.textContent = response && response.error && response.error.message || "Output folder unavailable";
  }
});

setInterval(async () => {
  if (!companionConfigured || v2Queue) return;
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
