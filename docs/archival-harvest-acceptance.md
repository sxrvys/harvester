# Archival Harvest acceptance

Status: manually accepted through the V1.0.2 multi-archive workflow.

## Purpose

Archival Harvest is a distinct, explicitly triggered Instagram Saved workflow.
It maintains a local lifecycle ledger, periodically discovers newly saved posts,
and harvests small oldest-first batches so disappearing older material receives
priority. It is not a general queue, feed downloader, or unattended scraper.

## Screen

The Firefox extension provides a separate **Archival Harvest** screen showing:

- a user-managed list of Instagram Saved pages and collections;
- indexed, waiting, complete, deferred, and retired counts;
- the last successful Saved scan and its boundary;
- **Scan saved posts**;
- bounded batch size and randomized minimum/maximum delay controls;
- **Harvest next batch**;
- current operation and last-result status;
- a readable plain-text failure log generated from the structured local JSON;
- the approved account-risk warning.

## Scan contract

- A scan begins only after **Scan saved posts** is clicked.
- The selected archive supplies the exact Saved-page URL; multiple archives keep
  separate queues and scan history.
- A successful scan-created Instagram tab closes automatically. A failed scan
  leaves it open for diagnosis.
- It reads the authorized Firefox Instagram session without exporting cookies.
- It scans Saved newest-first and stops after five consecutive ledgered post IDs.
- Newly discovered posts are appended to the canonical oldest-first index and
  synchronized into the ledger as `discovered`.
- The last-scan counter is per-scan, not cumulative, and is labeled **newly
  indexed** because Instagram may resurface an older Saved ID that was absent
  from the current index.
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
- Posts shared by multiple configured archives use one metadata-identified bundle;
  every affected ledger is refreshed before and after a batch.
- Completion reports separate downloaded and skipped counts rather than implying
  that every requested post produced media.
- The latest completed-batch result is reconstructed from the durable native batch
  record when extension-local presentation state is unavailable.

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

## V1.0.2 multi-archive acceptance

Accepted in Firefox on 2026-09-02:

- A clean first-run profile added, named, edited, renamed, selected, and reopened
  an All Saved page and a separate named collection.
- The All Saved page indexed 468 posts. The two-thumbnail collection resolved and
  indexed both posts despite Instagram not exposing ordinary post anchors.
- Selecting and scanning either archive affected only that archive, and successful
  temporary scan tabs closed automatically.
- A one-item batch processed a five-video carousel as one archival bundle containing
  five originals, five playable video derivatives, and five audio derivatives.
- The carousel exists in both configured archives but occupies one on-disk bundle;
  both ledgers recognize the shared completion.
- The resulting archive audit reported 7 bundles, 33 files, zero errors, and zero
  warnings.

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
- A later ten-item batch completed its full bounded run: six media posts were
  downloaded and four posts with no video formats were skipped into manual review.
  The six new bundles passed the archive audit; no automatic retries occurred.
