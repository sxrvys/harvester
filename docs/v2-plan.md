# Harvester 2.0

## Product direction agreed with the owner

Harvester prepares deliberately selected found media for creative work. Keep the
Firefox extension as the fastest way to submit a find; a Mac app owns the queue,
processing, settings, and recovery. Also accept pasted links and local files.

- Adding a job should be immediate, with no mandatory naming dialog.
- Accept multiple explicitly supplied URLs; do not enumerate feeds or playlists.
- Persist jobs across restarts; flag duplicates without interrupting collection.
- Download concurrently across sources. Keep Instagram sequential and paced.
- Serialize conversion initially so encoding does not overwhelm the user's Mac.
- Show each job's stage, outcome, cancel action, and deliberate retry action.
- Names are editable; source identity and file bookkeeping stay inside the app,
  not as JSON sidecars in the user’s output folders.
- Default output: silent all-keyframe H.264 MP4 plus separate 24-bit WAV. Do not
  retain downloaded originals. Keep existing audio presets.
- Current per-item limit is 60 minutes / 500 MB of source media.
- Existing archives remain ordinary files; no automatic migration or deletion.

## First development slice

A separate local queue engine, with an inspectable JSON journal and a single
runner. Submissions do no networking. A worker processes each job in isolation;
one failed item does not block other sources. Interrupted and failed jobs require
an explicit retry. Authentication/rate-limit trouble pauses that source.

Use the existing acquisition adapters and conversion code, without replacing the
installed companion. Start with YouTube, Reddit, Instagram post URLs, and local
files; streaming blobs and Saved collection management remain separate workflows.

The development default will keep video and audio together in a named bundle.
The owner’s latest feedback favors video and audio together with video immediately
accessible. Output folders contain media only; keep receipts in private queue state.
Names must never be used as source identity. Resolve collisions with ordinary
numeric suffixes.

## Subsequent milestones

Local app 2.1 now includes preview, per-stage progress, post-download clip ranges,
optional smaller H.264/FLAC, and an explicit Chromatron file handoff. The current
signed Firefox add-on submits ordinary links through the bridge; the new naming
and queue controls are built in an unsigned 2.1 package. See [2.1 status](v2-1.md).

1. Native Mac queue window: paste many links, immediate enqueue, visible progress.
2. Firefox submission bridge: one click adds a job without holding the popup open.
3. Rename completed bundles safely; project destinations and review workflow.
4. Managed tool/runtime packaging, app signing, installation, and updates.
5. Broader source acceptance and an explicitly separate playback-recording design.

No claim of general MSE/DRM support. No background collection, telemetry, or cookie
exports. Real-account tests still require scoped authorization.
