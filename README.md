# harvester

harvester is a local-first tool for turning media the user intentionally saved
online into durable, predictable creative-media bundles.

Its privacy, ownership, and
least-privilege commitments are defined in
[`PROJECT_CONSTITUTION.md`](PROJECT_CONSTITUTION.md). Current and intended
licensing status is recorded in [`LICENSING.md`](LICENSING.md).

The current Firefox prototype turns one explicitly selected Instagram, YouTube,
or Reddit post—or one visible media element or local file—into a local bundle
containing preserved originals, useful derivatives, and provenance metadata.
Instagram also has a separate, ledger-backed archival workflow for the user's
Saved collection. The project does not access a browser session or account unless
the user explicitly initiates an operation that requires it.

## Current status

- Firefox and its native companion have completed live acceptance for one-off
  Instagram, YouTube, and Reddit harvesting.
- The bounded visible-media picker has passed on an unsupported iframe-based page.
- One-file local harvesting has passed with a Finder-selected Archive.org video;
  its preserved original and playable derivative were byte-identical to the source.
- Audio derivatives support five global presets: two WAV, one FLAC, and two MP3.
- The Instagram Archival Harvest screen can incrementally scan Saved posts and run
  explicitly initiated, paced, oldest-first batches against its private ledger.
- Settings can choose an output folder through Finder and automatically detect
  Firefox's declared default profile, with manual profile editing kept advanced.
- All 86 automated tests pass. Packaging, signing, and distribution remain paused
  until core functionality receives final review and explicit approval.
- No code from RADIO HARVEST is used or required.

See [`docs/v0-technical-plan.md`](docs/v0-technical-plan.md) and
[`docs/instagram-acquisition.md`](docs/instagram-acquisition.md).

## Browser extension direction

The intended interface is a small Firefox-first WebExtension backed by the
local harvester engine through Native Messaging. Its primary action is an
explicit **Harvest this** command for the current page or pasted URL. It does
not inspect traffic, collect browsing history, retain cookies, send telemetry,
or become a media-library application.

The agreed interface, permission boundary, resource limits, and native message
contract are recorded in
[`docs/browser-extension-spec.md`](docs/browser-extension-spec.md).

The proof-of-concept host reads its private configuration from
`~/.config/harvester/settings.json` (or `HARVESTER_SETTINGS_PATH`). The Firefox
Settings screen stores the output folder and explicit Firefox profile there;
the file is written atomically with user-only permissions. The popup enables
**Harvest this** only when both paths are configured and valid, and the native
host verifies them again before every run.

Active harvests are owned by the extension background script, so closing the
popup does not interrupt work. Safe progress and completion state persist in
local extension storage. One-off harvests create bundles without lifecycle-ledger
bookkeeping; the ledger is reserved for archival queues. **Open output folder**
delegates to the verified native path.

On unsupported HTTP(S) pages, **Select visible media** activates a temporary,
one-shot picker. It follows the user's pointer into accessible frames, outlines
only the hovered `<video>` or `<audio>`, and displays **Harvest media** for an
unambiguous selection. It reads only that selected element's ordinary media URLs
and performs one bounded attempt; it does not scan page content or inspect traffic.
The accepted proof is recorded in
[`docs/unsupported-site-picker-acceptance.md`](docs/unsupported-site-picker-acceptance.md).

Canonical YouTube watch pages use a separate bounded adapter behind **Harvest
this**. It accepts exactly one video ID and forces no-playlist mode,
applies the same 10-minute and 500 MB ceilings, and never enumerates channels,
playlists, search results, recommendations, or account collections.
The first live Firefox acceptance passed on 2026-08-30 with YouTube video
`URwmZq70_DU`, producing a preserved WebM, playable WebM, and 48 kHz/24-bit
stereo WAV without adding an archival-ledger entry.

Canonical Reddit post pages use a separate bounded adapter behind **Harvest
this**. It accepts one `/r/.../comments/<post-id>/<slug>/` URL, acquires at most
one attached media result, applies the same resource limits, and never enumerates
feeds, subreddits, profiles, comments, Saved collections, or related posts.
Its first live Firefox acceptance passed on 2026-08-30 with a single Reddit post,
producing a preserved MP4, identical playable MP4, and configured WAV derivative
without adding an archival-ledger entry.

Settings provide one global audio-derivative preset for future bundles:
Production WAV (48 kHz/24-bit), Standard WAV (44.1 kHz/16-bit), FLAC
(48 kHz/24-bit), MP3 (320 kbps), or MP3 (192 kbps). Production WAV remains the
default. Harvester preserves the acquired original and generates one audio
derivative; it does not offer per-harvest choices, video transcoding, or
retroactive batch conversion. Each derivative records its named encoding preset.

