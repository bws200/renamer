import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import ExifTags, Image

import renamer
from renamer import (
    PREVIEW_DEBOUNCE_MS,
    PREVIEW_MAX_DIMENSION,
    ImageProcessorApp,
    get_exif_data_and_dates,
    get_unique_output_path,
    resize_to_fit,
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

    def test_preview_updates_are_debounced(self):
        app = ImageProcessorApp.__new__(ImageProcessorApp)
        app.root = Mock()
        app.root.after.side_effect = ["first", "second"]
        app._preview_after_id = None
        app.update_edited_mockup = Mock()

        app.schedule_edited_preview()
        app.schedule_edited_preview()

        app.root.after_cancel.assert_called_once_with("first")
        self.assertEqual(app.root.after.call_args.args[0], PREVIEW_DEBOUNCE_MS)
        app.root.after.call_args.args[1]()
        app.update_edited_mockup.assert_called_once_with()
        self.assertIsNone(app._preview_after_id)

    def test_empty_state_clears_preview_and_disables_navigation(self):
        app = ImageProcessorApp.__new__(ImageProcessorApp)
        app.files = []
        app.current_index = 0
        app._preview_after_id = None
        app.current_pil_img = Image.new("RGB", (4, 3))
        app.rotation_angle = 90
        app.tk_orig_img = Mock()
        app.tk_edit_img = Mock()
        app.lbl_cnt = Mock()
        app.lbl_old_fn = Mock()
        app.lbl_new_fn = Mock()
        app.canvas_orig = Mock()
        app.canvas_edit = Mock()
        app.btn_process = Mock()
        app.btn_skip = Mock()
        app.btn_back = Mock()

        app._show_empty_state()

        self.assertIsNone(app.current_pil_img)
        self.assertEqual(app.rotation_angle, 0)
        self.assertIsNone(app.tk_orig_img)
        self.assertIsNone(app.tk_edit_img)
        app.lbl_cnt.config.assert_called_once_with(
            text="No supported images found")
        app.canvas_orig.config.assert_called_once_with(image="")
        app.canvas_edit.config.assert_called_once_with(image="")
        app.btn_process.config.assert_called_once_with(state="disabled")
        app.btn_skip.config.assert_called_once_with(state="disabled")
        app.btn_back.config.assert_called_once_with(state="disabled")

    def test_completed_state_disables_process_and_skip_but_allows_back(self):
        app = ImageProcessorApp.__new__(ImageProcessorApp)
        app.files = ["one.jpg", "two.jpg"]
        app.current_index = len(app.files)
        app._preview_after_id = None
        app.lbl_cnt = Mock()
        app.btn_process = Mock()
        app.btn_skip = Mock()
        app.btn_back = Mock()

        app.load_preview()

        app.lbl_cnt.config.assert_called_once_with(
            text="Batch complete")
        app.btn_process.config.assert_called_once_with(state="disabled")
        app.btn_skip.config.assert_called_once_with(state="disabled")
        app.btn_back.config.assert_called_once_with(state="normal")

    def test_unloaded_current_file_can_be_skipped_but_not_processed(self):
        app = ImageProcessorApp.__new__(ImageProcessorApp)
        app.files = ["broken.jpg"]
        app.current_index = 0
        app.current_pil_img = None
        app.btn_process = Mock()
        app.btn_skip = Mock()
        app.btn_back = Mock()

        app._update_navigation_buttons()

        app.btn_process.config.assert_called_once_with(state="disabled")
        app.btn_skip.config.assert_called_once_with(state="normal")
        app.btn_back.config.assert_called_once_with(state="disabled")

    def test_selecting_empty_folder_resets_previous_batch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = ImageProcessorApp.__new__(ImageProcessorApp)
            app.input_folder = "previous-folder"
            app.files = ["previous.jpg"]
            app.current_index = 1
            app._preview_after_id = None
            app.current_pil_img = Image.new("RGB", (4, 3))
            app.rotation_angle = 90
            app.tk_orig_img = Mock()
            app.tk_edit_img = Mock()
            app.lbl_folder = Mock()
            app.lbl_cnt = Mock()
            app.lbl_old_fn = Mock()
            app.lbl_new_fn = Mock()
            app.canvas_orig = Mock()
            app.canvas_edit = Mock()
            app.btn_process = Mock()
            app.btn_skip = Mock()
            app.btn_back = Mock()

            with (
                patch.object(renamer.filedialog, "askdirectory",
                             return_value=temp_dir),
                patch.object(renamer.messagebox, "showinfo"),
            ):
                app.browse_folder()

        self.assertEqual(app.input_folder, temp_dir)
        self.assertEqual(app.files, [])
        self.assertEqual(app.current_index, 0)
        self.assertIsNone(app.current_pil_img)
        app.btn_process.config.assert_called_once_with(state="disabled")
        app.btn_skip.config.assert_called_once_with(state="disabled")
        app.btn_back.config.assert_called_once_with(state="disabled")

    def test_loading_valid_image_enables_processing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Image.new("RGB", (20, 16), "white").save(
                Path(temp_dir) / "photo.png")
            app = ImageProcessorApp.__new__(ImageProcessorApp)
            app.files = ["photo.png"]
            app.input_folder = temp_dir
            app.current_index = 0
            app.current_pil_img = None
            app.rotation_angle = 0
            app._preview_after_id = None
            app.tk_orig_img = None
            app.tk_edit_img = None
            app.lbl_cnt = Mock()
            app.lbl_old_fn = Mock()
            app.lbl_new_fn = Mock()
            app.canvas_orig = Mock()
            app.canvas_edit = Mock()
            app.btn_process = Mock()
            app.btn_skip = Mock()
            app.btn_back = Mock()
            app.slider_left = Mock()
            app.slider_right = Mock()
            app.slider_top = Mock()
            app.slider_bottom = Mock()
            app.lbl_left = Mock()
            app.lbl_right = Mock()
            app.lbl_top = Mock()
            app.lbl_bottom = Mock()
            app.update_edited_mockup = Mock()

            with patch.object(renamer.ImageTk, "PhotoImage",
                              return_value=object()):
                app.load_preview()

        self.assertIsNotNone(app.current_pil_img)
        app.btn_process.config.assert_called_with(state="normal")
        app.btn_skip.config.assert_called_with(state="normal")
        app.btn_back.config.assert_called_with(state="disabled")
        app.update_edited_mockup.assert_called_once_with()

    def test_failed_image_load_disables_processing_but_allows_skip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "broken.png").write_bytes(b"not an image")
            app = ImageProcessorApp.__new__(ImageProcessorApp)
            app.files = ["broken.png"]
            app.input_folder = temp_dir
            app.current_index = 0
            app.current_pil_img = Image.new("RGB", (4, 3))
            app.rotation_angle = 0
            app._preview_after_id = None
            app.tk_orig_img = Mock()
            app.tk_edit_img = Mock()
            app.lbl_cnt = Mock()
            app.lbl_old_fn = Mock()
            app.lbl_new_fn = Mock()
            app.canvas_orig = Mock()
            app.canvas_edit = Mock()
            app.btn_process = Mock()
            app.btn_skip = Mock()
            app.btn_back = Mock()

            with patch.object(renamer.messagebox, "showerror"):
                app.load_preview()

        self.assertIsNone(app.current_pil_img)
        app.btn_process.config.assert_called_with(state="disabled")
        app.btn_skip.config.assert_called_with(state="normal")


if __name__ == "__main__":
    unittest.main()
