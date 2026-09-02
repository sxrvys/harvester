"use strict";

const includeUrl = document.querySelector("#include-url");
const report = document.querySelector("#report");
const copy = document.querySelector("#copy");
const github = document.querySelector("#github");
const status = document.querySelector("#status");
let context = {firefox: [], native: [], sanitized_page_url: null};

function line(value) {
  return String(value || "Unavailable").replace(/[\r\n]+/g, " ");
}

function render() {
  const events = [...context.firefox, ...context.native]
    .sort((left, right) => line(left.recorded_at).localeCompare(line(right.recorded_at)))
    .slice(-20);
  const lines = [
    "Harvester bug report",
    "",
    `Harvester: ${browser.runtime.getManifest().version}`,
    `Firefox: ${navigator.userAgent}`
  ];
  if (includeUrl.checked && context.sanitized_page_url) {
    lines.push(`Page: ${context.sanitized_page_url}`);
  }
  lines.push("", `Recent safe diagnostic events: ${events.length}`, "");
  events.forEach((event, index) => lines.push(
    `${index + 1}. ${line(event.recorded_at)}`,
    `   Operation: ${line(event.operation)}`,
    `   Error: ${line(event.code)}`,
    `   Detail: ${line(event.message)}`,
    `   Harvester: ${line(event.application_version)}`,
    ""
  ));
  report.value = lines.join("\n");
}

async function initialize() {
  context = await browser.runtime.sendMessage({command: "get_bug_report_context"});
  includeUrl.disabled = !context.sanitized_page_url;
  render();
}

includeUrl.addEventListener("change", render);
copy.addEventListener("click", () => {
  report.focus();
  report.select();
  const copied = document.execCommand("copy");
  status.textContent = copied ? "Report copied" : "Select the report and copy it manually";
});
github.addEventListener("click", () => {
  const title = encodeURIComponent(`Bug report: Harvester ${browser.runtime.getManifest().version}`);
  const body = encodeURIComponent(report.value);
  browser.tabs.create({url: `https://github.com/sxrvys/harvester/issues/new?title=${title}&body=${body}`});
});

initialize().catch(() => {
  report.value = "Harvester bug report\n\nDiagnostics could not be prepared.";
  status.textContent = "Diagnostics unavailable";
});
