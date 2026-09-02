"use strict";

(() => {
  if (globalThis.__harvesterArchiveScannerInstalled) return;
  globalThis.__harvesterArchiveScannerInstalled = true;

  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function visiblePostLinks() {
    const found = [];
    for (const anchor of document.querySelectorAll("a[href]")) {
      try {
        const url = new URL(anchor.href, location.href);
        if (!['instagram.com', 'www.instagram.com'].includes(url.hostname)) continue;
        const match = url.pathname.match(/^\/(?:p|reel|reels)\/([A-Za-z0-9_-]+)\/?/);
        if (!match) continue;
        found.push({
          source_id: match[1],
          source_url: `https://www.instagram.com/p/${match[1]}/`
        });
      } catch (error) {
        // Ignore malformed page-owned links.
      }
    }
    return found;
  }

  function postFromUrl(raw) {
    try {
      const url = new URL(raw, location.href);
      if (!['instagram.com', 'www.instagram.com'].includes(url.hostname)) return null;
      const match = url.pathname.match(/^\/(?:p|reel|reels)\/([A-Za-z0-9_-]+)\/?/);
      return match ? {source_id: match[1], source_url: `https://www.instagram.com/p/${match[1]}/`} : null;
    } catch (error) {
      return null;
    }
  }

  async function postsFromVisibleTiles() {
    window.scrollTo({top: 0, behavior: "instant"});
    await wait(700);
    const candidates = [...document.querySelectorAll("main img")].filter((image) => {
      const rectangle = image.getBoundingClientRect();
      return rectangle.width >= 120 && rectangle.height >= 120 && rectangle.bottom > 0 && rectangle.top < innerHeight;
    });
    browser.runtime.sendMessage({command: "archive_tile_progress", candidates: candidates.length, found: 0}).catch(() => undefined);
    const found = [];
    for (const image of candidates.slice(0, 100)) {
      const target = image.closest("[role=link], [role=button], button, [tabindex='0']") || image;
      const before = location.href;
      target.click();
      await wait(900);
      let post = postFromUrl(location.href);
      if (!post) {
        const dialogLink = document.querySelector("[role=dialog] a[href*='/p/'], [role=dialog] a[href*='/reel/'], [role=dialog] a[href*='/reels/']");
        post = dialogLink ? postFromUrl(dialogLink.href) : null;
      }
      if (post && !found.some((item) => item.source_id === post.source_id)) found.push(post);
      browser.runtime.sendMessage({command: "archive_tile_progress", candidates: candidates.length, found: found.length}).catch(() => undefined);
      document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", code: "Escape", bubbles: true}));
      await wait(350);
      if (location.href !== before) {
        history.back();
        await wait(700);
      }
    }
    return {items: found, candidates: candidates.length};
  }

  async function scan(knownSourceIds) {
    const known = new Set(knownSourceIds);
    const seen = new Set();
    const items = [];
    let knownStreak = 0;
    let idleRounds = 0;
    let examinedLinks = 0;
    window.scrollTo({top: 0, behavior: "instant"});
    await wait(2000);

    for (let round = 0; round < 300 && items.length < 5000; round += 1) {
      let added = 0;
      const pageLinks = document.querySelectorAll("a[href]").length;
      examinedLinks = Math.max(examinedLinks, pageLinks);
      for (const item of visiblePostLinks()) {
        if (seen.has(item.source_id)) continue;
        seen.add(item.source_id);
        items.push(item);
        added += 1;
        knownStreak = known.has(item.source_id) ? knownStreak + 1 : 0;
        if (knownStreak >= 5) break;
      }
      browser.runtime.sendMessage({command: "archive_scan_progress", count: items.length, examined_links: examinedLinks, round: round + 1}).catch(() => undefined);
      if (knownStreak >= 5) return {items, boundary: "known-streak", examined_links: examinedLinks, rounds: round + 1};
      idleRounds = added ? 0 : idleRounds + 1;
      const idleLimit = items.length ? 5 : 20;
      if (idleRounds >= idleLimit) {
        if (!items.length) {
          const fallback = await postsFromVisibleTiles();
          return {items: fallback.items, boundary: "visible-tiles", examined_links: examinedLinks, examined_tiles: fallback.candidates, rounds: round + 1};
        }
        return {items, boundary: "end-of-page", examined_links: examinedLinks, rounds: round + 1};
      }
      window.scrollTo({top: document.documentElement.scrollHeight, behavior: "smooth"});
      await wait(900);
    }
    return {items, boundary: "bounded-limit", examined_links: examinedLinks, rounds: 300};
  }

  browser.runtime.onMessage.addListener((message) => {
    if (!message || message.command !== "scan_instagram_archive_page") return undefined;
    const known = Array.isArray(message.known_source_ids) ? message.known_source_ids : [];
    return scan(known);
  });
})();
