# V0 technical plan

## Acceptance target

Given the URL of one Instagram post already saved by the user, and only after
the user authorizes use of an existing logged-in browser session, HARVEST creates
one deterministic local bundle. Re-running the same source ID updates that same
bundle rather than creating another uncontrolled copy.

The manual acceptance run must cover these checks:

1. The operator supplies one canonical post/reel URL.
2. The Instagram adapter retrieves all media belonging to that post through the
   authorized session and writes into a temporary staging directory.
3. HARVEST derives a stable item key from `instagram` plus the post shortcode.
4. Every acquired source file is copied byte-for-byte into `original/` before
   derivatives are made.
5. Every video is retained. When it has audio, HARVEST writes `audio.wav` as
   stereo, 48 kHz, 24-bit PCM (`pcm_s24le`). If multiple videos contain audio,
   their WAV names are indexed rather than silently choosing one.
6. Image and carousel files are retained in source order.
7. `metadata.json` validates against the documented contract and records source
   identity, retrieval time, files, media facts, and tool versions.
8. The user drags a generated WAV into the real music workflow and confirms it
   opens and plays correctly.
9. A second run for the same source ID targets the same directory and does not
   overwrite a different item.

## Smallest architecture

```text
Instagram adapter -> staged acquisition -> HarvestItem
                                         -> archive bundle
                                         -> FFprobe/FFmpeg derivatives
                                         -> metadata.json
```

The adapter owns platform behavior. The archive and processor accept local files
plus a `HarvestItem`; they do not know Instagram request details.

## Output contract

```text
archive/
  instagram_<shortcode>/
    metadata.json
    original/
      01_<downloaded-name>.<ext>
      02_<downloaded-name>.<ext>
    audio.wav                 # one audible video/audio source
    audio_01.wav              # used instead when there are several
    audio_02.wav
    video.<ext>               # retained video, when applicable
    video_01.<ext>            # indexed for multiple videos
    image_01.<ext>            # still/carousel files in source order
    image_02.<ext>
```

Originals are immutable inputs. Derivative files may be safely regenerated from
them. File hashes in metadata distinguish exact file content; the stable source
key prevents duplicate item directories.

## `HarvestItem` minimum

- `source`: currently the literal `instagram`
- `source_id`: stable Instagram shortcode
- `source_url`: canonical post or reel URL
- `retrieved_at`: timezone-aware UTC timestamp
- `files`: ordered acquired-file records
- optional source facts: author handle, posted timestamp, caption

Acquired-file records include archive-relative path, role, MIME/media kind,
byte size, SHA-256, and probed stream facts. `metadata.json` also carries a
schema version and the HARVEST/FFmpeg tool versions needed for provenance.

## Implementation sequence

1. **Contract (now):** item identity, deterministic directory, safe writes,
   original preservation, media probing, WAV format, metadata shape.
2. **Acquisition spike (requires explicit authorization):** run one URL through
   the selected adapter using an existing browser session; save downloader JSON
   and files into a temporary staging directory; never persist cookies.
3. **Single real item:** complete the bundle and manually verify its WAV.
4. **Small mixed set:** only after step 3, cover one reel/video, image, and
   carousel and correct observed edge cases.
5. **Reliability:** only after the mixed set, add durable run state, bounded
   retries, conservative pacing, backoff, and authentication hard-stop behavior.

## Progress

- 2026-08-29: contract and source-agnostic media/archive core completed.
- 2026-08-29: first authorized supplied-URL acquisition completed for
  `DcSvEX4IWu7`; repeat acquisition targeted the same directory with no duplicate
  files.
- Pending: manual drag-and-play verification of `audio.wav` in the user's music
  workflow, followed by a small supplied-URL mixed-media test set.
- 2026-08-29: enumerated 399 Saved IDs into a private local JSON index and ran a
  strictly paced oldest-ten batch. Nine posts completed; one eight-image carousel
  was recorded as failed/deferred because audio/video material is the priority.

Batch policy: an ordinary item failure is terminal for that batch and is appended
to the private `state/manual-review.json` queue. Resume never retries failed
items automatically. Authentication, challenge, and rate-limit failures stop the
entire batch immediately.

## Offline archive maintenance

`harvest audit` verifies metadata structure, stable identity uniqueness, recorded
paths, byte sizes, SHA-256 hashes, original presence, FFprobe readability, and the
48 kHz/24-bit/stereo WAV contract. It is read-only and exits unsuccessfully when
an error is found.

`harvest names-preview` proposes bounded deterministic folder names without
renaming anything. It prefers a short first caption line, then a short standalone
line, then an eight-word first phrase. `manual_title` and `manual_creator` fields
take precedence and are preserved when metadata is regenerated.

The first real audit on 2026-08-29 checked 10 bundles and 31 recorded files with
zero errors and zero warnings. The first naming preview proposed seven shorter
names and retained the three already concise names, including
`shame-1968_ingmar-bergman_DcSvEX4IWu7`.

Generated asset filenames use the readable stem but omit the Instagram ID. The
ID remains in the bundle folder and JSON state only. Role suffixes are stable:
`__audio`, `__video`, `__image`, and `__original`, with `-01`, `-02`, etc. for
multi-file roles. `harvest assets-preview` shows the complete folder/file plan
without applying it.

`state/item-ledger.json` is the authoritative lifecycle record keyed by
`source:source_id`. Its statuses are `discovered`, `complete`, `deferred`,
`retired-used`, and `retired-deleted`. Only `discovered` is eligible for future
automatic acquisition. A terminal status survives local file movement or
deletion, so missing files never trigger an automatic re-download.

On 2026-08-29 the user intentionally deleted the two completed C-walk bundles
without editing JSON. A ledger resync left both terminal rather than rediscovering
them; they were then marked `retired-deleted`. The eight remaining bundles and 25
media files were migrated to approved readable names. The post-migration audit
reported zero errors and zero warnings.

## Incremental Saved synchronization

Routine sync is append-only and does not enumerate the complete collection:

1. Read Saved posts newest-first.
2. Collect unknown stable IDs without modifying the canonical ledger.
3. Reset the boundary counter whenever an unknown ID appears.
4. Stop after five consecutive IDs already present in the ledger.
5. Reverse the newly discovered group and append it to the oldest-first ledger.
6. Recompute display positions and atomically replace `saved-index.json`.

Natural end-of-collection is also a valid boundary for a small collection. If
authentication, pagination, or networking fails before either boundary, the
canonical ledger remains unchanged and `saved-sync-partial.json` records that an
incomplete scan occurred. HARVEST does not model unsaves: the ledger and local
archive are intentionally durable and append-only.

## Explicitly deferred

Saved-collection enumeration, batch scheduling, a database, UI, other sources,
AI/search/analysis, cloud features, and RADIO HARVEST salvage are not part of the
first acceptance test.
