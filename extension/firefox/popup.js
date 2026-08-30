"use strict";

const NATIVE_APPLICATION = "com.harvester.native";
const page = document.querySelector("#page");
const status = document.querySelector("#status");

function requestId() {
  return crypto.randomUUID();
}

async function initialize() {
  try {
    const tabs = await browser.tabs.query({active: true, currentWindow: true});
    const url = tabs[0] && tabs[0].url;
    if (url) {
      const parsed = new URL(url);
      page.textContent = `${parsed.host}${parsed.pathname}`;
      page.title = url;
    }

    const response = await browser.runtime.sendNativeMessage(NATIVE_APPLICATION, {
      version: 1,
      command: "get_status",
      request_id: requestId(),
      payload: {}
    });
    status.textContent = response && response.ok
      ? "Local companion ready"
      : "Local companion returned an error";
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

initialize();
