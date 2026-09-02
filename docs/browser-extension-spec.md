# Browser extension and native companion specification

Status: implemented Firefox V1 contract.

Implementation note (2026-09-02): the Native Messaging host, supported-source
adapters, one-shot visible-media picker, local-file workflow, settings, and
Instagram Archival Harvest are implemented and manually accepted. Packaging and
Mozilla signing are tracked separately in `release-checklist.md`.

## Purpose

The extension is a small browser control surface for the local harvester engine.
It lets a user explicitly identify one piece of media, choose how it should be
retained, and send that request to the native companion. The extension does not
download or process media itself.

Primary workflow:

```text
Current page -> Harvest this -> native companion -> ordinary local files
```

Secondary Instagram workflow:

```text
Harvest next oldest batch -> existing Saved index and ledger -> local files
```

## Popup

The toolbar popup contains only:

- the current page host and shortened URL;
- **Harvest this**;
- **Select visible media** on unsupported pages;
- the latest safe status message;
- **Open output folder**;
- **Harvest local file**;
- **Archival Harvest**;
- **Settings**;

`Harvest this` is always the primary action. Local-file and Instagram Saved
backlog processing remain visually secondary and use distinct code paths.

## Settings

- Output folder, selected through an operating-system folder picker presented by
  the native companion.
- One global future-audio preset: production WAV, standard WAV, FLAC, 320 kbps
  MP3, or 192 kbps MP3.
- Explicit Firefox profile used for authorized Instagram work.

Originals are always preserved. There is no per-harvest format choice, video
transcoding, or retroactive batch conversion. Generic and supported-source limits
remain enforced in the companion rather than exposed as casual UI controls.

## Local diagnostic access

Archival Harvest shows aggregate lifecycle counts and can open a generated
plain-text view of its structured manual-review state. Settings can similarly
open a plain-text view of the bounded cross-operation diagnostics log. User-facing
actions never launch internal JSON. The interface does not preview media, display
captions, recommend content, rank assets, or create a media library.

## Native Messaging protocol

Transport is browser Native Messaging. There is no listening network port.
Every request and response is one JSON object using Native Messaging's standard
length-prefixed framing.

Request envelope:

```json
{
  "version": 1,
  "command": "harvest_url",
  "request_id": "locally-generated-random-id",
  "payload": {}
}
```

V1 commands:

- `harvest_url`
- `harvest_media_url`
- `harvest_local_file`
- `get_archival_status`
- `scan_saved_posts`
- `harvest_archival_batch`
- `get_settings`
- `update_settings`
- `choose_output_folder`
- `open_output_folder`
- `open_failure_log`
- `open_diagnostics`
- `get_status`

Safe response envelope:

```json
{
  "version": 1,
  "request_id": "locally-generated-random-id",
  "ok": true,
  "result": {}
}
```

Responses may include safe status, progress counts, source identity, and local
output paths. They must never include cookies, headers, signed media URLs, raw
third-party responses, downloader command lines, or unsanitized diagnostics.

## Browser permissions

The Firefox proof requests only:

- `activeTab`, so the current URL is available after a user gesture;
- `nativeMessaging`, for the explicit local companion channel;
- local extension `storage`, for non-sensitive presentation preferences;
- `contextMenus` only if the explicit right-click action is implemented.

The extension does not request cookie, history, webRequest, debugger, proxy,
downloads, or broad permanent host permissions. A media-element picker may use
temporary scripting access granted through `activeTab` only after the user
activates that picker.

## Privacy invariants

- No telemetry, analytics, crash reporting, tracking pixels, remote logging, or
  cloud service.
- No harvester account.
- No browsing-history collection or background page inspection.
- No cookie permission in the extension.
- No copying, exporting, serializing, returning, or logging browser cookies.
- No network interception, request inspection, response inspection, proxying,
  packet capture, developer-tools integration, or browser-cache reading.
- No extraction of authentication headers.
- Settings, ledgers, logs, staging, and media remain on the user's machine.
- Logs redact query strings, signed URLs, headers, session material, and raw
  downloader diagnostics.
- Removing harvester never makes already-created media inaccessible.

Supported adapters may temporarily ask the browser-owned cookie database for
authorization through the local downloader boundary. Authentication material is
never returned to the extension or stored in harvester JSON.

## Generic fallback

For an unsupported current page, the user may explicitly choose:

1. Try the current page URL through the generic extractor.
2. Activate a temporary picker and click one visible `<video>` or `<audio>`
   element in the page or an accessible frame.
3. Paste one direct HTTP(S) media, HLS, or DASH URL.

The picker reads only ordinary properties of the clicked element: `currentSrc`,
`src`, and child `<source src>` values. It stops after selection or cancellation.
It does not scan page content or inspect network activity. After the explicit
picker gesture, it may follow the user's pointer into an accessible frame solely
to attach the one-shot click handler; inaccessible cross-origin frames remain
unsupported.

The companion accepts only HTTP(S) inputs. It rejects `file:`, `data:`,
`javascript:`, and `blob:` URLs, localhost, private-network destinations, and
redirects to those destinations. Stable page URLs are retained instead of
signed media URLs when possible; sensitive query strings are not written to the
ledger.

Clean unsupported outcomes include DRM/encrypted playback, Media Source
Extensions, inaccessible cross-origin frames, short-lived signed resources, and
media requiring unavailable authentication headers. harvester does not attempt
to defeat those boundaries.

## Scope and resource enforcement

- One explicit page, post, or selected media element per `harvest_url` command.
- No playlists, channels, profiles, crawling, adjacent-link discovery, or
  multi-URL expansion.
- A post-owned carousel is one item; its aggregate bytes count toward limits.
- Preflight rejects known duration or size above configured limits.
- Streaming acquisition stops at the actual byte ceiling even when remote
  metadata is missing or inaccurate.
- FFprobe verifies staged duration before archival processing.
- Over-limit staging is cleaned and produces no partial archive bundle.
- Generic inputs with unknowable duration are rejected rather than risking an
  unbounded download.
- No retries for ordinary failures; authentication, challenge, and rate-limit
  signals stop the active batch.

## Initial safe error codes

- `unsupported_source`
- `unsupported_media`
- `invalid_url`
- `unsafe_url`
- `duration_limit`
- `size_limit`
- `output_unavailable`
- `authentication_stop`
- `rate_limit_stop`
- `companion_unavailable`
- `acquisition_failed`
- `processing_failed`
- `invalid_request`
- `unsupported_command`

Human-readable messages may accompany these codes but must be sanitized.

## Implemented sequence

1. Native host reads and writes versioned messages over standard input/output.
2. `get_status` and `harvest_url` call the existing local engine.
3. Minimal Firefox popup sends the current URL after an explicit click.
4. Add settings and operating-system destination selection.
5. Add `harvest_oldest_batch` using the existing ledger and batch workflow.
6. Add Open Folder and aggregate archival status.
7. Add the explicit generic media-element picker.
8. Add explicit one-file local harvesting and safe failure-log access.
9. Package and sign Firefox V1 with its macOS companion.

Chrome derivation is post-V1 work and requires its own browser-specific native
host manifest and acceptance pass.

No later step begins by expanding permissions. Any permission change requires a
documented feature need and explicit review against the privacy invariants.
