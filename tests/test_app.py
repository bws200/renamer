import os
import tempfile
import unittest
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock, call, patch

from PIL import Image, ImageTk

import photo_renamer.app as app_module
from photo_renamer.app import ImageProcessorApp
from photo_renamer.history import get_file_fingerprint
from photo_renamer.models import StampFields
from photo_renamer.settings import PREVIEW_DEBOUNCE_MS

class AppTests(unittest.TestCase):
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


    def test_empty_state_clears_preview_and_disables_navigation(self):
        app = ImageProcessorApp.__new__(ImageProcessorApp)
        app.files = []
        app.current_index = 0
        app._preview_after_id = None
        app.current_pil_img = Image.new("RGB", (4, 3))
        app.current_fingerprint = "previous-fingerprint"
        app.rotation_angle = 90
        app.tk_orig_img = Mock()
        app.tk_edit_img = Mock()
        app.lbl_cnt = Mock()
        app.lbl_old_fn = Mock()
        app.lbl_new_fn = Mock()
        app.canvas_orig = Mock()
        app.canvas_edit = Mock()
        app.drop_loc = Mock()
        app.txt_short = Mock()
        app.txt_notes = Mock()
        app.btn_process = Mock()
        app.btn_skip = Mock()
        app.btn_back = Mock()

        app._show_empty_state()

        self.assertIsNone(app.current_pil_img)
        self.assertIsNone(app.current_fingerprint)
        self.assertEqual(app.rotation_angle, 0)
        self.assertIsNone(app.tk_orig_img)
        self.assertIsNone(app.tk_edit_img)
        app.lbl_cnt.config.assert_called_once_with(
            text="No supported images found")
        app.canvas_orig.config.assert_called_once_with(image="")
        app.canvas_edit.config.assert_called_once_with(image="")
        app.drop_loc.set.assert_called_once_with("")
        app.txt_short.delete.assert_called_once_with(0, tk.END)
        app.txt_notes.delete.assert_called_once_with("1.0", tk.END)
        app.btn_process.config.assert_called_once_with(state="disabled")
        app.btn_skip.config.assert_called_once_with(state="disabled")
        app.btn_back.config.assert_called_once_with(state="disabled")


    def test_failed_image_load_disables_processing_but_allows_skip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "broken.png").write_bytes(b"not an image")
            app = ImageProcessorApp.__new__(ImageProcessorApp)
            app.files = ["broken.png"]
            app.input_folder = temp_dir
            app.current_index = 0
            app.current_pil_img = Image.new("RGB", (4, 3))
            app.processing_history = {}
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
            app.drop_loc = Mock()
            app.txt_short = Mock()
            app.txt_notes = Mock()

            with patch.object(app_module.messagebox, "showerror"):
                app.load_preview()

        self.assertIsNone(app.current_pil_img)
        app.drop_loc.set.assert_called_once_with("")
        app.txt_short.delete.assert_called_once_with(0, tk.END)
        app.txt_notes.delete.assert_called_once_with("1.0", tk.END)
        app.btn_process.config.assert_called_with(state="disabled")
        app.btn_skip.config.assert_called_with(state="normal")


    def test_loading_stamped_image_uses_its_own_ocr_when_history_has_no_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Image.new("RGB", (20, 16), "white").save(
                Path(temp_dir) / "photo.png")
            app = ImageProcessorApp.__new__(ImageProcessorApp)
            app.files = ["photo.png"]
            app.input_folder = temp_dir
            app.current_index = 0
            app.current_pil_img = None
            app.current_fingerprint = None
            app.processing_history = {}
            app.rotation_angle = 0
            app._preview_after_id = None
            app.tk_orig_img = None
            app.tk_edit_img = None
            app._ocr_warning_shown = False
            app.root = Mock()
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
            app.drop_loc = Mock()
            app.txt_short = Mock()
            app.txt_notes = Mock()
            app.update_edited_mockup = Mock()

            with (
                patch.object(
                    app_module,
                    "read_stamp_fields",
                    return_value=StampFields(
                        "Recovered Site", "Recovered short",
                        "Recovered description"),
                ) as read_stamp,
                patch.object(ImageTk, "PhotoImage",
                             return_value=object()),
            ):
                app.load_preview()

        self.assertEqual(app.drop_loc.set.call_args_list, [
            call(""),
            call("Recovered Site"),
        ])
        app.txt_short.insert.assert_called_once_with(0, "Recovered short")
        app.txt_notes.insert.assert_called_once_with(
            "1.0", "Recovered description")
        self.assertEqual(
            read_stamp.call_args.args[0],
            os.path.join(temp_dir, "photo.png"),
        )
        app.update_edited_mockup.assert_called_once_with()


    def test_loading_valid_image_enables_processing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "photo.png"
            Image.new("RGB", (20, 16), "white").save(image_path)
            app = ImageProcessorApp.__new__(ImageProcessorApp)
            app.files = ["photo.png"]
            app.input_folder = temp_dir
            app.current_index = 0
            app.current_pil_img = None
            fingerprint = get_file_fingerprint(image_path)
            app.processing_history = {
                fingerprint: {
                    "site": "Field Site",
                    "short_text": "Cabinet 2",
                    "notes": "North gate description",
                    "source_name": "photo.png",
                    "output_name": "processed-photo.png",
                },
            }
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
            app.drop_loc = Mock()
            app.txt_short = Mock()
            app.txt_notes = Mock()
            app.update_edited_mockup = Mock()

            with patch.object(ImageTk, "PhotoImage",
                              return_value=object()):
                app.load_preview()

        self.assertIsNotNone(app.current_pil_img)
        self.assertIsNotNone(app.current_fingerprint)
        self.assertEqual(app.drop_loc.set.call_args_list, [
            call(""),
            call("Field Site"),
        ])
        self.assertEqual(app.txt_short.delete.call_args_list, [
            call(0, tk.END),
        ])
        self.assertEqual(app.txt_notes.delete.call_args_list, [
            call("1.0", tk.END),
        ])
        self.assertEqual(app.txt_short.insert.call_args_list, [
            call(0, "Cabinet 2"),
        ])
        self.assertEqual(app.txt_notes.insert.call_args_list, [
            call("1.0", "North gate description"),
        ])
        app.btn_process.config.assert_called_with(state="normal")
        app.btn_skip.config.assert_called_with(state="normal")
        app.btn_back.config.assert_called_with(state="disabled")
        app.update_edited_mockup.assert_called_once_with()


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
            app.drop_loc = Mock()
            app.txt_short = Mock()
            app.txt_notes = Mock()
            app.btn_process = Mock()
            app.btn_skip = Mock()
            app.btn_back = Mock()

            with (
                patch.object(app_module.filedialog, "askdirectory",
                             return_value=temp_dir),
                patch.object(app_module.messagebox, "showinfo"),
            ):
                app.browse_folder()

        self.assertEqual(app.input_folder, temp_dir)
        self.assertEqual(app.files, [])
        self.assertEqual(app.current_index, 0)
        self.assertIsNone(app.current_pil_img)
        app.btn_process.config.assert_called_once_with(state="disabled")
        app.btn_skip.config.assert_called_once_with(state="disabled")
        app.btn_back.config.assert_called_once_with(state="disabled")


    def test_selecting_output_folder_loads_direct_images_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "bordered_output"
            nested_output_dir = output_dir / "bordered_output"
            nested_output_dir.mkdir(parents=True)
            Image.new("RGB", (4, 3)).save(output_dir / "processed.jpg")
            Image.new("RGB", (4, 3)).save(
                nested_output_dir / "nested-processed.jpg")

            app = ImageProcessorApp.__new__(ImageProcessorApp)
            app.root = Mock()
            app.input_folder = ""
            app.processing_history = {}
            app.lbl_folder = Mock()
            app.load_preview = Mock()

            with patch.object(
                    app_module.filedialog,
                    "askdirectory",
                    return_value=str(output_dir)):
                app.browse_folder()

        self.assertEqual(app.input_folder, str(output_dir))
        self.assertEqual(app.files, ["processed.jpg"])
        app.load_preview.assert_called_once_with()


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


if __name__ == "__main__":
    unittest.main()
