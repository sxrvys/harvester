# Browser extension and native companion specification

Status: agreed product contract for the Firefox-first proof of concept.

Implementation note (2026-08-30): the Native Messaging host, settings flow,
background-owned Instagram `harvest_url`, durable safe popup status, output-folder
action, and ledger reconciliation are implemented and manually accepted.

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
- **Harvest next oldest batch** under an Instagram Saved section;
- the latest safe status message;
- **Open output folder**;
- **Settings**;
- **View database**.

`Harvest this` is always the primary action. Saved backlog processing is
visually secondary and available only when its adapter is configured.

## Settings

- Output folder, selected through an operating-system folder picker presented by
  the native companion.
- Output switches:
  - preserve original;
  - keep playable video;
  - extract 48 kHz/24-bit stereo WAV.
- Convenience presets:
  - audio only;
  - video only;
  - video plus separate WAV;
  - full archive.
- Generic maximum duration: 10 minutes by default.
- Generic maximum source bytes: 500 MB by default.
- Instagram batch count: 10 by default.
- Instagram inter-item delay: random 10-15 seconds by default and never below
  10 seconds.
- Explicit Firefox profile used for authorized Instagram work.

At least one output switch must remain enabled. A deliberate one-item override
may exceed the defaults, but the companion retains an absolute ceiling of 30
minutes and 2 GB to prevent accidental or scope-breaking jobs.

## Database view

The database action opens a small local ledger view, not a media library. It may
show only:

- readable name;
- source;
- lifecycle status;
- output path;
- harvest date;
- Open Folder;
- Open raw JSON.

It does not preview media, display captions, recommend content, rank assets, or
create an organizational database beyond the authoritative JSON ledger.

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

Initial commands:

- `harvest_url`
- `harvest_oldest_batch`
- `get_settings`
- `update_settings`
- `choose_output_folder`
- `open_output_folder`
- `get_ledger`
- `open_raw_ledger`
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
   element.
3. Paste one direct HTTP(S) media, HLS, or DASH URL.

The picker reads only ordinary properties of the clicked element: `currentSrc`,
`src`, and child `<source src>` values. It stops after selection or cancellation.
It does not scan the page or inspect network activity.

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

## Implementation sequence

1. Native host reads and writes versioned messages over standard input/output.
2. `get_status` and `harvest_url` call the existing local engine.
3. Minimal Firefox popup sends the current URL after an explicit click.
4. Add settings and operating-system destination selection.
5. Add `harvest_oldest_batch` using the existing ledger and batch workflow.
6. Add Open Folder and the minimal ledger view.
7. Add the explicit generic media-element picker.
8. Derive Chrome packaging from the same WebExtension code and a browser-specific
   native-host registration manifest.

No later step begins by expanding permissions. Any permission change requires a
documented feature need and explicit review against the privacy invariants.
