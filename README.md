# harvestrr

harvestrr is a local-first tool for turning media the user intentionally saved
online into durable, predictable creative-media bundles.

Its privacy, ownership, and
least-privilege commitments are defined in
[`PROJECT_CONSTITUTION.md`](PROJECT_CONSTITUTION.md). Current and intended
licensing status is recorded in [`LICENSING.md`](LICENSING.md).

V0 has one acceptance target: transform one user-identified Instagram post into
one local bundle containing preserved originals, useful derivatives, and
provenance metadata. The project does not access a browser session or Instagram
account unless the user explicitly authorizes that step.

## Current status

- The V0 output contract and acceptance test are defined.
- Source-agnostic item, archive, and media-processing primitives are present.
- Single-URL Instagram acquisition is isolated behind a source adapter and has
  completed its first authorized live proof on 2026-08-29.
- Saved discovery uses a private Git-ignored JSON index; a first oldest-ten batch
  completed nine audio/video bundles and deferred one image-only carousel.
- Incremental Saved sync scans newest-first and stops after five consecutive
  ledgered IDs, so routine updates do not rescan the complete collection.
- No code from RADIO HARVEST is used or required.

See [`docs/v0-technical-plan.md`](docs/v0-technical-plan.md) and
[`docs/instagram-acquisition.md`](docs/instagram-acquisition.md).

## Local checks

Requires Python 3.11+ and FFmpeg/FFprobe on `PATH`.

```sh
python3 -m unittest discover -s tests -v
```

Offline archive checks and naming review:

```sh
harvest audit --archive-root archive
harvest names-preview --archive-root archive
```

The audit is read-only. Naming preview never renames a bundle; it shows proposed
bounded names and honors `manual_title` / `manual_creator` metadata overrides.
The first-corpus naming analysis and editorial proposals are recorded in
[`docs/naming-review.md`](docs/naming-review.md).

Media asset filenames omit the Instagram ID and use the readable bundle stem:

```text
<readable-stem>__audio.wav
<readable-stem>__video.mp4
original/<readable-stem>__original.mp4
```

The bundle folder, metadata, Saved index, and `state/item-ledger.json` retain the
stable identity. File presence and filenames are never used to decide whether an
item is eligible for reacquisition.

The first approved migration has been applied: bundle folders retain Instagram
IDs, while all 25 remaining media assets use clean readable role-based names.

Live acquisition requires an exact URL, an exact Firefox profile path, and the
user's explicit authorization for that run. It is intentionally not configured
through a default profile or stored cookie file.
