<p align="center">
  <img src="assets/brand/harvester-glyph.svg" width="120" alt="Harvester logo">
</p>

# Harvester

Harvester is a local-first Firefox extension for artists, musicians, editors,
researchers, and people who collect source material online for later. It saves the
original media, makes a practical audio derivative, and records enough provenance
to remember where it came from—all in ordinary files on your Mac.

It works with individual Instagram, YouTube, and Reddit posts, visible video or
audio on other sites, and one local file at a time. It can also work through your
Instagram Saved collection in small, deliberately paced batches, starting with the
oldest things you saved.

Harvester is intentionally focused. It is not a general scraper, feed crawler,
playlist downloader, media library, or batch converter. It
only acts when you ask it to harvest something.

## What it can do

- Harvest individual Instagram posts and Reels, including every media item in a
  carousel.
- Natively harvest individual YouTube videos and Reddit media posts.
- Let you point at one visible video or audio player on another website and make a
  bounded attempt to preserve it.
- Turn one local audio or video file into a tidy, self-contained Harvester bundle.
- Maintain multiple Instagram Saved archives or collections, each with its own
  queue and progress, and work through them oldest-first in small paced batches.
- Recognize posts shared between collections and keep one copy instead of
  downloading duplicates.
- Create a practical audio derivative automatically. Choose 24-bit or 16-bit WAV,
  FLAC, or 320/192 kbps MP3 in Settings.
- Keep the original media, useful derivatives, source attribution, and technical
  metadata together in an ordinary folder you control.
- Review the latest archival batch, rename its folders, reveal an item in Finder,
  or move an unwanted item safely to Trash.
- Prepare a readable, privacy-conscious bug report when something fails—without
  silently sending anything anywhere.

Harvester does the clerical work of helping you archive a sound or video while the discovery is still fresh. It preserves the source, makes an immediately useful audio file, and keeps provenance beside the
media. Carousels stay together as one post; long-lived Saved collections can be
worked through gradually; and everything lands in normal files that can go straight
into a sampler, DAW, NLE, VJ setup, collage folder, or research notebook. Harvester
does not try to become your creative environment. It brings interesting material to
the environment you already use.

## Install on macOS

Harvester has two parts: the Firefox extension you click and a small local companion
that handles downloads and media processing.

