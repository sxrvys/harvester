from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class SavedEnumerationError(RuntimeError):
    pass


class IncrementalBoundaryError(RuntimeError):
    pass


def enumerate_saved(firefox_profile: Path, destination: Path) -> dict[str, Any]:
    """Enumerate Saved metadata only, newest-first from Instagram, then store oldest-first."""

    try:
        import browser_cookie3
        import instaloader
    except ImportError as error:
        raise SavedEnumerationError("Instaloader discovery dependencies are not installed") from error

    cookie_database = firefox_profile / "cookies.sqlite"
    if not cookie_database.is_file():
        raise ValueError("browser profile does not contain cookies.sqlite")

    cookies = {
        cookie.name: cookie.value
        for cookie in browser_cookie3.firefox(cookie_file=str(cookie_database))
        if "instagram.com" in cookie.domain
    }
    if "sessionid" not in cookies:
        raise SavedEnumerationError("authorized Firefox profile has no Instagram session cookie")

    loader = instaloader.Instaloader(
        quiet=True,
        sleep=True,
        max_connection_attempts=1,
        request_timeout=30.0,
        fatal_status_codes=[401, 403, 429],
        iphone_support=False,
    )
    loader.context.update_cookies(cookies)
    username = loader.test_login()
    if not username:
        raise SavedEnumerationError("Instagram did not accept the authorized browser session")
    loader.context.username = username
    profile = instaloader.Profile.from_username(loader.context, username)

    newest_first: list[dict[str, Any]] = []
    try:
        for position, post in enumerate(profile.get_saved_posts(), start=1):
            newest_first.append(_saved_item(post, position))
            if position % 12 == 0:
                _write_index(destination, newest_first, complete=False)
    except Exception as error:
        _write_index(destination, newest_first, complete=False)
        raise SavedEnumerationError(f"Saved enumeration stopped after {len(newest_first)} items") from error

    return _write_index(destination, newest_first, complete=True)


def sync_saved_incremental(
    firefox_profile: Path,
    index_path: Path,
    partial_path: Path,
    known_streak_required: int = 5,
) -> dict[str, Any]:
    """Discover new saves without rescanning beyond a proven known-item boundary."""

    if known_streak_required < 1:
        raise ValueError("known_streak_required must be positive")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if not index.get("complete"):
        raise IncrementalBoundaryError("canonical Saved index is incomplete")

    try:
        posts = _saved_posts(firefox_profile)
        merged, scan = merge_incremental_index(index, posts, known_streak_required)
    except Exception as error:
        partial = {
            "schema_version": 1,
            "complete": False,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "reason": type(error).__name__,
            "canonical_index_unchanged": True,
        }
        _atomic_json(partial_path, partial, prefix=".saved-sync-")
        if isinstance(error, (ValueError, IncrementalBoundaryError, SavedEnumerationError)):
            raise
        raise SavedEnumerationError("incremental Saved sync stopped before a proven boundary") from error

    _atomic_json(index_path, merged, prefix=".saved-index-")
    partial_path.unlink(missing_ok=True)
    return {"index": merged, "scan": scan}


