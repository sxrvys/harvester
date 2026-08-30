# Unsupported-site media picker acceptance

Status: acceptance contract for the next core-functionality milestone. Packaging,
signing, and distribution remain paused until the project owner explicitly resumes
them.

## Manual acceptance result

Accepted 2026-08-30 in Firefox using MDN's iframe-based HTML video demo. After
**Select visible media**, the picker entered the accessible `srcdoc` frame,
outlined the flower video, and displayed the explicit **Harvest media** control.
The click produced a background-owned bounded harvest and the reopened popup
reported **Selected media harvest complete**.

The resulting `flower_ec751467597feb26` bundle contains a 554,058-byte preserved
WebM, a playable WebM derivative, a 48 kHz/24-bit stereo WAV, and metadata whose
recorded sizes and SHA-256 hashes match. The one-off proof created no lifecycle
ledger entry. The full automated suite passed 61 tests after acceptance.

## Successful proof

On MDN's top-level simple-video example (or one equivalent simple HTTP(S) page)
outside the first-class adapters:

1. The popup identifies the page as unsupported and offers **Select visible media**.
2. Nothing is injected and no page content is inspected before that explicit click.
3. After the click, the user clicks one visible `<video>` or `<audio>` element in
   the page or an accessible frame.
4. Hovering a harvestable element draws a temporary outline and **Harvest media**
   control so the user can confirm the exact selection without triggering native
   playback controls; moving away or ending the picker restores the page.
5. The temporary picker reads only that element's normal `currentSrc`, `src`, and
   direct child `<source src>` values. It does not enumerate other elements or links.
6. The picker removes every injected frame instance immediately after one selection
   or Escape cancellation.
7. Exactly one HTTP(S) media URL and the stable page URL cross Native Messaging.
8. The companion rejects unsafe/private destinations and preflights one item with
   a 10-minute and 500 MB default limit.
9. Acquisition is restricted to one media item with no playlist, adjacent-link,
   profile, channel, or recursive expansion.
10. The result is one ordinary local bundle with preserved input, playable media
   when applicable, extracted 48 kHz/24-bit stereo WAV when audio is present, and
   provenance metadata.
11. Closing the popup does not interrupt the background-owned attempt; reopening it
    shows a safe running, complete, or failed state.
12. Reloading the extension clears a stale picker state because injected handlers no
    longer exist; a genuinely running native operation is reported as interrupted.
13. Closing or navigating the source tab immediately cancels its picker state.

## Required clean failures

- `blob:` or Media Source Extensions: `unsupported_media`
- no ordinary URL on the selected element: `unsupported_media`
- non-HTTP(S), localhost, loopback, link-local, or private-network destination:
  `unsafe_url`
- unknown duration, duration over 10 minutes, unknown size, or size over 500 MB:
  the matching safe limit/unsupported error with no partial archive
- DRM/encrypted media, inaccessible cross-origin frame, expired URL, or unavailable required
  authentication: a sanitized unsupported/acquisition error
- a second selection while one job is running: rejected without starting another
  native process

## Privacy and permission assertions

- Permissions remain `activeTab`, `nativeMessaging`, and local extension `storage`.
- No cookie, history, `webRequest`, debugger, proxy, downloads, or broad host
  permission is added.
- No network request/response inspection, headers, browser cache, page scan,
  telemetry, or remote logging is introduced.
- After **Select visible media**, the picker may follow the user's pointer into an
  accessible frame solely to attach the one-shot click handler. It does not enumerate
  media or inspect frame contents; inaccessible cross-origin frames remain unsupported.
- Tests use mocks and local fixtures. Any public-site proof requires an explicit
  user gesture and remains within the limits above.
