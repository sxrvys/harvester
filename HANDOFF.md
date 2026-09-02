# harvester project handoff

Last updated: 2026-08-30

Read this document before changing the project. It records decisions and
acceptance results established with the project owner.

## Product purpose

harvester is a local-first tool for collecting individual pieces of interesting
audio/video that a user explicitly selects online. It preserves useful media,
separates component parts when requested, and writes ordinary files to a
user-selected local destination.

Instagram is the first supported source. Later adapters may support Reddit,
YouTube, and carefully bounded generic media URLs. This is not a media-library
application, generic page scraper, crawler, recommendation engine, playlist
downloader, or account-archiving service.

The ideal interface is a small Firefox-first browser extension, followed later
by Chrome support from the same WebExtension codebase.

## Non-negotiable privacy boundary

- No harvester account or separate Instagram login.
- No telemetry, analytics, tracking, cloud service, or remote logging.
- No stored or exported cookies, passwords, authentication headers, or signed
  media URLs.
- No browser-history collection or background page inspection.
- No traffic interception or inspection, proxying, `webRequest`, debugger,
  packet capture, browser-cache reading, or developer-tools integration.
- Use only an explicit user gesture such as **Harvest this**.
- The extension requests only the permissions needed for the active operation.
- Instagram authentication remains owned by the user's existing Firefox
  session. For an explicitly authorized operation, the native downloader may
  temporarily consult the selected Firefox profile through its browser-cookie
  interface. Authentication material must never be returned to the extension
  or persisted in harvester JSON/logs.
- Ask before accessing authentication material or using a real account.
- Removing harvester must not make existing downloaded media inaccessible.

See `PROJECT_CONSTITUTION.md` and `docs/browser-extension-spec.md`.

## Agreed browser interface

Primary action:

```text
Current page or pasted URL -> Harvest this -> native companion -> local files
```

Secondary Instagram action:

```text
Harvest next oldest batch -> Saved index/ledger -> local files
```

The popup should remain small. Planned controls are Harvest this, the secondary
Saved-batch command, status, Open output folder, Settings, and View database.
The database view is a minimal JSON-ledger view, not a media browser; it does not
need audio/video previews or caption/attribution review.

Generic fallback may later try one current page URL, let the user explicitly
select one visible video/audio element, or accept one direct HTTP(S) media URL.
It must not crawl or inspect network activity and must fail cleanly for DRM,
blob/MSE, unavailable authentication headers, or inaccessible frames.

Resource limits agreed for generic inputs:

- Default maximum duration: 10 minutes.
- Default maximum source size: 500 MB.
- Absolute safety ceiling: 30 minutes / 2 GB.
- A deliberate one-item override may exceed defaults but not the ceiling.
- No playlists, profiles, channels, crawling, or multi-URL expansion.

## Naming and storage decisions

- Product name is **harvester**. The earlier spellings `harvestrr` and
  `harvestr` are obsolete and must not be reintroduced.
- Repository: `https://github.com/sxrvys/harvester` (private for now).
- Local repository: `/Users/scott/Documents/harvester`.
- Python package and CLI name: `harvester`.
- Firefox extension ID: `@harvester-sxrvys`.
- Native Messaging application: `com.harvester.native`.
- Approved glyph assets are under `assets/brand/`; explicit black/white toolbar
  variants support light and dark themes.
- Media filenames use readable stems and roles, without Instagram IDs:

```text
<readable-stem>__audio.wav
<readable-stem>__video.mp4
original/<readable-stem>__original.mp4
```

- Stable source IDs live in bundle metadata, the Saved index, and
  `state/item-ledger.json`, not media filenames or embedded tags.
- The JSON ledger is authoritative for deduplication. Deleting a media folder
  does not make an item eligible for reacquisition.
- Durable terminal statuses include `retired-used` and `retired-deleted`.
- Failures are not retried automatically; defer them to manual review.
- Image-only carousels are lower priority and may be skipped/deferred.
- Platform-provided artist/song fields may be stored exactly when Instagram
  supplies them. Do not perform audio recognition or infer music metadata.

## Instagram backlog decisions

- Work oldest-to-newest because older saved material is more likely to vanish.
- Batch count defaults to 10.
- Inter-item delay is randomized from 10–15 seconds and never below 10 seconds.
- No retries for normal failures. Authentication, challenge, or rate-limit
  signals stop the active batch.
- Incremental Saved sync scans newest-first and stops after five consecutive
  already-ledgered items. The owner does not intend to unsave items.

