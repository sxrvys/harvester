# Reddit single-post acceptance

Status: manually accepted. Packaging, signing, and distribution remain paused.

## Contract

After one explicit **Harvest this** action on a canonical Reddit comments URL,
harvester may submit that URL to one Reddit-specific adapter and acquire at most
the media attached to that single post.

- Accept only `https://www.reddit.com/r/<subreddit>/comments/<post-id>/<slug>/`.
- Reject home pages, feeds, subreddits, profiles, searches, comment permalinks,
  Saved collections, and non-Reddit URLs.
- Use the explicitly configured Firefox profile for Reddit access without
  exporting or persisting cookies.
- Force no-playlist mode, zero whole-request retries, and zero fragment retries.
- Enforce the existing 10-minute and 500 MB ceilings and require exactly one
  completed media file before archival.
- Produce preserved original, useful video/audio derivatives, and inspectable
  provenance metadata without adding a lifecycle-ledger entry.
- Do not scan feeds or comments, crawl links, enumerate related posts, inspect
  browser traffic, capture headers, or bypass DRM/access controls.
- Fail cleanly for deleted, inaccessible, unsupported, multi-item, over-limit,
  or authentication-blocked posts without leaving a partial archive bundle.

## Manual proof target

`https://www.reddit.com/r/HolyShitHistory/comments/1uh1oty/in_1955_iranian_doctors_documented_the_days_of_a/`

Accepted in Firefox on 2026-08-30. The post produced a 24,604,629-byte preserved
MP4 and identical playable MP4 derivative (H.264/AAC, 1456x1080, 156.6 seconds),
plus a 48 kHz/24-bit stereo WAV. Recorded sizes and hashes matched, and the
one-off harvest created no lifecycle-ledger entry.