1. Install [Homebrew](https://brew.sh/) if you do not already have it.
2. Open Terminal and install Harvester's media tools:

   ```sh
   brew install python ffmpeg yt-dlp deno
   ```

3. Download and extract `harvester-macos-companion-1.0.2.tar.gz`. In Terminal,
   enter the extracted folder and run:

   ```sh
   scripts/install-macos-companion
   ```

4. Download the Mozilla-signed `.xpi`.
5. In Firefox, open `about:addons`, click the gear, choose **Install Add-on From
   File…**, and select the `.xpi`.
6. Open Harvester. If it says **Local companion ready**, you're ready to go.

V1.0.2 supports Firefox desktop 142 or newer on macOS.

## Getting started

Open **Settings** first. Choose an output folder with the Finder button, choose the
audio format you normally want, and leave the Firefox profile path alone unless
you deliberately use a different Firefox profile. Once the popup says **Local
companion ready**, pick the workflow that matches what you found:

- **Instagram, YouTube, or Reddit:** Open one post or video and click **Harvest
  this**.
- **Another website:** Click **Select visible media**, point at one visible video
  or audio player, then click **Harvest media**.
- **A file on your Mac:** Click **Harvest local file** and choose one audio or video
  file in Finder.
- **Your Instagram Saved collections:** Open **Archival Harvest**, click **+**, and
  paste the URL of an Instagram Saved page or collection—or use one already open
  in Firefox. Give it a name, scan it, and run a small oldest-first batch. Add as
  many collections as you actually use; overlapping posts are downloaded only
  once. When a batch finishes, you can review, rename, reveal, or move individual
  results to Trash.
- **Output and audio format:** Open **Settings** to choose where files go and which
  audio preset Harvester should create.

Keep Firefox open while a harvest is running. Please only harvest material you are
legally allowed to preserve and use.

## If something does not work

- Confirm the popup says **Local companion ready**. If it does not, reinstall the
  companion and restart Firefox.
- Keep the source tab open until Harvester reports completion.
- A visible-media harvest can fail cleanly when a player uses `blob:`/MSE, DRM, an
  inaccessible frame, an expiring address, or authentication the companion cannot
  use. Harvester does not inspect network traffic or capture private headers to get
  around those boundaries.
- In **Settings**, open the failure log or choose **Prepare bug report**. You can
  inspect and copy the safe diagnostic text before deciding whether to open a
  GitHub issue.

## What you get

Each harvest becomes a self-contained folder with:

- the preserved original;
- a playable video copy when applicable;
- one audio derivative in your chosen WAV, FLAC, or MP3 preset; and
- `metadata.json`, containing provenance and useful media facts.

Instagram archival folders have compact, naturally sorted names such as
`0044__people-dancing`. The Instagram identifier still lives in the
metadata and private ledger, where it is useful, instead of cluttering Finder.

## Privacy

No Harvester account. No cloud service. No analytics, advertising, telemetry, or
automatic bug reports. Your settings, archive state, diagnostics, and harvested
media stay on your Mac. Firefox remains in charge of Firefox authentication.

If something goes wrong, **Settings → Prepare bug report** shows you exactly what
would be shared. Page addresses are excluded unless you explicitly add a sanitized
version. Reports never include cookies, credentials, query parameters, media URLs,
headers, filesystem paths, or raw downloader output. You decide whether to copy the
report or open a GitHub issue, and nothing is submitted for you.

## A note about Archival Harvest

Archival Harvest exists for one specific job: slowly working through your own
Instagram Saved pages and collections without losing your place. Each configured
collection has its own queue and progress, while shared posts use one copy of the
media on disk.

Scanning starts with the newest saved posts and stops after five consecutive posts
already known to the private ledger. Harvesting then works oldest-first, one item at
a time. You choose a batch size from 1–25 and a randomized delay from 10–300 seconds.
Ordinary failures are not retried during the same batch, and authentication or
rate-limit trouble stops the run.

Automated access can trigger Instagram restrictions. Larger batches and shorter
delays increase that risk, so Harvester keeps hard minimums and makes you start each
batch yourself. You are responsible for deciding whether and how to proceed.

## For contributors and curious programmers

The Firefox extension is plain HTML, CSS, and JavaScript under
[`extension/firefox`](extension/firefox). It talks through Firefox Native Messaging
to the Python companion under [`src/harvester`](src/harvester). There is no bundler,
transpiler, minifier, hosted backend, or Node runtime in the product.

Harvester's boundaries are deliberate:

- one explicitly chosen item per ordinary harvest;
- no page-wide scraping or network-traffic inspection;
- no playlists, feeds, profiles, recommendations, or unrelated links;
- bounded downloads of no more than 10 minutes or 500 MB;
- no folders, watch directories, or multi-file local conversion; and
- no silent deletion—archival removal verifies identity, moves one bundle to macOS
  Trash, and marks it retired so it will not be downloaded again.

The implementation contracts and acceptance records are in [`docs`](docs),
including the [browser-extension specification](docs/browser-extension-spec.md),
[visible-media acceptance test](docs/unsupported-site-picker-acceptance.md), and
[archival acceptance test](docs/archival-harvest-acceptance.md).

### Run the checks

Harvester requires Python 3.11+ and FFmpeg/FFprobe on `PATH`.

```sh
python3 -m unittest discover -s tests -v
```

The release test suite and Mozilla's extension validator must pass before a package
is published.

### Build the two release packages

```sh
scripts/build-firefox-extension
scripts/build-macos-companion
```

The companion archive includes the installer and Python source, but no user
settings, authentication material, ledger, diagnostics, or harvested media. See
[`docs/release-checklist.md`](docs/release-checklist.md) for the complete release
procedure.

## Why Harvester exists

Interesting source material has a habit of disappearing—or becoming impossible to
find the moment inspiration strikes. Harvester is a small tool for catching those
fragments.