## Completed acquisition work

- Single explicitly supplied Instagram post proof completed.
- Saved discovery/index and incremental-sync logic implemented.
- First oldest-ten batch completed nine audio/video bundles and deferred one
  image-only carousel.
- A later ten-item batch completed successfully; four dance/C-walk bundles were
  subsequently retired and deleted through the ledger-aware deletion workflow.
- Current retained archive was last audited at 14 bundles and 43 files with zero
  errors/warnings.
- Real audio workflow acceptance passed: the owner imported
  `redneck-vampire_michael-ray-vanmeter__audio.wav` and confirmed 48 kHz,
  24-bit stereo WAV, correct duration, waveform, and filename.
- Exact platform attribution was verified with Instagram reel `DbG-S_oRk5s`:
  Magazine 60 — Don Quichotte. Older bundles do not require backfilling.

The archive and private state are intentionally Git-ignored. Preserve them.

## Browser/native milestone completed

Commit `91f330d` renamed the project to harvester and added the browser bridge.
It is pushed to `main` in the private GitHub repository.

Implemented:

- `src/harvester/native_host.py`: size-bounded, versioned Native Messaging
  framing with sanitized errors.
- Only `get_status` is implemented so far.
- `extension/firefox/`: minimal Firefox extension shell and adaptive glyph.
- Permissions are currently only `activeTab` and `nativeMessaging`.
- The **Harvest this** button is deliberately disabled until its backend is
  safely connected.
- `scripts/harvester-native-host` and a native manifest template exist.
- All 44 tests passed after the complete rename.

Machine setup completed:

- Firefox's per-user Native Messaging manifest is registered as
  `com.harvester.native.json`.
- The installed launcher lives under
  `~/Library/Application Support/harvester/harvester-native-host`.
- Firefox loaded the temporary extension and the owner confirmed the popup says
  **Local companion ready** after the rename.
- Because the repository folder was renamed after loading the temporary
  extension, Firefox may need the extension removed and reloaded from
  `/Users/scott/Documents/harvester/extension/firefox/manifest.json`.

## Firefox harvest milestone completed

The next vertical slice was completed and manually accepted on 2026-08-30:

- The popup accepts only canonical Instagram post/reel URLs and enables
  **Harvest this** only when local settings are valid.
- Native-local settings store only the archive root and explicit Firefox profile
  in a user-only file; cookies remain browser-owned.
- A persistent background script owns active harvests, so closing the popup no
  longer interrupts them. Safe status survives popup closure and Firefox restart.
- The popup can open the configured output folder.
- One-off extension harvests create bundles without ledger entries. The lifecycle
  ledger is reserved for archival discovery and batch workflows.
- Firefox successfully harvested `Da8NsGRq7i0` and idempotently refreshed the
  existing `DcSvEX4IWu7` bundle. The owner confirmed the popup progressed from
  **Harvesting** to **Harvest complete** after being closed and reopened.
- The full suite passes 61 tests.

## Unsupported-site picker milestone completed

Manually accepted in Firefox on 2026-08-30 using MDN's iframe-based flower-video
demo:

- **Select visible media** activates only after an explicit user gesture.
- The picker follows the pointer into accessible frames, outlines only the hovered
  `<video>` or `<audio>`, and shows an explicit **Harvest media** control.
- Selection reads only `currentSrc`, `src`, and direct child `<source>` URLs.
- The bounded native path rejects private/local destinations, validates redirects,
  enforces a 500 MB streamed-byte ceiling, and requires a probed duration no longer
  than 10 minutes before archival.
- The accepted proof produced `flower_ec751467597feb26` with a preserved WebM,
  playable WebM, 48 kHz/24-bit stereo WAV, and matching sizes/hashes.
- Closing the popup does not interrupt work. Picker state cancels on timeout, Escape,
  tab navigation/closure, or extension reload and cannot remain falsely ready.
- Permissions remain only `activeTab`, `nativeMessaging`, and local `storage`.
- Archive.org exposed a player overlay/clipping edge case: cursor-local
  `elementsFromPoint` selection now finds only media under the user's pointer,
  and a pointer-transparent fixed border renders inside the media rectangle.
  The owner manually confirmed the button, border, and Escape cleanup work.

The current Saved index and ledger contain 454 items. Three oldest-first batches
of ten have completed; the third completed 10/10 on 2026-08-30. The ledger then
contained 25 complete items, six retired-deleted items, one deferred image-only
carousel, and 422 discovered items.

