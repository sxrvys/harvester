from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.naming import apply_asset_migration, preview_asset_migration, propose_name


class NamingTests(unittest.TestCase):
    def test_preserves_short_title_creator_pattern(self) -> None:
        proposed, title, creator, rule = propose_name({
            "source_id": "ABC",
            "caption": "Shame (1968) - Ingmar Bergman\n\nDescription",
        })
        self.assertEqual(proposed, "shame-1968_ingmar-bergman_ABC")
        self.assertEqual((title, creator, rule), ("Shame (1968)", "Ingmar Bergman", "short-first-line"))

    def test_prefers_short_standalone_line_over_long_intro(self) -> None:
        proposed, title, _, rule = propose_name({
            "source_id": "ABC",
            "caption": "This is a very long introductory paragraph that contains far too many words to become a useful filesystem title for a saved media item.\n\nStreetwise\n🎬 Martin Bell, 1984",
        })
        self.assertEqual(proposed, "streetwise_martin-bell-1984_ABC")
        self.assertEqual((title, rule), ("Streetwise", "work-credit"))

    def test_uses_labeled_tutorial_detail(self) -> None:
        proposed, title, creator, rule = propose_name({
            "source_id": "ABC",
            "caption": "CWALK FOOTWORK TUTORIAL\nFootwork name :- V step with Back Step\n#cwalk",
        })
        self.assertEqual(proposed, "cwalk-footwork-tutorial-v-step-with-back-step_ABC")
        self.assertEqual(title, "CWALK FOOTWORK TUTORIAL V step with Back Step")
        self.assertIsNone(creator)
        self.assertEqual(rule, "labeled-detail")

    def test_bounds_long_prose(self) -> None:
        proposed, title, creator, rule = propose_name({
            "source_id": "ABC",
            "caption": "One two three four five six seven eight nine ten eleven twelve thirteen",
        })
        self.assertEqual(proposed, "one-two-three-four-five-six-seven-eight_ABC")
        self.assertEqual(title, "One two three four five six seven eight")
        self.assertIsNone(creator)
        self.assertEqual(rule, "bounded-first-phrase")

    def test_manual_override_wins(self) -> None:
        proposed, title, creator, rule = propose_name({
            "source_id": "ABC",
            "caption": "Automatic caption",
            "manual_title": "My Title",
            "manual_creator": "My Creator",
        })
        self.assertEqual(proposed, "my-title_my-creator_ABC")
        self.assertEqual((title, creator, rule), ("My Title", "My Creator", "manual"))

    def test_asset_preview_keeps_id_in_folder_but_not_media_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "old_ABC"
            bundle.mkdir()
            metadata = {
                "item": {"source_id": "ABC", "caption": "Shame (1968) - Ingmar Bergman"},
                "files": [
                    {"path": "original/01_clip.mp4", "role": "original"},
                    {"path": "audio.wav", "role": "audio"},
                ],
            }
            (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            proposal = preview_asset_migration(root)["bundles"][0]
            self.assertEqual(proposal["proposed_folder"], "shame-1968_ingmar-bergman_ABC")
            self.assertEqual(
                [file["proposed"] for file in proposal["files"]],
                [
                    "original/shame-1968_ingmar-bergman__original.mp4",
                    "shame-1968_ingmar-bergman__audio.wav",
                ],
            )

    def test_apply_asset_migration_updates_files_metadata_and_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "old_ABC"
            original = bundle / "original" / "01_clip.mp4"
            original.parent.mkdir(parents=True)
            original.write_bytes(b"original")
            audio = bundle / "audio.wav"
            audio.write_bytes(b"audio")
            metadata = {
                "item": {"source_id": "ABC", "caption": "Shame (1968) - Ingmar Bergman"},
                "files": [
                    {"path": "original/01_clip.mp4", "role": "original"},
                    {"path": "audio.wav", "role": "audio"},
                ],
            }
            (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            result = apply_asset_migration(root)
            migrated = root / "shame-1968_ingmar-bergman_ABC"
            migrated_metadata = json.loads((migrated / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(result["summary"]["file_changes"], 2)
            self.assertTrue((migrated / "shame-1968_ingmar-bergman__audio.wav").is_file())
            self.assertEqual(
                migrated_metadata["files"][0]["path"],
                "original/shame-1968_ingmar-bergman__original.mp4",
            )
