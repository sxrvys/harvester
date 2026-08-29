# Instagram acquisition investigation

Status: public-documentation spike and one explicitly authorized single-URL
proof completed 2026-08-29. The active Firefox profile was supplied directly to
`yt-dlp`; no cookies were exported, printed, serialized by harvestrr, or committed.

## First live result

Post `DcSvEX4IWu7` produced one deterministic archive directory containing the
preserved MP4, byte-identical retained video, a 48 kHz/24-bit stereo PCM WAV, and
versioned provenance metadata. A second acquisition resolved to the same item
directory without adding duplicate files. Manual DAW import remains the final
human acceptance check.

## Finding

Meta's supported Instagram APIs are designed around professional accounts and
their owned/managed media, publishing, comments, insights, mentions, and
messaging. The documented feature and permission surface does not provide a
consumer-account Saved collection or a way to download arbitrary posts a user
has saved. Therefore the official API is not a route to the V0 acceptance test.

Meta does provide an account-information export, which is useful as a low-risk
future input for discovering saved URLs if the export contains them. It is not a
good single-item acquisition loop: it is asynchronous and does not itself solve
media retrieval from another account's post.

## V0 recommendation

Separate discovery from acquisition:

1. The user manually copies the URL of one already-saved post. V0 does **not**
   enumerate the Saved collection.
2. After explicit approval, the Instagram adapter invokes the installed
   `yt-dlp` against that one URL and reads the existing authorized session via
   `--cookies-from-browser`. The browser and profile must be named explicitly at
   runtime; no default browser probing is allowed.
3. Cookies are read only by the downloader for that run. harvestrr does not export,
   copy, log, serialize, or commit them. Downloader stdout/stderr is sanitized
   before it becomes application logging.
4. The adapter stages downloader output and machine-readable metadata locally.
   The source-agnostic pipeline then preserves and processes those files.
5. Any login redirect, challenge, checkpoint, 401/403/429 response, or message
   indicating authentication failure stops the run. V0 does not retry auth
   failures or attempt to automate login/challenges.

This is a technical feasibility route, not a supported Instagram integration.
Instagram says automated collection without permission violates its terms, and
third-party downloader behavior can break when Instagram changes. Use should be
limited to media the user is authorized to preserve and should remain deliberately
small while the first acceptance test is evaluated.

## Alternatives considered

| Route | Decision | Reason |
|---|---|---|
| Meta Instagram API | Reject for V0 | No documented Saved-post access; professional-account focus |
| Meta information export | Keep as later discovery option | User-controlled and low-risk, but too indirect for one-item retrieval |
| `yt-dlp` + authorized browser session + supplied URL | Spike first | Smallest isolated path; supports Instagram media and browser cookies |
| Instaloader Saved-post enumeration | Defer | Expands scope to private collection automation before one-item success |
| Browser UI automation/network interception | Reject for V0 | Brittle, invasive, and unnecessary for a supplied URL |
| Manual browser download | Fallback | Safest acquisition fallback, but inconsistent metadata/carousel handling |

## Authorization gate for the next step

Before a live test, ask the user for all of the following:

- permission to access authentication material for this run;
- the browser family and exact profile to use;
- the single Instagram URL;
- confirmation that the user is authorized to preserve the post's media.

Do not ask for or accept an Instagram password. Do not commit a cookie file.

## Public sources

- [Meta Instagram API documentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [Meta: Managing information across Meta apps](https://about.fb.com/news/2023/10/manage-your-information-across-apps/)
- [Meta: How We Combat Scraping](https://about.fb.com/news/2021/04/how-we-combat-scraping/)
- [`yt-dlp` cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ)
- [`yt-dlp` Instagram extractor source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/instagram.py)