## Next implementation direction

Expose **Archival Harvest** as a distinct user-facing mode. Its Instagram section
should show Saved queue counts and last scan, offer **Scan saved posts** using the
existing five-consecutive-known boundary, and offer **Harvest next 10** using the
existing oldest-first ledger and pacing. One-off harvests must remain ledger-free.

The bounded single-video YouTube adapter was manually accepted in Firefox on
2026-08-30 using public-domain U.S. Government film `URwmZq70_DU`. It produced
a preserved 17,694,619-byte WebM, an identical playable WebM derivative, and a
48 kHz/24-bit stereo WAV; all recorded sizes and hashes matched. It accepts only
canonical `/watch?v=` URLs and structurally rejects playlists, channels, searches,
and bulk enumeration. Current YouTube extraction requires the Homebrew yt-dlp/Deno
stack, and both whole-request and fragment retries are disabled.

The bounded single-post Reddit adapter was manually accepted in Firefox against
post `1uh1oty`. It produced a preserved 24,604,629-byte MP4, an identical playable
MP4 derivative, and a 48 kHz/24-bit stereo WAV with matching recorded sizes and
hashes and no ledger entry.

Audio output is now governed by one global Settings preset for future bundles:
48 kHz/24-bit WAV (default), 44.1 kHz/16-bit WAV, 48 kHz/24-bit FLAC, 320 kbps
MP3, or 192 kbps MP3. There is deliberately no per-harvest choice, video
transcoding, or retroactive batch conversion. Originals remain byte-preserved,
and derivative metadata records the preset.
The Settings page uses a native macOS folder picker for output selection and
auto-detects Firefox's declared default profile; manual profile editing remains
available under an Advanced disclosure. The owner manually accepted the complete
Settings workflow in Firefox. Packaging, signing, and distribution
remain paused until the project owner explicitly resumes them.

The separate Instagram **Archival Harvest** screen was manually accepted in
Firefox. Its first UI scan found two new saves after scanning seven posts and
stopped at the five-known boundary, bringing the index and ledger to 456. Its
first UI-driven oldest-first batch completed post `DbL0aWgIApV`, bringing the
ledger to 423 waiting, 26 complete, one deferred, and six retired. The new bundle
passed source identity, hash, media, and configured `wav_48k_24` derivative checks. It
offers an explicit five-known-boundary scan and oldest-first batches with size
1–25, randomized 10–300 second delay bounds, sequential downloads, no retries,
authentication/rate-limit stops, live batch progress, and the approved account-risk
warning. One-time scheduling remains deferred until this manual workflow is proven.
The full automated suite currently passes 86 tests.

The single-file **Harvest local file** workflow was manually accepted in Firefox
using the Archive.org download of *Duck and Cover*. The Finder-selected source,
preserved original, and playable MP4 derivative have the same SHA-256 digest. Its
configured audio derivative is 48 kHz/24-bit stereo WAV, and no lifecycle-ledger
entry was created. A verification pass caught and fixed ffprobe's absolute
`filename` field before acceptance; probe metadata now strips filesystem paths,
and the accepted bundle was sanitized. Local harvesting remains deliberately
one-file-at-a-time with no folders, watchers, batch conversion, or retained source
directory.

## Firefox V1 release candidate

On 2026-09-02 the package, native companion, and extension advanced to version
1.0.0 with stable Firefox ID `@harvester-sxrvys`. Mozilla `web-ext` validation
passes with zero errors, notices, or warnings; the manifest explicitly declares
no data collection or transmission. The supported release boundary is Firefox
desktop 142 or newer plus the macOS companion.

Reproducible builders create separate extension and companion archives under the
Git-ignored `dist/` directory. The companion installer was proven first in an
isolated home and then installed live under `~/Library/Application Support/harvester`.
It owns a versioned virtual environment and private state directory rather than
depending on this repository. The existing 462-item Saved index and ledger were
migrated byte-for-byte, and a framed live status request returned version 1.0.0,
configured and ready. The native manifest permits only the stable extension ID.

Mozilla approved the unlisted 1.0.0 submission. The owner removed only the
temporary debugging instance, installed the signed XPI permanently, and confirmed
the native companion, Settings, and plain-text diagnostics. Signed-V1 smoke tests
then passed for a one-off Instagram Reel, MDN visible-media selection, an
oldest-first archival batch (10 complete, zero skipped), and an idempotent local
file harvest. The release still needs final GitHub documentation, license and
repository-visibility decisions, and publication of the signed XPI plus companion
package.

