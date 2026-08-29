# HARVESTRR Project Constitution

HARVESTRR exists to increase the user's ownership, agency, and creative access to
media they intentionally choose to preserve. It must never turn the user, their
attention, or their archive into a product.

## User ownership

- The user controls the archive, metadata, derivatives, configuration, and state
  created by HARVESTRR.
- Outputs use ordinary folders, media files, and inspectable JSON.
- Removing HARVESTRR must not make an existing archive inaccessible or unusable.
- HARVESTRR creates no artificial dependency on a hosted service, subscription,
  account, proprietary database, or continued availability of the project.
- HARVESTRR does not alter the ownership or copyright status of source media. The
  user remains responsible for acquiring and using media lawfully.

## Privacy

- Local-first and offline wherever possible.
- No analytics, telemetry, advertising, tracking, behavioral profiling, or data
  brokerage.
- No upload or cloud synchronization by default.
- Diagnostic information remains local unless the user deliberately chooses to
  inspect and share it.
- Authentication secrets are never logged, committed, exported by default, or
  collected for unrelated purposes.

## Explicit scope and least privilege

Every acquisition must follow this authorization chain:

```text
Explicit user action
    -> one submitted URL or explicitly bounded collection operation
        -> one scoped adapter
            -> one local result or recorded failure
```

- Browser integrations request only the permissions required to submit the URL
  the user explicitly selected.
- A single-URL request never implies permission to enumerate an account,
  collection, history, or unrelated page content.
- Broader workflows require separate, explicit authorization and distinct code
  paths.
- Failures are recorded for manual review rather than retried indefinitely.
- Authentication challenges, checkpoints, and rate-limit signals stop work.

## No coercive product mechanics

HARVESTRR must not introduce:

- Watermarks, degraded exports, artificial quotas, or paid removal of limitations
  imposed by HARVESTRR itself.
- Remote kill switches or server-dependent access to local archives.
- Dark patterns, lock-in, hidden collection, or permissions unrelated to the
  user's explicit request.
- Monetization based on selling, profiling, or exploiting user data.

## Engineering consequences

- Stable source identity and deduplication live in inspectable local state, never
  in opaque services.
- Originals are preserved byte-for-byte before derivatives are created.
- Open, durable formats are preferred.
- Operations should be deterministic, auditable, resumable, and reversible when
  practical.
- New features must be earned by real use and judged against this constitution.

The standing design question is:

> Does this feature serve the user's archive, or does it create leverage over the
> user?

If it creates leverage, it does not belong in HARVESTRR.

