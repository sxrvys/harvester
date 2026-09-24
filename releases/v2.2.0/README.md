# Harvester 2.2.0 signed Firefox extension

Mozilla-approved unlisted extension, signed September 24, 2026. Stable extension
ID: `@harvester-sxrvys`. Firefox 142 or newer required.

Download `harvester-firefox-2.2.0-signed.xpi` with GitHub's **Download raw file**
and install via Firefox `about:addons` → gear → **Install Add-on From File…**.
The local macOS app and native messaging bridge are also required; see the root README.

All packaged source files match this checkout byte-for-byte except manifest.json,
which Mozilla reformatted without changing its parsed content. Signature files
are retained unchanged. Firefox accepted and installed the package permanently.

SHA-256: `fa59ddb11e30103c0b0d8d580a5185839525be0279f323dc431436c96843d725`

Validated: 131 Python tests, popup tests, zero Mozilla lint errors/warnings/notices,
native release build, live signed Firefox naming/trim/queue/harvest, and two-video
Chromatron handoff. One transient native connection failure during the live test
cleared on retry; no duplicate job was created. The signed popup still describes
the default 60-minute/500 MB limits; actual native queue limits follow Settings.
