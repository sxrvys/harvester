# Harvester 2 local installation and development

Harvester 2 is the native Mac app with a persistent queue. The installed Firefox
bridge sends supported YouTube/Reddit links to it; other extension workflows
remain on the legacy companion. See [the 2.1 update](v2-1.md) for newer controls.

## Daily-use installation

The local app is installed at `~/Applications/Harvester.app`. Its backend is
packaged inside the app, and its queue lives at
`~/Library/Application Support/harvester/queue-v2`. It still uses installed
Homebrew Python, FFmpeg, yt-dlp, and Deno; it is not a portable, notarized release.

Build with `scripts/build-v2-app --release`. Stop queues and quit both app versions
before running `scripts/install-v2-app`. On first installation, the installer
copies the development queue and receipts, preserving the old queue as a backup.
It leaves harvested media and the Firefox companion in place. Later installations
preserve the existing daily-use queue. Do not run the old development queue after
migration: the two queue journals are independent.

The September 23 local installation preserved all four completed jobs and the
selected output folder, `/Users/scott/Documents/harvester/Archive v2`.

## Open the app

From this checkout:

```sh
scripts/build-v2-app
```

Open `build/Harvester 2.app`. The app is locally signed for development and relies
on this checkout and the existing Python/FFmpeg/yt-dlp toolchain. It is not yet a
portable, notarized distribution. Do not move or remove the source checkout while
using the development app.

1. Choose an output folder, or use the separate `build/v2-output` default.
2. Paste one URL per line and click **Add to queue**. Give each line its own optional
   name using `URL:Name`, for example:

   ```text
   https://www.youtube.com/watch?v=NCxkLReX_YQ:Jim Jones Preaching In Los Angeles
   https://youtu.be/AAAAAAAAAAA:Empty shopping mall
   https://www.youtube.com/watch?v=BBBBBBBBBBB
   ```

   Plain links use the source title. Spaces around the naming colon are allowed;
   later colons belong to the name and are made filename-safe. Scheme (`https:`)
   and port colons are never naming separators. Encode colons inside URL query
   values as `%3A` to keep them part of the URL. Existing local file paths are
   preserved as-is. Duplicate links keep their existing job/name; use **Name…**
   to rename a queued job. Colliding output names receive numeric suffixes.
3. Click **Harvest** to submit the text in the box and start immediately. With an
   empty box, **Harvest** starts queued work. Use **Add to queue** to build a list
   first. Both actions remain available during active harvesting; the running
   queue automatically picks up new submissions as capacity becomes available.
4. Use **Open video** or **Show bundle** when a job completes.

**Add files…** accepts explicitly selected local files, without deleting the
inputs. URLs support single YouTube videos (including short links and Shorts),
Reddit posts, and Instagram posts. The native app deliberately does not access
an Instagram account yet; its account/profile setup is a subsequent milestone.
An Instagram job without setup fails visibly and pauses Instagram while other
sources continue. The CLI can accept an explicitly authorized Firefox profile.

## Firefox bridge

Build/install app 2.0.1, then run `scripts/install-firefox-v2-bridge`. The existing
signed Firefox extension can now send **Harvest this** YouTube/Reddit requests
through the native companion into the daily-use v2 queue. The companion saves
the job before opening the app; the app starts eligible queued work. An already
running queue picks up submissions automatically. Duplicates reuse the same job;
failed/interrupted jobs still need explicit Retry. No browser cookies are used.

The signed extension's popup still says “Harvest complete” on a successful
handoff; watch actual processing in the app. Updated extension source has accurate
handoff wording, but requires a new signed add-on for permanent installation.
Instagram, Saved batches, local-file selection, and generic selected media retain
the v1 companion workflow. A selected YouTube blob routed through its page URL
uses v2. General page URLs, playlists, feeds, and arbitrary MSE/blob inputs are
not supported by the v2 queue.

The installer preserves the previous launcher at
`~/Library/Application Support/harvester/harvester-native-host.before-v2`.
Restoring that file as `harvester-native-host` restores the previous routing.
Keep the installed app at `~/Applications/Harvester.app` while the bridge is enabled.

## Output contract

A completed named folder contains the media files only:

```text
Preacher gestures/
  Preacher gestures — video.mp4
  Preacher gestures — audio.wav
```

Video has no audio stream; audio has no video stream. Downloaded combined
originals are temporary. Silent videos produce no invented audio. Carousel media
uses numbered filenames. Job/source identity, file hashes, and file references
are stored in private queue receipts, not as metadata files in the output folder.
The current build uses the existing all-keyframe H.264/WAV presets. The owner is
considering delegating playback-specific transcoding to Chromatron; the default
has not been changed without that decision.

## Queue behavior

- Enqueueing does no network work or cookie access.
- Atomic, permission-restricted JSON under `state/v2-queue` survives app restarts.
- Duplicate source identities return the existing job rather than start another.
- Up to three workers, one active job per source, with one conversion slot.
- Instagram has a 10–15 second delay between jobs and pauses on access failures.
- Failed/interrupted/cancelled jobs require **Retry**. No automatic failure loop.
- **Stop queue** interrupts active jobs; queued jobs remain saved. Quitting does
  the same. After reopening, start the queue and explicitly retry interrupted jobs.
- Rename queued/failed jobs before running; completed-bundle renaming is deferred.
- Complete bundles are published atomically; receipts support recovery if a process
  stops between publishing files and saving the final queue state.

## Command-line development interface

```sh
scripts/harvester-v2 add 'https://www.youtube.com/watch?v=NCxkLReX_YQ'
scripts/harvester-v2 add --stdin < links.txt
scripts/harvester-v2 status
scripts/harvester-v2 run --output build/v2-output --watch
scripts/harvester-v2 rename JOB_ID 'Preacher gestures'
scripts/harvester-v2 cancel JOB_ID
scripts/harvester-v2 retry JOB_ID
scripts/harvester-v2 resume-source instagram
```

Use `--queue-root PATH` before the subcommand for an isolated test queue.
`run` without `--watch` drains eligible work and exits. Only one supervisor may
run a queue. Paused sources do not prevent the remaining sources from completing.

## Verification so far

- Real local-media worker tests verify named video/audio outputs, collisions,
  cleanup, and no metadata sidecar or retained combined original.
- Synthetic downloader tests exercise actual worker processes: different sources
  download concurrently, another job can be added mid-run, and conversion remains
  serialized. These tests make no source-site requests.
- Native UI smoke test: paste the same local VP9/Opus file twice; one job is
  added and one duplicate reported. Start the queue; verify H.264-only MP4 and
  PCM-only WAV. Quit and reopen; the completed job remains visible.
- Packaged backend smoke test produces separate video/audio; its local signature
  remains valid after running. Installed app opens with all four migrated jobs
  and the previous output folder. 116 automated tests pass.
- Broader live source acceptance and public distribution signing remain later milestones.
