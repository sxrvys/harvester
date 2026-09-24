<p align="center">
  <img src="app/Assets/HarvesterIcon.png" width="160" alt="Harvester: a scythe behind a CRT television">
</p>

# Harvester 2.2

**Find it. Queue it. Keep going.**

Harvester collects source material for found sound, video collage, and other art
projects. Paste a link or a batch of links into the Mac app, or send the page
you're browsing from Firefox. Each completed video harvest gives you a silent
H.264 MP4 and separate audio in a normally named folder. Downloaded originals
are discarded; local input files are left untouched.

Built by **Scott and Splice**. Splice is the nickname for the Codex collaborator
on Harvester. One human, one coding agent, a lot of strange footage.

## What you can do

- Submit multiple links or local files and keep adding while harvesting runs.
- Name links in one box: `https://example.com/video:My clip name` (one per line).
- Choose start/end times, all-keyframe H.264 for seeking or smaller H.264, and
  separate 24-bit WAV or lossless FLAC audio.
- Preview completed videos, reveal their bundles, and retry failed jobs.
- Select multiple completed videos and send them to Chromatron in one action.
  Select unsent helps avoid repeat handoffs; Sent labels persist across launches.
- Adjust source limits in **Harvester → Settings** (`⌘,`). Defaults are 60 minutes
  and 500 MB; ceilings are six hours and 5 GB per source. Changes apply when the
  queue next starts. Full-source limits still apply when trimming, and exported
  video/audio can be much larger than the download.

The queue runs up to three acquisition workers, one per source at a time, with
conversion serialized. It persists jobs locally and keeps provenance in private
queue records rather than adding metadata sidecars to v2 media folders.

## Harvester + Chromatron

Harvester gathers and names material. **Chromatron** prepares clips for VDMX,
with its own queue so incoming videos need not replace the clip being worked on.
In Harvester, choose your Chromatron application under **Options for new
submissions → Choose Chromatron…**, then use the per-video button or select a
batch and click **Send selected to Chromatron**.

Handoffs use local MP4 files through macOS, with no upload. A Sent label means
macOS accepted the handoff; it does not mean Chromatron has finished processing.
Chromatron is optional—Harvester's output works as ordinary media files.
Its repository link will be added when the companion project is published.

## Source support and Firefox

YouTube and Reddit have dedicated adapters. Individual public media pages and
direct media file links are attempted through yt-dlp's extractors. Support varies
by site; playlists, live streams, DRM, login requirements, temporary URLs, or
unusual players may prevent acquisition. General page harvesting does not borrow
Firefox cookies. A submitted link authorizes that item, not an account crawl.

The **signed Firefox 2.2 extension** offers a name, clip options, **Harvest now**,
**Add to queue**, and **Open Harvester** for page harvests. These feed the same
queue as the Dock app. The app can also run independently of Firefox.

**Select visible media**, browser local-file selection, and Instagram/Archival
Harvest still use the older companion workflow and its Firefox Settings. The
visible-media picker can transfer readable blobs, but a `blob:` address is not
always a complete downloadable file. Bringing this picker into the native queue
is future work. Keep the source tab open for browser capture workflows.

## Install from this checkout (macOS)

The Firefox extension is Mozilla-signed. The native app is locally ad-hoc signed,
not Apple Developer ID signed or notarized. Building it requires Apple's command
line developer tools with Swift and the macOS SDK. Runtime tools are installed
separately:

```sh
brew install python ffmpeg yt-dlp deno
```

From the project directory:

```sh
scripts/install-macos-companion
scripts/build-v2-app --release
scripts/install-v2-app
scripts/install-firefox-v2-bridge
```

Stop the queue and quit older Harvester app versions before installing. The
installer preserves an app backup and existing queue. Launch
`~/Applications/Harvester.app`; use **Choose folder…** to select your media output.
The native backend is bundled in the app. The bridge connects Firefox to that
backend while retaining the existing native messaging registration.

Download the [Mozilla-signed Firefox 2.2.0 XPI](releases/v2.2.0/harvester-firefox-2.2.0-signed.xpi)
(use GitHub's **Download raw file**). In Firefox, open `about:addons`, click the gear
menu, choose **Install Add-on From File…**, and select the XPI. Remove any temporary
Harvester development copy from `about:debugging` first. Firefox 142 or newer is
required. The signed installation survives browser restarts.

## Daily workflow

1. Paste one or more links in the app, optionally followed by `:Name`, or select
   local files. Firefox can send the current media page instead.
2. Set optional clip times and export choices before submitting.
3. **Harvest** submits and starts work. **Add to queue** only queues while idle;
   an already running queue picks up new items automatically.
4. Completed bundles contain silent video and separate audio when those streams
   exist. Audio-only input produces audio only.
5. Select completed videos and send them to Chromatron, or open the files in
   whatever creative software you use.

## Privacy and older workflows

No Harvester account, hosted backend, analytics, telemetry, or automatic uploads.
Downloads contact the source sites you choose. Queue state, provenance, settings,
and media stay on your Mac. Harvest only material you are authorized to preserve.

Legacy Instagram Saved archival workflows retain their paced collection queues,
review tools, and metadata conventions; their video may live in the shared
archive `video/` folder. They are separate from v2's named, self-contained output
bundles. Existing archives are not silently migrated or deleted.

See [2.2 notes](docs/v2-2.md), [development and architecture](docs/v2-development.md),
and the [project constitution](PROJECT_CONSTITUTION.md). Licensing is unchanged;
see [LICENSING.md](LICENSING.md).

## Development checks

Python 3.11+, FFmpeg/FFprobe, and Node (for development checks only) are required:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
node tests/test_popup.cjs
npx --yes web-ext lint --source-dir extension/firefox
scripts/build-firefox-extension
scripts/build-v2-app --release
```

The extension uses plain HTML/CSS/JavaScript; the native app is SwiftUI and the
backend is Python. No Node runtime is required by the installed product.
Generated builds, authentication material, queue state, and harvested media are
excluded from Git. The signed 2.2 XPI is intentionally preserved with its checksum
under [releases/v2.2.0](releases/v2.2.0).