## V1.0.1 roadmap

- Add privacy-bounded Firefox-side failure logging for picker injection,
  selection timeout, missing ordinary media URL, native-message dispatch, and
  other failures that occur before the companion can record them. Automatic
  diagnostics must not retain page URLs or media URLs.
- Add a user-initiated **Prepare bug report** workflow that previews everything
  being copied. It may optionally include a sanitized page URL only with explicit
  consent. Sanitization uses the URL parser, permits only HTTP(S), and removes
  credentials, query parameters, and fragments. Never include the selected media
  URL, cookies, headers, browser history, filesystem paths, or raw downloader
  output. Offer **Copy report** for everyone and **Open GitHub issue** for users
  with a GitHub account; state plainly that GitHub requires an account and never
  submit automatically. Do not publish or embed a support email yet. The owner
  may later designate a shared project address for Harvester and future creative
  software projects.
- Add a recent-batch review section to **Archival Harvest**. After a batch, show
  only that batch's attempted items with a useful title/thumbnail, outcome, and
  an **Open** action. Permit deliberate deletion of an individual completed
  bundle through the existing ledger-aware retirement workflow; require clear
  confirmation and never provide bulk deletion. The view is a batch receipt, not
  a general media-library browser.
- Improve new archival bundle directory names for Finder legibility using
  `<zero-padded archival order>__<short human-readable title>`, for example
  `0044__palestinians-displaced-1967`. The normalized title has a predictable
  maximum length. Do not include the Instagram shortcode in the directory or
  derivative filenames; provenance and attribution already retain it in
  `metadata.json`, the ledger, and batch receipts. Archival order supplies stable
  sorting and uniqueness. Idempotent lookup must use ledger/source identity rather
  than reconstructing a path from its display name. Do not silently rename
  existing bundle directories: any migration must update ledger and batch
  references transactionally, or existing archives remain under their original
  names.

V1.0.1 implementation and live acceptance completed on 2026-09-02. The existing
42 ledger-backed archival folders were transactionally migrated; a repeated dry
run reports zero changes and every ledger/batch reference resolves. New archival
batches natively use the compact ordered convention. The latest-batch viewer
returned ten bounded local thumbnails and the owner confirmed Rename, Reveal in
Finder, and confirmed Move to Trash; the deleted bundle appeared in macOS Trash
and its ledger state changed to `retired-deleted`. Firefox-side protected-page
injection failure produced a privacy-safe local event. The owner confirmed report
preview, opt-in sanitized page address, plain-text copy, and a correctly prefilled
GitHub issue without submission. The suite passes 93 tests and Mozilla lint reports
zero errors, notices, or warnings. Remaining work is final artifact rebuild,
Mozilla 1.0.1 signing, signed-XPI smoke test, license/repository visibility choice,
and GitHub release publication.

## V1.0.2 first-release candidate

V1.0.2 adds the missing first-run archive workflow. Archival Harvest now starts
with an empty user-managed list and accepts multiple explicitly supplied Instagram
Saved-page or collection URLs. Archives can be added from a pasted URL or an open
Instagram page, named, renamed, edited, reopened, selected independently, and
removed without deleting harvested media. Each has an isolated queue and history;
the output archive is shared, so metadata identity deduplicates posts appearing in
more than one collection. Named collections whose thumbnails do not expose normal
links use a bounded, visible-tile resolver only during the explicit scan.

The owner completed a clean pre-release archival-state reset and tested the normal
new-user flow. The main Saved page indexed 468 items; a second two-item collection
indexed independently. Scanning one collection did not scan the other, successful
scan-created tabs closed automatically, and progress correctly reported two of two
identified tiles. A one-item batch harvested a five-video carousel as one bundle
with five originals, five video derivatives, and five audio derivatives. The same
post occurs in both archives and is represented by one on-disk bundle while both
ledgers recognize it as complete. The current archive audit reports 7 bundles,
33 files, zero errors, and zero warnings.

The 1.0.2 release still requires the final automated checks, artifact inspection,
Mozilla signing, signed-XPI smoke test, and GitHub release publication. Repository
visibility and licensing remain separate owner decisions.

## Working preferences

- Keep communication conversational and concrete.
- Push only one or two coherent batches per day, not every small change.
- Preserve unrelated user files and local archive/state.
- Do not depend on or modify the original RADIO HARVEST repository.
- The old simulated-radio/demodulation concept is a distant optional idea, not
  V0 scope.