def merge_incremental_index(
    index: dict[str, Any],
    scanned_newest_first: Iterable[dict[str, Any]],
    known_streak_required: int = 5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure merge used by live sync and tests; consumes only through the boundary."""

    if known_streak_required < 1:
        raise ValueError("known_streak_required must be positive")
    if not index.get("complete") or index.get("order") != "oldest-saved-first":
        raise IncrementalBoundaryError("incremental sync requires a complete oldest-first index")

    existing_ids = {item["source_id"] for item in index["items"]}
    scanned_ids: set[str] = set()
    new_items_newest_first: list[dict[str, Any]] = []
    known_streak = 0
    scanned_count = 0
    boundary = "end-of-collection"

    for item in scanned_newest_first:
        source_id = item["source_id"]
        if source_id in scanned_ids:
            continue
        scanned_ids.add(source_id)
        scanned_count += 1
        if source_id in existing_ids:
            known_streak += 1
        else:
            known_streak = 0
            new_items_newest_first.append(dict(item))
        if known_streak >= known_streak_required:
            boundary = "known-streak"
            break

    merged_items = [dict(item) for item in index["items"]] + list(reversed(new_items_newest_first))
    total = len(merged_items)
    for oldest_index, item in enumerate(merged_items):
        item["saved_position_newest_first"] = total - oldest_index

    synced_at = datetime.now(timezone.utc).isoformat()
    merged = {
        **index,
        "count": total,
        "items": merged_items,
        "last_incremental_sync_at": synced_at,
        "last_incremental_sync": {
            "boundary": boundary,
            "known_streak_required": known_streak_required,
            "known_streak_reached": known_streak,
            "scanned_count": scanned_count,
            "new_count": len(new_items_newest_first),
        },
    }
    return merged, merged["last_incremental_sync"]


def _saved_posts(firefox_profile: Path) -> Iterable[dict[str, Any]]:
    try:
        import browser_cookie3
        import instaloader
    except ImportError as error:
        raise SavedEnumerationError("Instaloader discovery dependencies are not installed") from error

    cookie_database = firefox_profile / "cookies.sqlite"
    if not cookie_database.is_file():
        raise ValueError("browser profile does not contain cookies.sqlite")
    cookies = {
        cookie.name: cookie.value
        for cookie in browser_cookie3.firefox(cookie_file=str(cookie_database))
        if "instagram.com" in cookie.domain
    }
    if "sessionid" not in cookies:
        raise SavedEnumerationError("authorized Firefox profile has no Instagram session cookie")

    loader = instaloader.Instaloader(
        quiet=True,
        sleep=True,
        max_connection_attempts=1,
        request_timeout=30.0,
        fatal_status_codes=[401, 403, 429],
        iphone_support=False,
    )
    loader.context.update_cookies(cookies)
    username = loader.test_login()
    if not username:
        raise SavedEnumerationError("Instagram did not accept the authorized browser session")
    loader.context.username = username
    profile = instaloader.Profile.from_username(loader.context, username)

    def items() -> Iterable[dict[str, Any]]:
        for position, post in enumerate(profile.get_saved_posts(), start=1):
            yield _saved_item(post, position)

    return items()


def _saved_item(post: Any, position: int) -> dict[str, Any]:
    return {
        "source": "instagram",
        "source_id": post.shortcode,
        "source_url": f"https://www.instagram.com/p/{post.shortcode}/",
        "post_date": post.date_utc.isoformat(),
        "saved_position_newest_first": position,
        "audio": audio_metadata_from_node(getattr(post, "_node", {})),
    }


def audio_metadata_from_node(node: dict[str, Any]) -> dict[str, Any]:
    """Read only Instagram-provided attribution already present in a Saved post node."""

    clips = node.get("clips_metadata") if isinstance(node, dict) else {}
    clips = clips if isinstance(clips, dict) else {}
    music_info = clips.get("music_info")
    music_info = music_info if isinstance(music_info, dict) else {}
    asset = music_info.get("music_asset_info")
    asset = asset if isinstance(asset, dict) else {}
    original_info = clips.get("original_sound_info")
    original_info = original_info if isinstance(original_info, dict) else {}

    title = _text(asset.get("title"))
    artist = _text(asset.get("display_artist"))
    original_title = _text(original_info.get("original_audio_title"))
    is_original = clips.get("audio_type") == "original_sounds" or bool(original_info)
    label = original_title if is_original else title
    return {
        "label": label,
        "title": None if is_original else title,
        "artist": None if is_original else artist,
        "is_original": is_original,
    }


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _write_index(destination: Path, newest_first: list[dict[str, Any]], complete: bool) -> dict[str, Any]:
    oldest_first = list(reversed(newest_first))
    payload = {
        "schema_version": 1,
        "enumerated_at": datetime.now(timezone.utc).isoformat(),
        "complete": complete,
        "count": len(oldest_first),
        "order": "oldest-saved-first",
        "items": oldest_first,
    }
    _atomic_json(destination, payload, prefix=".saved-index-")
    return payload


def _atomic_json(destination: Path, payload: dict[str, Any], prefix: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
