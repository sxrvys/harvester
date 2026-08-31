# Local file harvest acceptance

Status: manually accepted on 2026-08-30. Packaging, signing, and distribution remain paused.

## Contract

After one explicit **Harvest local file** action, the native companion opens a
Finder file picker and accepts exactly one user-selected local media file.

- The extension never receives the selected filesystem path.
- Only one regular file is accepted; folders and batch selection are unavailable.
- The file must contain a probed audio or video stream, remain within the active
  duration and source-size limits, and be readable by the local media toolchain.
- Identity derives from the complete source-file SHA-256 digest.
- The original is preserved byte-for-byte and one globally configured audio
  derivative is created when the source contains audio.
- Metadata may retain the original basename, size, content hash, media facts,
  and import time. It never retains the original directory or absolute path.
- No lifecycle-ledger entry is created, and existing bundles are not converted.
- Cancellation is a normal, clean outcome with no bundle or failure record.

The feature does not accept folders, watch directories, multiple files, arbitrary
FFmpeg arguments, video-transcoding choices, or retroactive/batch conversion.

## Manual proof target

The user selected the Archive.org download of *Duck and Cover* through Finder and
the popup reported **Local file harvest complete**. The Downloads source, preserved
original, and playable MP4 derivative share the exact SHA-256 digest
`4ba23cfc250d9471a7f73aef6000313977e4a16df6ecff4d2eca46ed61f710ed`.
The configured derivative is a 48 kHz, 24-bit stereo PCM WAV. Metadata retains the
source basename but no absolute filesystem path, and the local import created no
lifecycle-ledger entry.
