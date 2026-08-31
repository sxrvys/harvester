"use strict";

(() => {
  if (window.__harvesterPickerActive) return;
  window.__harvesterPickerActive = true;
  const registrations = [];
  let highlighted = null;

  function clearHighlight() {
    if (!highlighted) return;
    highlighted.badge.remove();
    highlighted.overlay.remove();
    highlighted.element.style.setProperty("outline", highlighted.outline, highlighted.outlinePriority);
    highlighted.element.style.setProperty(
      "outline-offset", highlighted.outlineOffset, highlighted.outlineOffsetPriority
    );
    highlighted.element.style.setProperty("box-shadow", highlighted.boxShadow, highlighted.boxShadowPriority);
    highlighted = null;
  }

  function highlight(element) {
    if (highlighted && highlighted.element === element) {
      positionControls(element, highlighted.overlay, highlighted.badge);
      return;
    }
    clearHighlight();
    highlighted = {
      element,
      outline: element.style.getPropertyValue("outline"),
      outlinePriority: element.style.getPropertyPriority("outline"),
      outlineOffset: element.style.getPropertyValue("outline-offset"),
      outlineOffsetPriority: element.style.getPropertyPriority("outline-offset"),
      boxShadow: element.style.getPropertyValue("box-shadow"),
      boxShadowPriority: element.style.getPropertyPriority("box-shadow"),
      overlay: element.ownerDocument.createElement("div"),
      badge: element.ownerDocument.createElement("button")
    };
    element.style.setProperty("outline", "3px solid #35c46a", "important");
    element.style.setProperty("outline-offset", "3px", "important");
    element.style.setProperty("box-shadow", "0 0 0 4px rgba(53, 196, 106, 0.3)", "important");
    const rectangle = element.getBoundingClientRect();
    const overlay = highlighted.overlay;
    overlay.setAttribute("aria-hidden", "true");
    Object.assign(overlay.style, {
      position: "fixed",
      zIndex: "2147483646",
      boxSizing: "border-box",
      border: "4px solid #35c46a",
      boxShadow: "inset 0 0 0 2px rgba(255, 255, 255, 0.8)",
      pointerEvents: "none"
    });
    const badge = highlighted.badge;
    badge.type = "button";
    badge.textContent = "Harvest media";
    badge.setAttribute("aria-label", "Harvest this media element");
    Object.assign(badge.style, {
      position: "fixed",
      zIndex: "2147483647",
      padding: "7px 10px",
      border: "2px solid #ffffff",
      borderRadius: "5px",
      background: "#17883f",
      color: "#ffffff",
      font: "600 13px system-ui, sans-serif",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.35)"
    });
    badge.style.setProperty("cursor", "pointer", "important");
    badge.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      select(element);
    }, true);
    positionControls(element, overlay, badge);
    element.ownerDocument.body.appendChild(overlay);
    element.ownerDocument.body.appendChild(badge);
  }

  function positionControls(element, overlay, badge) {
    const rectangle = element.getBoundingClientRect();
    Object.assign(overlay.style, {
      left: `${rectangle.left}px`,
      top: `${rectangle.top}px`,
      width: `${rectangle.width}px`,
      height: `${rectangle.height}px`
    });
    Object.assign(badge.style, {
      left: `${Math.max(6, rectangle.left + 8)}px`,
      top: `${Math.max(6, rectangle.top + 8)}px`
    });
  }

  function register(targetDocument) {
    if (!targetDocument || registrations.some((entry) => entry.document === targetDocument)) return;
    const root = targetDocument.documentElement;
    const style = targetDocument.createElement("style");
    style.textContent = [
      "html.__harvester-picker-active,",
      "html.__harvester-picker-active body,",
      "html.__harvester-picker-active body * { cursor: crosshair !important; }"
    ].join("\n");
    (targetDocument.head || root).appendChild(style);
    root.classList.add("__harvester-picker-active");
    targetDocument.addEventListener("pointerdown", choose, true);
    targetDocument.addEventListener("keydown", cancel, true);
    targetDocument.addEventListener("mouseover", enterFrame, true);
    targetDocument.addEventListener("pointermove", showTarget, true);
    registrations.push({document: targetDocument, root, style});
  }

  function cleanup() {
    for (const entry of registrations) {
      entry.document.removeEventListener("pointerdown", choose, true);
      entry.document.removeEventListener("keydown", cancel, true);
      entry.document.removeEventListener("mouseover", enterFrame, true);
      entry.document.removeEventListener("pointermove", showTarget, true);
      entry.root.classList.remove("__harvester-picker-active");
      entry.style.remove();
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
    const element = mediaTarget(event);
    if (element) highlight(element);
    else if (!highlighted || event.target !== highlighted.badge) clearHighlight();
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
    const composed = path.find((element) => element && ["VIDEO", "AUDIO"].includes(element.tagName));
    if (composed) return composed;
    const documentAtPointer = event.target && event.target.ownerDocument;
    if (!documentAtPointer || typeof documentAtPointer.elementsFromPoint !== "function") return null;
    const stack = documentAtPointer.elementsFromPoint(event.clientX, event.clientY);
    for (const element of stack) {
      if (["VIDEO", "AUDIO"].includes(element.tagName)) return element;
      const nested = element.closest && element.closest("video, audio");
      if (nested) return nested;
    }
    return null;
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
