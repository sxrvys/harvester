from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
import unicodedata


@dataclass(frozen=True)
class HarvestItem:
    """Source identity and provenance for one intentional harvest."""

    source: str
    source_id: str
    source_url: str | None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    author: str | None = None
    posted_at: datetime | None = None
    caption: str | None = None
    title: str | None = None
    creator: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}_{self.source_id}"

    @property
    def directory_name(self) -> str:
        title, creator = self.title, self.creator
        if not title and self.caption:
            title, creator = title_from_caption(self.caption)
        descriptive = "_".join(part for part in (slugify(title), slugify(creator)) if part)
        descriptive = descriptive[:72].rstrip("-_")
        return f"{descriptive}_{self.source_id}" if descriptive else self.key

    def __post_init__(self) -> None:
        for label, value in (("source", self.source), ("source_id", self.source_id)):
            if not value or not all(character.isalnum() or character in "-_" for character in value):
                raise ValueError(f"{label} must contain only letters, numbers, '-' or '_'")
        if self.source_url is None:
            if self.source != "local":
                raise ValueError("only local items may omit source_url")
        elif not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an HTTP(S) URL")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")


def title_from_caption(caption: str) -> tuple[str | None, str | None]:
    first_line = next((line.strip() for line in caption.splitlines() if line.strip()), "")
    if not first_line:
        return None, None
    parts = re.split(r"\s+[–—-]\s+", first_line, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (first_line, None)


def slugify(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value)).strip("-")[:80]