**Harvest local file** opens a native Finder picker and ingests exactly one audio
or video file. The selected path never enters the extension or metadata; only the
basename, size, content hash, duration, and media facts are retained. Harvester
preserves the original, generates the configured audio derivative when applicable,
and does not accept folders, watch directories, multiple selection, or batch
conversion. The accepted proof is recorded in
[`docs/local-file-acceptance.md`](docs/local-file-acceptance.md).

The extension also has a distinct Instagram **Archival Harvest** screen backed by
the private Saved index and lifecycle ledger. It exposes explicit newest-first
incremental scanning to a five-known-item boundary and explicit oldest-first
batches with size 1–25 and randomized 10–300 second delay bounds. Downloads are
sequential, ordinary failures are not retried, and authentication/rate-limit
signals stop the batch. This workflow is Instagram-only and remains separate
from ledger-free one-off harvests.

Acceptance contracts and manual proof results for the newer workflows live in
[`docs/reddit-single-post-acceptance.md`](docs/reddit-single-post-acceptance.md),
[`docs/archival-harvest-acceptance.md`](docs/archival-harvest-acceptance.md), and
[`docs/local-file-acceptance.md`](docs/local-file-acceptance.md).

The approved glyph master and an editable theme-adaptive SVG live under
[`assets/brand/`](assets/brand/). The SVG uses the surrounding text color, so it
can render black in light browser themes and white in dark browser themes.

## Local checks

Requires Python 3.11+ and FFmpeg/FFprobe on `PATH`.

```sh
python3 -m unittest discover -s tests -v
```

Firefox V1 release artifacts are built separately because the browser extension
communicates with a local macOS companion:

```sh
scripts/build-firefox-extension
scripts/build-macos-companion
```

The companion package contains its installer and Python source but no settings,
authentication material, ledger, or media. See
[`docs/release-checklist.md`](docs/release-checklist.md) for validation, native
registration, and Mozilla-signing requirements.

The V1 release target is Firefox desktop 142 or newer on macOS. The extension
declares that it collects or transmits no data, and the installed companion keeps
settings, archival state, diagnostics, and output local to the user's machine.
Settings exposes a plain-text view of the newest 100 sanitized operational
failures for support and contributor debugging; internal JSON, sensitive URLs,
authentication material, and local source paths are never opened or displayed.

Offline archive checks and naming review:

```sh
harvester audit --archive-root archive
harvester names-preview --archive-root archive
harvester batch-review --batch state/BATCH.json
```

The audit is read-only. Naming preview never renames a bundle; it shows proposed
bounded names and honors `manual_title` / `manual_creator` metadata overrides.
Batch review is also read-only. It combines batch, ledger, and bundle metadata
into a concise review report with lifecycle status, media inventory, duration,
caption excerpt, naming proposal, and platform-provided audio attribution.

`batch-oldest` creates a unique timestamped record under `state/batches/` when
`--state` is omitted. After the bounded run it synchronizes the lifecycle ledger
and prints the batch review automatically. To resume an interrupted run, pass
its exact record back with `--state`; terminal failures are not retried.
The first-corpus naming analysis and editorial proposals are recorded in
[`docs/naming-review.md`](docs/naming-review.md).

Media asset filenames omit the Instagram ID and use the readable bundle stem:

```text
<readable-stem>__audio.wav
<readable-stem>__video.mp4
original/<readable-stem>__original.mp4
```

The bundle folder, metadata, Saved index, and `state/item-ledger.json` retain the
stable identity. File presence and filenames are never used to decide whether an
item is eligible for reacquisition.

Approved naming migrations keep Instagram IDs on bundle folders while giving
all retained media assets clean, readable role-based names.

## Recoverable deletion

The core deletion action requires an exact ledgered item and an explicit Trash
destination. It verifies the bundle's embedded source identity, moves only that
bundle, and durably records `retired-deleted` so it cannot be reacquired:

```sh
harvester archive-delete SOURCE_ID --trash-root /path/to/trash
```

The operation refuses missing bundles, identity mismatches, paths outside the
archive root, and existing Trash destinations. This command is the backend
contract intended for a later front-end Delete control.

Live acquisition requires an exact URL, an exact Firefox profile path, and the
user's explicit authorization for that run. It is intentionally not configured
through a default profile or stored cookie file.
