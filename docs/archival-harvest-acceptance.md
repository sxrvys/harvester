# Archival Harvest acceptance

Status: manually accepted. Packaging, signing, and distribution remain paused.

## Purpose

Archival Harvest is a distinct, explicitly triggered Instagram Saved workflow.
It maintains a local lifecycle ledger, periodically discovers newly saved posts,
and harvests small oldest-first batches so disappearing older material receives
priority. It is not a general queue, feed downloader, or unattended scraper.

## Screen

The Firefox extension provides a separate **Archival Harvest** screen showing:

- indexed, waiting, complete, deferred, and retired counts;
- the last successful Saved scan and its boundary;
- **Scan saved posts**;
- bounded batch size and randomized minimum/maximum delay controls;
- **Harvest next batch**;
- current operation and last-result status;
- the approved account-risk warning.

## Scan contract

- A scan begins only after **Scan saved posts** is clicked.
- It reads the authorized Firefox Instagram session without exporting cookies.
- It scans Saved newest-first and stops after five consecutive ledgered post IDs.
- Newly discovered posts are appended to the canonical oldest-first index and
  synchronized into the ledger as `discovered`.
- Authentication, challenge, and rate-limit signals stop the scan safely.
- A failed scan does not replace the last complete canonical index.

## Batch contract

- A batch begins only after **Harvest next batch** is clicked.
- Selection is oldest-first from non-terminal ledger entries.
- Batch size is an integer from 1 through 25; default 10.
- Delays satisfy `10 <= minimum <= maximum <= 300` seconds and every inter-item
  delay is independently randomized within that range; defaults are 10–15.
- Downloads are sequential. Ordinary failures are not retried. Authentication,
  challenge, or rate-limit signals stop the batch.
- The active global audio preset applies to newly created bundles.
- Results synchronize into the lifecycle ledger and remain inspectable locally.

The screen displays:

> Automated access may trigger Instagram restrictions or violate platform rules.
> Larger batches and shorter delays increase that risk. Harvester cannot guarantee
> account safety. You are responsible for choosing how and whether to proceed.

## Explicit exclusions

- no recurring schedule in this milestone;
- no unattended rescan;
- no Reddit, YouTube, or generic archival queue;
- no concurrency, automatic retries, challenge handling, or rate-limit bypass;
- no cookies, authentication headers, browsing history, or page contents in logs;
- no packaging, signing, or distribution work.

One-time scheduling may be considered only after the manual workflow is accepted.

## Manual acceptance

Accepted in Firefox on 2026-08-30:

- The screen loaded the existing 454-item ledger with correct lifecycle counts.
- **Scan saved posts** scanned seven newest-first posts, found two new items, and
  stopped at five consecutive known IDs. Index and ledger both advanced to 456.
- A one-item oldest-first batch selected Instagram post `DbL0aWgIApV`, created
  `burden-of-dreams-1982_les-blank_DbL0aWgIApV`, and synchronized the ledger from
  25 to 26 complete and 424 to 423 waiting.
- The bundle contains a byte-preserved 4,177,072-byte MP4, identical playable
  MP4 derivative, and configured 48 kHz/24-bit stereo WAV with matching recorded
  sizes and hashes and explicit `wav_48k_24` encoding metadata.
