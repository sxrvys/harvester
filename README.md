# harvester

harvester is a local-first tool for turning media the user intentionally saved
online into durable, predictable creative-media bundles.

Its privacy, ownership, and
least-privilege commitments are defined in
[`PROJECT_CONSTITUTION.md`](PROJECT_CONSTITUTION.md). Current and intended
licensing status is recorded in [`LICENSING.md`](LICENSING.md).

V0 has one acceptance target: transform one user-identified Instagram post into
one local bundle containing preserved originals, useful derivatives, and
provenance metadata. The project does not access a browser session or Instagram
account unless the user explicitly authorizes that step.

## Current status

- The V0 output contract and real-workflow acceptance test are complete.
- Source-agnostic item, archive, and media-processing primitives are present.
- Single-URL Instagram acquisition is isolated behind a source adapter and has
  completed its first authorized live proof on 2026-08-29.
- Saved discovery uses a private Git-ignored JSON index; a first oldest-ten batch
  completed nine audio/video bundles and deferred one image-only carousel.
- A generated readable WAV was verified in the user's real audio workflow as
  48 kHz, 24-bit stereo with the correct duration and waveform.
- Incremental Saved sync scans newest-first and stops after five consecutive
  ledgered IDs, so routine updates do not rescan the complete collection.
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

The approved glyph master and an editable theme-adaptive SVG live under
[`assets/brand/`](assets/brand/). The SVG uses the surrounding text color, so it
can render black in light browser themes and white in dark browser themes.

## Local checks

Requires Python 3.11+ and FFmpeg/FFprobe on `PATH`.

```sh
python3 -m unittest discover -s tests -v
```

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
