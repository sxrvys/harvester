"use strict";

(() => {
  if (window.__harvesterPickerActive) return;
  window.__harvesterPickerActive = true;
  const registrations = [];
  let highlighted = null;

  function clearHighlight() {
    if (!highlighted) return;
    highlighted.badge.remove();
    highlighted.element.style.outline = highlighted.outline;
    highlighted.element.style.outlineOffset = highlighted.outlineOffset;
    highlighted = null;
  }

  function highlight(element) {
    if (highlighted && highlighted.element === element) return;
    clearHighlight();
    highlighted = {
      element,
      outline: element.style.outline,
      outlineOffset: element.style.outlineOffset,
      badge: element.ownerDocument.createElement("button")
    };
    element.style.outline = "3px solid #35c46a";
    element.style.outlineOffset = "3px";
    const rectangle = element.getBoundingClientRect();
    const badge = highlighted.badge;
    badge.type = "button";
    badge.textContent = "Harvest media";
    badge.setAttribute("aria-label", "Harvest this media element");
    Object.assign(badge.style, {
      position: "fixed",
      left: `${Math.max(6, rectangle.left + 8)}px`,
      top: `${Math.max(6, rectangle.top + 8)}px`,
      zIndex: "2147483647",
      padding: "7px 10px",
      border: "2px solid #ffffff",
      borderRadius: "5px",
      background: "#17883f",
      color: "#ffffff",
      font: "600 13px system-ui, sans-serif",
      cursor: "pointer",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.35)"
    });
    badge.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      select(element);
    }, true);
    element.ownerDocument.body.appendChild(badge);
  }

  function register(targetDocument) {
    if (!targetDocument || registrations.some((entry) => entry.document === targetDocument)) return;
    const root = targetDocument.documentElement;
    const previousCursor = root.style.cursor;
    root.style.cursor = "crosshair";
    targetDocument.addEventListener("pointerdown", choose, true);
    targetDocument.addEventListener("keydown", cancel, true);
    targetDocument.addEventListener("mouseover", enterFrame, true);
    targetDocument.addEventListener("mouseover", showTarget, true);
    targetDocument.addEventListener("mouseout", hideTarget, true);
    registrations.push({document: targetDocument, root, previousCursor});
  }

  function cleanup() {
    for (const entry of registrations) {
      entry.document.removeEventListener("pointerdown", choose, true);
      entry.document.removeEventListener("keydown", cancel, true);
      entry.document.removeEventListener("mouseover", enterFrame, true);
      entry.document.removeEventListener("mouseover", showTarget, true);
      entry.document.removeEventListener("mouseout", hideTarget, true);
      entry.root.style.cursor = entry.previousCursor;
    }
    clearHighlight();
    registrations.length = 0;
    browser.runtime.onMessage.removeListener(stop);
    delete window.__harvesterPickerActive;
  }

  function stop(message) {
    if (message && message.command === "stop_picker") cleanup();
  }

  function enterFrame(event) {
    const frame = event.target;
    if (!frame || !["IFRAME", "FRAME"].includes(frame.tagName)) return;
    try {
      register(frame.contentDocument);
    } catch (error) {
      // Cross-origin and otherwise inaccessible frames remain unsupported.
    }
  }

  function showTarget(event) {
    const element = event.target.closest && event.target.closest("video, audio");
    if (element) highlight(element);
  }

  function hideTarget(event) {
    if (!highlighted) return;
    const next = event.relatedTarget;
    if (next && (highlighted.element.contains(next) || highlighted.badge.contains(next))) return;
    clearHighlight();
  }

  function ordinarySources(element) {
    const values = [element.currentSrc, element.src];
    for (const child of element.children) {
      if (child.tagName === "SOURCE") values.push(child.src);
    }
    return values.filter((value) => typeof value === "string" && value.trim());
  }

  function mediaTarget(event) {
    const direct = event.target.closest && event.target.closest("video, audio");
    if (direct) return direct;
    const path = typeof event.composedPath === "function" ? event.composedPath() : [];
    return path.find((element) => element && ["VIDEO", "AUDIO"].includes(element.tagName)) || null;
  }

  function select(element) {
    const mediaUrl = ordinarySources(element)[0];
    cleanup();
    browser.runtime.sendMessage({command: "picker_selection", media_url: mediaUrl || null});
  }

  function choose(event) {
    const element = mediaTarget(event);
    if (!element) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    select(element);
  }

  function cancel(event) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    cleanup();
    browser.runtime.sendMessage({command: "picker_cancelled"});
  }

  register(document);
  browser.runtime.onMessage.addListener(stop);
})();
