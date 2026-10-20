import json
import tempfile
import unittest
from pathlib import Path

from photo_renamer.history import (
    get_file_fingerprint, load_processing_history, save_processing_history,
)

class HistoryTests(unittest.TestCase):
    def test_file_fingerprint_tracks_file_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "photo.jpg"
            file_path.write_bytes(b"first image")
            first_fingerprint = get_file_fingerprint(file_path)
            file_path.write_bytes(b"second image")

            second_fingerprint = get_file_fingerprint(file_path)

        self.assertNotEqual(first_fingerprint, second_fingerprint)


    def test_processing_history_migrates_records_without_short_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "processing_history.json"
            legacy_history = {
                "source-fingerprint": {
                    "site": "Field Site",
                    "notes": "North gate description",
                    "source_name": "photo.jpg",
                    "output_name": "20240102-field-site.jpg",
                },
            }
            history_path.write_text(
                json.dumps(legacy_history), encoding="utf-8")

            loaded_history = load_processing_history(history_path)

        self.assertEqual(
            loaded_history["source-fingerprint"]["short_text"], "")
        self.assertEqual(
            loaded_history["source-fingerprint"]["notes"],
            "North gate description",
        )


    def test_processing_history_rejects_invalid_json_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "processing_history.json"
            history_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_processing_history(history_path)


    def test_processing_history_round_trips_saved_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "processing_history.json"
            history = {
                "source-fingerprint": {
                    "site": "Field Site",
                    "short_text": "Cabinet 2",
                    "notes": "North gate description",
                    "source_name": "photo.jpg",
                    "output_name": "20240102-field-site-cabinet-2.jpg",
                },
            }

            self.assertEqual(load_processing_history(history_path), {})
            save_processing_history(history_path, history)

            self.assertEqual(load_processing_history(history_path), history)


if __name__ == "__main__":
    unittest.main()
