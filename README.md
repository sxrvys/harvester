<p align="center">
  <img src="app/Assets/HarvesterIcon.png" width="160" alt="Harvester icon">
</p>

# Harvester

**Find it. Queue it. Keep going.**

Harvester finds, downloads, prepares, and organizes footage for video artists and
VJs. Build a reusable library, find the moments you want, and drag ordinary video
files into your favorite editor or performance software. No companion editor or
Harvester account is required.

Built by **Scott and Splice**. Splice is the nickname for the Codex collaborator
on Harvester. One human, one coding agent, a lot of strange footage.

## Install Harvester on your Mac

**[Download Harvester from GitHub Releases](https://github.com/sxrvys/harvester/releases/latest)**

The current app release is **2.4.4**. Choose
**Harvester-2.4.4-macos-arm64.dmg** under **Assets**, not the Source code ZIP or
tar.gz. You do not need a GitHub account, a compiler, or a separate editor.

1. Open the downloaded `.dmg` and drag **Harvester.app** into **Applications**.
2. Open Harvester from Applications. This beta is not Apple-notarized; if macOS
   blocks it, review **System Settings → Privacy & Security** for the option to
   approve opening it. Only approve a copy you trust. Managed Macs may require
   help from an administrator.
3. Harvester includes its required tools. No Homebrew, Terminal commands, or
   separate dependency installation is needed.
4. Choose **Keep my library on this Mac** to use `Movies/Harvester`, or
   **Choose another location…** for an external drive or an existing library.
   Allow drive access if macOS asks.

**Compatibility:** 2.4.4 requires an **Apple silicon Mac (M-series)** and macOS 13
or later. Python, FFmpeg/FFprobe, yt-dlp, and Deno are included privately inside
the app. This build does not use or install Homebrew tools. Settings checks the
included tools; if one fails, retry or download a fresh app copy.

Intel users can use the [previous 2.4.1 release](https://github.com/sxrvys/harvester/releases/tag/v2.4.1),
which needs separate tools. The bundled 2.4.4 release is Apple silicon only.

The app is locally ad-hoc signed, **not Developer ID signed or notarized**. There
is no Windows release yet. The Firefox extension is optional and is not needed
for the workflow below.

## Your first harvest

1. Open **Harvest queue** and paste a video link under **Links to harvest**.
   For a batch, put one link on each line. Optionally add a readable name:
   `https://example.com/video:My clip`.
2. **Smaller files** is the default for new app submissions. Open
   **Options for new submissions** to choose **Smoother editing · larger files**
   if easier scrubbing and reversing matters more than storage space.
   Set a start/end range if you want only part of the video.
3. Leave **Keep sound** on to retain one audio track when available, or turn it
   off for silent footage.
4. Click **Add & start queue**. You can keep adding links while it runs.
5. Completed videos appear in **Video library**. Click a thumbnail to preview
   one, or drag it into your editor.

**Add to queue** saves jobs without starting an idle queue. **Start queue** runs
waiting jobs. If the queue is already running, it picks up new submissions.

Trimming still downloads the full source. Settings default to a 60-minute source
limit and a 500 MB download limit, adjustable up to six hours and 5 GB per source.
Existing queued jobs retain their format. Neither preset automatically reduces
resolution; file size depends on the footage. The included signed Firefox 2.2
add-on still defaults to all-keyframe video: choose **Smaller H.264** in its popup
for compact files. The updated app default does not override explicit add-on choices.
Prepared video, especially the
smoother-editing format, can be much larger than the download.

## Find footage without a link

Open **Discover** to search Prelinger, the wider Internet Archive video collection,
or NASA video. Preview results, select the ones you want, and add them to the
queue. Archive searches target video records rather than text, photos, or audio.
Harvester downloads only the items you choose.

## Add videos you already have

In **Video library**, click **Add media…**, then **Choose videos…**.

| Choice | What it does |
| --- | --- |
| **Copy into my library → Smaller files** | Prepares compact H.264 MP4 video for everyday playback. |
| **Copy into my library → Smoother editing** | Prepares larger H.264 files that are easier to scrub and reverse. |
| **Copy into my library → Keep original format** | Copies the file unchanged; does not repair an unsupported format. |
| **Use files where they are** | Adds a reference without copying or converting. Keep those files in place. |

Use **Queue import** for copies/conversions or **Add to library** for references.
Exact copies already in the library are identified so you can avoid importing
them again. Your selected local originals are not deleted.

## Browse and organize your library

- **By source** groups prepared versions and clips beneath their original source.
  Expand a source to see its derivatives; use **All clips** for a flat view.
- Search names, tags, notes, or filenames. **Role** stays visible; **Filters**
  exposes additional options. Searching can reveal a matching derivative even
  when its source family is collapsed.
- Click a thumbnail or **Preview & notes** to watch footage and save organization
  details. **Contact sheet** provides evenly spaced frames for navigation—not
  automatic detection of the best action shots. Save moments and in/out ranges
  while reviewing.
- Use tags and performance sets to collect material for a project. Roles describe
  how you intend to use a clip: **Masks**, **Background**, **Middle**, and **Top**.
- **Session Crate** gives you four role lanes for assembling a set and dragging
  files into other software. Clearing a setlist does not delete the media.
- **Open library in Finder** opens the readable browsing view. The library path
  is also shown in the app, so you always know where the collection lives.
- **Library Health** helps inspect library issues and cleanup suggestions.
  **Manage library → Repair file references…** helps reconnect moved files.
- Select one or several clips and use **Move selected to Trash…** to remove them.
  Review the confirmation before proceeding. Trash is recoverable until emptied;
  moving files there does not free disk space by itself.

Keep the library's media and catalog folders together. Acquired sources live in
`Sources/`; prepared versions live in `Derivatives/`. Generated Finder browsing
links point to stored media rather than making more video copies. Organize in the
app instead of renaming those generated links.

For an enrolled external-drive library, new harvests can be held temporarily in
`~/Movies/Harvester Pending Library` while that drive is unavailable and transferred
when it returns. Existing external-drive videos are **not** automatically copied
onto your Mac for offline playback. Verified local holding copies remain until
explicit cleanup.

## Update Harvester

In version 2.4.1 or later:

1. Open **Harvester → Settings → Check for Updates**.
2. If a newer compatible release exists, choose **Download Update…** and a place
   to save it. Harvester verifies the download's SHA-256 checksum.
3. Finish active harvests, save preview notes, and quit Harvester.
4. Open the downloaded installer and replace the old app **in the same folder**.
   **Show Current App** identifies that folder before you quit.

For an older app without this setting, download the latest DMG from the release
link above and follow the same replacement steps. Media, queue state, and settings
live outside the app bundle. Keep a copy of the previous app if you want a rollback.

Checks happen only when requested. There are no background checks, automatic
updates, or silent app replacements. A checksum verifies download integrity; it
is not an Apple publisher signature.

## Supported sources and sign-in

YouTube and Reddit have dedicated adapters. NASA uses its public media API.
Other public media pages and direct video links are attempted through yt-dlp.
Site support varies: playlists, live streams, DRM, login requirements, expired
links, or unusual players may prevent a download. Audio-only imports are not
supported by the native video workflow.

For YouTube, **Settings → Use Firefox login for YouTube** can use the Firefox
profile where you are already signed in. This is off by default, applies only to
YouTube, and does not save a cookie export. Choose the matching Firefox profile
and retry the failed item after signing in. Login does not guarantee a download;
authentication challenges, permissions, and rate limits are reported rather than
retried indefinitely.

### Optional Firefox extension

The **Mozilla-signed Firefox 2.2.0 extension is included** with the app and in
the disk image's Firefox folder. Firefox itself must already be installed;
version 142 or later is required.

1. Install Harvester in Applications and open that copy.
2. In Harvester Settings click **Connect Firefox…** and approve the local bridge
   registration. Any previous registration is backed up.
3. Click **Show Firefox Add-on**. In Firefox open `about:addons`, click the gear,
   choose **Install Add-on From File…**, and select the included `.xpi`.
4. Approve Firefox's prompt. Restart Firefox if it does not connect immediately.

Reconnect from Settings if you move the app later. No Terminal command or separate
companion installer is needed for this bridge. Pasting links into Harvester still
works without Firefox. The signed add-on is preserved unchanged; its older browser
capture/Instagram archival workflows are separate from the native video queue.

## If something does not work

| Problem | Try this |
| --- | --- |
| Bundled tool check fails | In Settings use **Check Again**. If it still fails, download a fresh 2.4.4 app and report the message; no separate tool installer is needed. |
| Library drive missing or inaccessible | Reconnect it, allow macOS drive access if requested, then click **Refresh**. Check the displayed library path. |
| Cannot add media or start harvesting | Choose a library folder first. |
| Download exceeds limits | Review the full source duration/size and the limits in Settings, even if you requested a short range. |
| Source requests authentication or is rate-limited | Follow the job's message. For YouTube, check the selected Firefox profile. Some sites cannot be harvested. |
| A local file does not play well in another app | Use **Add media…** or **Prepare versions…** to prepare a compatible version rather than keeping its original format. |
| Update check fails | Try again later, or use [GitHub Releases](https://github.com/sxrvys/harvester/releases/latest) directly. |

## Privacy and ownership

No Harvester account, hosted library, analytics, telemetry, or automatic uploads.
Media and organization stay on your drives. Downloads contact the sources you
choose; an explicit
update check contacts GitHub without sending library data.

New URL harvests produce H.264 MP4 video with sound when available. Downloaded
source files are temporary and discarded after processing; the prepared video
is kept. Local files you select for import are left untouched. Existing archives
are not silently migrated or deleted. Harvest only material you are authorized
to preserve.

## For developers

Developer builds use local Python 3.11+, FFmpeg/FFprobe, yt-dlp, and Deno.
Release builds require `HARVESTER_BUNDLE_RUNTIME=1`; the release packager checks
the included tools and rejects the obsolete Terminal installer.

The Mac UI uses SwiftUI; its backend uses Python. The extension uses plain
HTML/CSS/JavaScript. Node is not required by the installed app.

**The 2.4.4 binary was built from a working-tree snapshot that is newer than the
public source checkout.** GitHub's automatic Source code archives do not reproduce
this release. Use the DMG to run the current app. The release includes
`BUILD-MANIFEST.json` with build provenance and file fingerprints, `SHA256SUMS.txt`,
and `INSTALL.txt`.

The release also provides corresponding FFmpeg/x264 source and build instructions
in `Harvester-2.4.4-third-party-sources.tar.gz`. These separate tools are GPLv2 or
later; their licenses are not replaced by Harvester’s own licensing. Python, Deno,
yt-dlp, and package notices are retained inside the app’s runtime folder. See
[third-party release materials](https://github.com/sxrvys/harvester/releases/tag/v2.4.4).

The existing [development notes](docs/v2-development.md) and
[2.2 notes](docs/v2-2.md) describe earlier source workflows; they are not the
installation instructions for this binary. Licensing is unchanged; see
[LICENSING.md](LICENSING.md).
