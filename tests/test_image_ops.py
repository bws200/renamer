import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw, ImageFont

import photo_renamer.image_ops as image_ops
from photo_renamer.image_ops import (
    add_bottom_stamp_strip, resize_to_fit, strip_four_side_border,
    wrap_stamp_text,
)
from photo_renamer.settings import PREVIEW_MAX_DIMENSION
from photo_renamer.storage import get_unique_output_path, save_image_exclusively

class ImageOpsTests(unittest.TestCase):
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


    def test_preview_resize_caps_dimensions_without_mutating_source(self):
        image = Image.new("RGB", (6000, 3000), "red")

        preview = resize_to_fit(image, PREVIEW_MAX_DIMENSION)

        self.assertEqual(preview.size, (1200, 600))
        self.assertEqual(image.size, (6000, 3000))


    def test_preview_resize_does_not_enlarge_small_images(self):
        image = Image.new("RGB", (160, 100), "red")

        preview = resize_to_fit(image, 320)

        self.assertIs(preview, image)
        self.assertEqual(preview.size, (160, 100))


    def test_stamp_strip_adds_black_only_below_image(self):
        image = Image.new("RGB", (40, 30), (20, 80, 140))

        stamped = add_bottom_stamp_strip(image, "", strip_height=12)

        self.assertEqual(stamped.size, (40, 42))
        self.assertEqual(stamped.crop((0, 0, 40, 30)).tobytes(),
                         image.tobytes())
        self.assertEqual(stamped.crop((0, 30, 40, 42)).getextrema(),
                         ((0, 0), (0, 0), (0, 0)))


    def test_stamp_strip_grows_to_fit_wrapped_text(self):
        image = Image.new("RGB", (60, 30), (20, 80, 140))

        with patch.object(image_ops, "get_scalable_font",
                          return_value=ImageFont.load_default()):
            stamped = add_bottom_stamp_strip(
                image,
                "2024:10:16 11:00:00 | Very long location name",
                "These notes need several wrapped lines to fit",
                strip_height=24,
            )

        self.assertGreater(stamped.height, image.height + 2 * 24)
        self.assertEqual(stamped.crop((0, 0, 60, 30)).tobytes(),
                         image.tobytes())


    def test_stamp_strip_places_notes_on_second_line(self):
        image = Image.new("RGB", (120, 30), (20, 80, 140))

        with patch.object(image_ops, "get_scalable_font",
                          return_value=ImageFont.load_default()):
            stamped = add_bottom_stamp_strip(
                image, "SITE", "NOTE", strip_height=40)

        self.assertEqual(stamped.size, (120, 110))
        self.assertEqual(stamped.crop((0, 0, 120, 30)).tobytes(),
                         image.tobytes())

        strip = stamped.crop((0, 30, 120, 110)).convert("L")
        first_line = strip.crop((0, 0, 120, 40)).getbbox()
        second_line = strip.crop((0, 40, 120, 80)).getbbox()
        self.assertIsNotNone(first_line)
        self.assertIsNotNone(second_line)


    def test_stamp_strip_stays_horizontal_below_rotated_photo(self):
        image = Image.new("RGB", (40, 80), (20, 80, 140)).rotate(90,
                                                                 expand=True)

        with patch.object(image_ops, "get_scalable_font",
                          return_value=ImageFont.load_default()):
            stamped = add_bottom_stamp_strip(image, "STAMP", strip_height=20)

        self.assertEqual(stamped.size, (80, 60))
        self.assertEqual(stamped.crop((0, 0, 80, 40)).tobytes(),
                         image.tobytes())
        self.assertEqual(stamped.getpixel((0, 59)), (0, 0, 0))
        text_bbox = stamped.crop((0, 40, 80, 60)).convert("L").getbbox()
        assert text_bbox is not None
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        self.assertGreater(text_width, text_height)


    def test_stamp_text_wraps_long_words_to_photo_width(self):
        font = ImageFont.load_default()
        text = "A verylongunbrokenlocationname"
        max_width = 48

        wrapped_lines = wrap_stamp_text(text, font, max_width)
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))

        self.assertGreater(len(wrapped_lines), 1)
        self.assertEqual(" ".join(wrapped_lines).replace(" ", ""), text.replace(
            " ", ""))
        for line in wrapped_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            self.assertLessEqual(bbox[2] - bbox[0], max_width)


    def test_unique_output_path_skips_existing_suffixes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "photo.jpg").touch()
            Path(temp_dir, "photo-2.jpg").touch()

            output_path = get_unique_output_path(temp_dir, "photo.jpg")

        self.assertEqual(os.path.basename(output_path), "photo-3.jpg")


if __name__ == "__main__":
    unittest.main()
