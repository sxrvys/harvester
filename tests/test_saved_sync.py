from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.saved import IncrementalBoundaryError, audio_metadata_from_node, merge_incremental_index


def item(source_id: str) -> dict[str, object]:
    return {
        "source": "instagram",
        "source_id": source_id,
        "source_url": f"https://www.instagram.com/p/{source_id}/",
        "post_date": "2026-08-29T00:00:00",
        "saved_position_newest_first": 0,
    }


def index(*oldest_to_newest: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "complete": True,
        "count": len(oldest_to_newest),
        "order": "oldest-saved-first",
        "items": [item(source_id) for source_id in oldest_to_newest],
    }


class SavedSyncTests(unittest.TestCase):
    def test_adds_new_items_in_oldest_first_order_and_stops_at_five_known(self) -> None:
        existing = index("old-1", "old-2", "old-3", "old-4", "old-5", "old-6")
        scanned = [
            item("new-3"), item("new-2"), item("new-1"),
            item("old-6"), item("old-5"), item("old-4"), item("old-3"), item("old-2"),
            item("should-not-be-consumed"),
        ]
        merged, scan = merge_incremental_index(existing, scanned)
        self.assertEqual([entry["source_id"] for entry in merged["items"]][-3:], ["new-1", "new-2", "new-3"])
        self.assertEqual(scan, {
            "boundary": "known-streak",
            "known_streak_required": 5,
            "known_streak_reached": 5,
            "scanned_count": 8,
            "new_count": 3,
        })

    def test_unknown_item_resets_known_streak(self) -> None:
        existing = index("a", "b", "c", "d", "e", "f", "g")
        scanned = [item("g"), item("f"), item("new"), item("e"), item("d"), item("c"), item("b"), item("a")]
        _, scan = merge_incremental_index(existing, scanned)
        self.assertEqual(scan["scanned_count"], 8)
        self.assertEqual(scan["new_count"], 1)
        self.assertEqual(scan["known_streak_reached"], 5)

    def test_end_of_collection_is_a_valid_boundary_for_small_ledgers(self) -> None:
        merged, scan = merge_incremental_index(index("a", "b"), [item("new"), item("b"), item("a")])
        self.assertEqual(scan["boundary"], "end-of-collection")
        self.assertEqual(merged["count"], 3)

    def test_rejects_incomplete_canonical_index(self) -> None:
        incomplete = index("a")
        incomplete["complete"] = False
        with self.assertRaises(IncrementalBoundaryError):
            merge_incremental_index(incomplete, [item("a")])

    def test_reads_licensed_music_from_existing_post_node(self) -> None:
        node = {
            "clips_metadata": {
                "audio_type": "licensed_music",
                "music_info": {
                    "music_asset_info": {
                        "display_artist": "Magazine 60",
                        "title": "Don Quichotte",
                    }
                },
            }
        }
        self.assertEqual(audio_metadata_from_node(node), {
            "label": "Don Quichotte",
            "title": "Don Quichotte",
            "artist": "Magazine 60",
            "is_original": False,
        })

    def test_marks_original_audio_without_inventing_song_data(self) -> None:
        node = {
            "clips_metadata": {
                "audio_type": "original_sounds",
                "original_sound_info": {"original_audio_title": "Original audio"},
            }
        }
        self.assertEqual(audio_metadata_from_node(node), {
            "label": "Original audio",
            "title": None,
            "artist": None,
            "is_original": True,
        })
