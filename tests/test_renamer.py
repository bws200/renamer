import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from PIL import ExifTags, Image

from renamer import (
    get_exif_data_and_dates,
    get_unique_output_path,
    sanitize_to_slug,
    save_image_exclusively,
    strip_four_side_border,
)


class RenamerTests(unittest.TestCase):
    def test_capture_date_is_read_from_exif_ifd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            exif = Image.Exif()
            exif[ExifTags.IFD.Exif] = {
                ExifTags.Base.DateTimeOriginal: "2020:01:02 03:04:05"
            }
            Image.new("RGB", (4, 3)).save(image_path, exif=exif)

            _, date_for_name, date_for_label = get_exif_data_and_dates(
                str(image_path))

        self.assertEqual(date_for_name, "20200102")
        self.assertEqual(date_for_label, "20200102")

    def test_datetime_is_used_when_original_date_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            exif = Image.Exif()
            exif[ExifTags.Base.DateTime] = "2019:12:31 23:59:59"
            Image.new("RGB", (4, 3)).save(image_path, exif=exif)

            _, date_for_name, _ = get_exif_data_and_dates(str(image_path))

        self.assertEqual(date_for_name, "20191231")

    def test_original_capture_date_takes_precedence_over_datetime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            exif = Image.Exif()
            exif[ExifTags.Base.DateTime] = "2019:12:31 23:59:59"
            exif[ExifTags.IFD.Exif] = {
                ExifTags.Base.DateTimeOriginal: "2020:01:02 03:04:05"
            }
            Image.new("RGB", (4, 3)).save(image_path, exif=exif)

            _, date_for_name, _ = get_exif_data_and_dates(str(image_path))

        self.assertEqual(date_for_name, "20200102")

    def test_sanitize_to_slug_removes_unsafe_punctuation(self):
        self.assertEqual(
            sanitize_to_slug(" © Field Site A: #2! "),
            "field-site-a-2",
        )

    def test_crop_trims_each_requested_edge(self):
        image = Image.new("RGB", (100, 80), "white")

        cropped = strip_four_side_border(
            image,
            pct_left=10,
            pct_right=5,
            pct_top=12.5,
            pct_bottom=0,
        )

        self.assertEqual(cropped.size, (85, 70))

    def test_unique_output_path_skips_existing_suffixes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "photo.jpg").touch()
            Path(temp_dir, "photo-2.jpg").touch()

            output_path = get_unique_output_path(temp_dir, "photo.jpg")

        self.assertEqual(os.path.basename(output_path), "photo-3.jpg")

    def test_exclusive_save_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "photo.jpg"
            output_path.write_bytes(b"existing file")

            with self.assertRaises(FileExistsError):
                save_image_exclusively(
                    Image.new("RGB", (4, 3), "red"),
                    str(output_path),
                    "JPEG",
                )

            self.assertEqual(output_path.read_bytes(), b"existing file")

    def test_failed_save_removes_incomplete_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "photo.jpg"
            image = Mock()
            image.save.side_effect = OSError("simulated write failure")

            with self.assertRaisesRegex(OSError, "simulated write failure"):
                save_image_exclusively(image, str(output_path), "JPEG")

            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
