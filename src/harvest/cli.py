from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="harvest",
        description="HARVEST V0 (live Instagram acquisition requires explicit authorization)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    instagram = subparsers.add_parser("instagram", help="harvest one explicitly supplied Instagram URL")
    instagram.add_argument("url")
    instagram.add_argument("--firefox-profile", type=Path, required=True)
    instagram.add_argument("--archive-root", type=Path, default=Path("archive"))
    saved = subparsers.add_parser("saved-index", help="enumerate the authorized Instagram Saved collection")
    saved.add_argument("--firefox-profile", type=Path, required=True)
    saved.add_argument("--output", type=Path, default=Path("state/saved-index.json"))
    sync = subparsers.add_parser("saved-sync", help="incrementally discover new Saved posts")
    sync.add_argument("--firefox-profile", type=Path, required=True)
    sync.add_argument("--index", type=Path, default=Path("state/saved-index.json"))
    sync.add_argument("--partial", type=Path, default=Path("state/saved-sync-partial.json"))
    sync.add_argument("--known-streak", type=int, default=5)
    sync.add_argument("--item-ledger", type=Path, default=Path("state/item-ledger.json"))
    sync.add_argument("--archive-root", type=Path, default=Path("archive"))
    sync.add_argument("--manual-review", type=Path, default=Path("state/manual-review.json"))
    batch = subparsers.add_parser("batch-oldest", help="harvest a bounded oldest-first Saved batch")
    batch.add_argument("--firefox-profile", type=Path, required=True)
    batch.add_argument("--index", type=Path, default=Path("state/saved-index.json"))
    batch.add_argument("--state", type=Path, default=Path("state/batch-oldest-10.json"))
    batch.add_argument("--archive-root", type=Path, default=Path("archive"))
    batch.add_argument("--count", type=int, default=10)
    batch.add_argument("--min-delay", type=float, default=10.0)
    batch.add_argument("--max-delay", type=float, default=15.0)
    audit = subparsers.add_parser("audit", help="verify the local archive without modifying it")
    audit.add_argument("--archive-root", type=Path, default=Path("archive"))
    names = subparsers.add_parser("names-preview", help="preview shorter deterministic bundle names")
    names.add_argument("--archive-root", type=Path, default=Path("archive"))
    assets = subparsers.add_parser("assets-preview", help="preview readable bundle and asset paths")
    assets.add_argument("--archive-root", type=Path, default=Path("archive"))
    assets.add_argument("--overrides", type=Path, default=Path("state/name-overrides.json"))
    apply_assets = subparsers.add_parser("assets-apply", help="apply an approved local bundle/asset naming plan")
    apply_assets.add_argument("--archive-root", type=Path, default=Path("archive"))
    apply_assets.add_argument("--overrides", type=Path, default=Path("state/name-overrides.json"))
    ledger = subparsers.add_parser("ledger-sync", help="update the local authoritative item lifecycle ledger")
    ledger.add_argument("--saved-index", type=Path, default=Path("state/saved-index.json"))
    ledger.add_argument("--ledger", type=Path, default=Path("state/item-ledger.json"))
    ledger.add_argument("--archive-root", type=Path, default=Path("archive"))
    ledger.add_argument("--manual-review", type=Path, default=Path("state/manual-review.json"))
    lifecycle = subparsers.add_parser("ledger-status", help="set one item's durable lifecycle status")
    lifecycle.add_argument("source_id")
    lifecycle.add_argument(
        "status",
        choices=["discovered", "complete", "deferred", "retired-used", "retired-deleted"],
    )
    lifecycle.add_argument("--source", default="instagram")
    lifecycle.add_argument("--ledger", type=Path, default=Path("state/item-ledger.json"))
    lifecycle.add_argument("--reason")
    arguments = parser.parse_args()
    if arguments.command == "instagram":
        from .instagram import harvest_instagram_url

        destination = harvest_instagram_url(
            arguments.url,
            arguments.firefox_profile,
            arguments.archive_root,
        )
        print(destination)
        return 0
    if arguments.command == "saved-index":
        from .saved import enumerate_saved

        result = enumerate_saved(arguments.firefox_profile, arguments.output)
        print(f"{result['count']} saved posts -> {arguments.output}")
        return 0
    if arguments.command == "saved-sync":
        from .saved import sync_saved_incremental

        result = sync_saved_incremental(
            arguments.firefox_profile,
            arguments.index,
            arguments.partial,
            arguments.known_streak,
        )
        scan = result["scan"]
        if arguments.item_ledger.exists():
            from .ledger import sync_item_ledger

            sync_item_ledger(
                arguments.index,
                arguments.item_ledger,
                arguments.archive_root,
                arguments.manual_review,
            )
        print(
            f"saved sync: {scan['new_count']} new, {scan['scanned_count']} scanned, "
            f"boundary={scan['boundary']}"
        )
        return 0
    if arguments.command == "batch-oldest":
        from .batch import harvest_oldest

        result = harvest_oldest(
            arguments.index,
            arguments.state,
            arguments.firefox_profile,
            arguments.archive_root,
            arguments.count,
            arguments.min_delay,
            arguments.max_delay,
        )
        complete = sum(item["status"] == "complete" for item in result["items"])
        failed = sum(item["status"] == "failed" for item in result["items"])
        print(f"batch finished: {complete} complete, {failed} failed -> {arguments.state}")
        return 0
    if arguments.command == "audit":
        from .audit import audit_archive

        result = audit_archive(arguments.archive_root)
        summary = result["summary"]
        print(
            f"archive audit: {summary['bundles']} bundles, {summary['files']} files, "
            f"{summary['errors']} errors, {summary['warnings']} warnings"
        )
        for issue in result["issues"]:
            print(f"{issue['severity'].upper()} {issue['bundle']} {issue['code']}: {issue['detail']}")
        return 1 if summary["errors"] else 0
    if arguments.command == "names-preview":
        from .naming import preview_names

        result = preview_names(arguments.archive_root)
        for proposal in result["proposals"]:
            marker = "CHANGE" if proposal["changed"] else "KEEP"
            print(f"{marker} {proposal['current']} -> {proposal['proposed']} [{proposal['rule']}]")
        print(f"naming preview: {result['summary']['changes']} changes / {result['summary']['bundles']} bundles")
        return 0
    if arguments.command == "assets-preview":
        from .naming import preview_asset_migration

        result = preview_asset_migration(arguments.archive_root, arguments.overrides)
        for bundle in result["bundles"]:
            print(f"BUNDLE {bundle['current_folder']} -> {bundle['proposed_folder']}")
            for file in bundle["files"]:
                print(f"  {file['current']} -> {file['proposed']}")
        print(
            f"asset preview: {result['summary']['file_changes']} file changes / "
            f"{result['summary']['bundles']} bundles"
        )
        return 0
    if arguments.command == "assets-apply":
        from .naming import apply_asset_migration

        result = apply_asset_migration(arguments.archive_root, arguments.overrides)
        print(
            f"asset migration: {result['summary']['file_changes']} files / "
            f"{result['summary']['bundles']} bundles"
        )
        return 0
    if arguments.command == "ledger-sync":
        from .ledger import sync_item_ledger

        result = sync_item_ledger(
            arguments.saved_index,
            arguments.ledger,
            arguments.archive_root,
            arguments.manual_review,
        )
        print("item ledger: " + ", ".join(f"{key}={value}" for key, value in result["summary"].items()))
        return 0
    if arguments.command == "ledger-status":
        from .ledger import set_item_status

        record = set_item_status(
            arguments.ledger,
            arguments.source,
            arguments.source_id,
            arguments.status,
            arguments.reason,
        )
        print(f"{arguments.source}:{arguments.source_id} -> {record['status']}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
