# Firefox V1 release checklist

Harvester V1 is a Firefox extension plus a macOS Native Messaging companion.
The extension alone cannot acquire or process local media.

## Release boundary

- Firefox desktop 109 or newer.
- macOS companion installation.
- Python 3.11 or newer.
- FFmpeg/FFprobe, yt-dlp, and Deno available on the companion `PATH`.
- No Chrome package in V1.
- No telemetry, hosted service, or Harvester account.
- Firefox manifest declares Mozilla's required `none` data-collection permission.
- Stable Firefox extension ID: `@harvester-sxrvys`; the native manifest must
  allow this exact ID.

## Local release checks

1. Confirm the package, extension, and protocol versions are intentional.
2. Run all Python tests.
3. Parse every extension JavaScript file.
4. Run Mozilla's current `web-ext lint` against `extension/firefox`.
5. Build the unsigned review archive with `scripts/build-firefox-extension` and
   the standalone native package with `scripts/build-macos-companion`.
6. Inspect both file lists and verify they contain only their intended payloads.
7. Install the companion from its extracted package with
   `scripts/install-macos-companion`.
8. Verify the installed native manifest allows exactly the release extension ID.
9. Smoke-test status, settings, one supported URL, visible-media selection,
   local-file selection, output-folder opening, archival status, and failure-log
   opening from the permanent installation. Trigger one safe failure and confirm
   Settings opens its sanitized plain-text diagnostic record.

## Signing boundary

Normal Firefox releases must be signed by Mozilla. For private self-distribution,
submit the extension as **unlisted** and retain the returned signed XPI. Signing
requires the project owner's Mozilla Add-ons account and credentials; credentials
must be supplied directly to the signing tool through environment variables and
must never be written to this repository, settings, logs, or chat.

Do not publish a listed AMO release, make this repository public, or choose a
public-source license without the project owner's separate approval.
