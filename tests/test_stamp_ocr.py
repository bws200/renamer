import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pytesseract

from photo_renamer.image_ops import add_bottom_stamp_strip
from photo_renamer.models import StampFields
from photo_renamer.stamp_ocr import parse_stamp_text, read_stamp_fields

class StampOcrTests(unittest.TestCase):
    def test_stamp_ocr_parser_rejects_text_without_a_timestamp(self):
        self.assertEqual(
            parse_stamp_text("Cabinet switchboard\nInspection notes"),
            StampFields(),
        )


    def test_stamp_ocr_parser_separates_site_short_text_and_description(self):
        self.assertEqual(
            parse_stamp_text(
                "2024:05:06 07:08:09 | Rangiora | Cabinet 2\n"
                "Flood inspection\nNorth bank"
            ),
            StampFields(
                "Rangiora", "Cabinet 2", "Flood inspection North bank"),
        )


    def test_stamp_ocr_parser_uses_line_after_standalone_timestamp_as_site(self):
        self.assertEqual(
            parse_stamp_text(
                "2026:09:18 12:26:16\nCabinet switchboard\n"
                "Inspection notes\nNorth wall"
            ),
            StampFields("Cabinet switchboard", "", "Inspection notes North wall"),
        )


    def test_stamp_ocr_reads_bottom_black_strip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "processed.png"
            image = add_bottom_stamp_strip(
                Image.new("RGB", (100, 80), "white"),
                "2024:05:06 07:08:09 | Rangiora | Cabinet 2",
                "North bank",
                strip_height=20,
            )
            image.save(image_path)

            with patch.object(
                    pytesseract,
                    "image_to_string",
                    return_value=(
                        "2024:05:06 07:08:09 | Rangiora | Cabinet 2\n"
                        "North bank"
                    )
            ) as ocr:
                fields = read_stamp_fields(str(image_path))

        self.assertEqual(
            fields, StampFields("Rangiora", "Cabinet 2", "North bank"))
        ocr_image = ocr.call_args.args[0]
        self.assertEqual(ocr_image.width, 300)
        self.assertGreaterEqual(ocr_image.height, 120)
        self.assertEqual(ocr_image.getextrema(), (0, 255))


if __name__ == "__main__":
    unittest.main()
