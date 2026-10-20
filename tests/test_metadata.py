import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PIL import ExifTags, Image

from photo_renamer.metadata import (
    build_output_filename, get_exif_data_and_dates, sanitize_to_slug,
)
from photo_renamer.settings import (
    SITE_DROPDOWN_MAX_HEIGHT, get_site_dropdown_height, load_sites,
)
from photo_renamer.storage import save_image_exclusively

class MetadataTests(unittest.TestCase):
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

        self.assertEqual(date_for_name, "20200102-030405")
        self.assertEqual(date_for_label, "2020:01:02 03:04:05")


    def test_capture_time_remains_in_saved_exif_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.jpg"
            output_path = Path(temp_dir) / "output.jpg"
            exif = Image.Exif()
            exif[ExifTags.IFD.Exif] = {
                ExifTags.Base.DateTimeOriginal: "2024:05:06 07:08:09"
            }
            Image.new("RGB", (12, 9), "green").save(source_path, exif=exif)

            raw_exif, _, _ = get_exif_data_and_dates(str(source_path))
            self.assertIsNotNone(raw_exif)
            assert raw_exif is not None
            raw_exif[0x0112] = 1
            save_image_exclusively(
                Image.new("RGB", (12, 9), "green"),
                str(output_path),
                "JPEG",
                {"exif": raw_exif.tobytes()},
            )

            with Image.open(output_path) as saved_image:
                saved_exif = saved_image.getexif().get_ifd(ExifTags.IFD.Exif)

        self.assertEqual(
            saved_exif[ExifTags.Base.DateTimeOriginal],
            "2024:05:06 07:08:09",
        )


    def test_datetime_is_used_when_original_date_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            exif = Image.Exif()
            exif[ExifTags.Base.DateTime] = "2019:12:31 23:59:59"
            Image.new("RGB", (4, 3)).save(image_path, exif=exif)

            _, date_for_name, _ = get_exif_data_and_dates(str(image_path))

        self.assertEqual(date_for_name, "20191231-235959")


    def test_filesystem_fallback_includes_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            Image.new("RGB", (4, 3)).save(image_path)

            with patch.object(os.path, "getctime",
                              return_value=1714986489):
                _, date_for_name, date_for_label = (
                    get_exif_data_and_dates(str(image_path)))

        fallback_datetime = datetime.fromtimestamp(1714986489)
        self.assertEqual(
            date_for_name,
            fallback_datetime.strftime("%Y%m%d-%H%M%S"),
        )
        self.assertEqual(
            date_for_label,
            fallback_datetime.strftime("%Y:%m:%d %H:%M:%S"),
        )


    def test_load_sites_reads_entries_and_skips_blank_or_comment_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "sites.txt"
            settings_path.write_text(
                "# Example sites\n\nHeadquarters\n  Field Site A  \n"
                " # another comment\nExternal Lab\n",
                encoding="utf-8",
            )

            sites = load_sites(settings_path)

        self.assertEqual(sites, [
            "Headquarters",
            "Field Site A",
            "External Lab",
        ])


    def test_midnight_capture_time_is_kept_in_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            exif = Image.Exif()
            exif[ExifTags.IFD.Exif] = {
                ExifTags.Base.DateTimeOriginal: "2020:01:02 00:00:00"
            }
            Image.new("RGB", (4, 3)).save(image_path, exif=exif)

            _, date_for_name, date_for_label = get_exif_data_and_dates(
                str(image_path))

        self.assertEqual(date_for_name, "20200102-000000")
        self.assertEqual(date_for_label, "2020:01:02 00:00:00")


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

        self.assertEqual(date_for_name, "20200102-030405")


    def test_output_filename_uses_timestamp_site_and_short_text(self):
        self.assertEqual(
            build_output_filename(
                "20240506-070809", "Rangiora Field Site", "Cabinet 2",
                ".JPG"),
            "20240506-070809-rangiora-field-site-cabinet-2.jpg",
        )


    def test_sanitize_to_slug_removes_unsafe_punctuation(self):
        self.assertEqual(
            sanitize_to_slug(" © Field Site A: #2! "),
            "field-site-a-2",
        )


    def test_site_dropdown_shows_all_sites_up_to_twenty_rows(self):
        self.assertEqual(get_site_dropdown_height([]), 1)
        self.assertEqual(get_site_dropdown_height(["A", "B"]), 2)
        self.assertEqual(get_site_dropdown_height(["Site"] * 20), 20)
        self.assertEqual(
            get_site_dropdown_height(["Site"] * 25),
            SITE_DROPDOWN_MAX_HEIGHT,
        )


if __name__ == "__main__":
    unittest.main()
