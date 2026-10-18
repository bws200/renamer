import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from PIL import ExifTags, Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import renamer
from renamer import (
    PREVIEW_DEBOUNCE_MS,
    PREVIEW_MAX_DIMENSION,
    SITE_DROPDOWN_MAX_HEIGHT,
    ImageProcessorApp,
    add_bottom_stamp_strip,
    build_output_filename,
    get_exif_data_and_dates,
    get_file_fingerprint,
    get_site_dropdown_height,
    get_unique_output_path,
    load_sites,
    load_processing_history,
    parse_stamp_text,
    read_stamp_fields,
    resize_to_fit,
    sanitize_to_slug,
    save_processing_history,
    save_image_exclusively,
    strip_four_side_border,
    wrap_stamp_text,
)


class RenamerTests(unittest.TestCase):
    def test_site_dropdown_shows_all_sites_up_to_twenty_rows(self):
        self.assertEqual(get_site_dropdown_height([]), 1)
        self.assertEqual(get_site_dropdown_height(["A", "B"]), 2)
        self.assertEqual(get_site_dropdown_height(["Site"] * 20), 20)
        self.assertEqual(
            get_site_dropdown_height(["Site"] * 25),
            SITE_DROPDOWN_MAX_HEIGHT,
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

    def test_processing_history_round_trips_saved_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "processing_history.json"
            history = {
                "source-fingerprint": {
                    "site": "Field Site",
                    "notes": "North gate",
                    "source_name": "photo.jpg",
                    "output_name": "20240102-field-site-north-gate.jpg",
                },
            }

            self.assertEqual(load_processing_history(history_path), {})
            save_processing_history(history_path, history)

            self.assertEqual(load_processing_history(history_path), history)

    def test_processing_history_rejects_invalid_json_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "processing_history.json"
            history_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_processing_history(history_path)

    def test_file_fingerprint_tracks_file_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "photo.jpg"
            file_path.write_bytes(b"first image")
            first_fingerprint = get_file_fingerprint(file_path)
            file_path.write_bytes(b"second image")

            second_fingerprint = get_file_fingerprint(file_path)

        self.assertNotEqual(first_fingerprint, second_fingerprint)

    def test_stamp_ocr_parser_separates_site_from_notes(self):
        self.assertEqual(
            parse_stamp_text(
                "2024:05:06 07:08:09 | Rangiora\nFlood inspection\n"
                "North bank"
            ),
            ("Rangiora", "Flood inspection North bank"),
        )

    def test_stamp_ocr_parser_uses_line_after_standalone_timestamp_as_site(self):
        self.assertEqual(
            parse_stamp_text(
                "2026:09:18 12:26:16\nCabinet switchboard\n"
                "Inspection notes\nNorth wall"
            ),
            ("Cabinet switchboard", "Inspection notes North wall"),
        )

    def test_stamp_ocr_parser_rejects_text_without_a_timestamp(self):
        self.assertEqual(
            parse_stamp_text("Cabinet switchboard\nInspection notes"),
            ("", ""),
        )

    def test_stamp_ocr_reads_bottom_black_strip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "processed.png"
            image = add_bottom_stamp_strip(
                Image.new("RGB", (100, 80), "white"),
                "2024:05:06 07:08:09 | Rangiora",
                "North bank",
                strip_height=20,
            )
            image.save(image_path)

            with patch.object(
                    renamer.pytesseract,
                    "image_to_string",
                    return_value="2024:05:06 07:08:09 | Rangiora\nNorth bank"
            ) as ocr:
                fields = read_stamp_fields(str(image_path))

        self.assertEqual(fields, ("Rangiora", "North bank"))
        ocr_image = ocr.call_args.args[0]
        self.assertEqual(ocr_image.width, 300)
        self.assertGreaterEqual(ocr_image.height, 120)
        self.assertEqual(ocr_image.getextrema(), (0, 255))

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

    def test_datetime_is_used_when_original_date_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            exif = Image.Exif()
            exif[ExifTags.Base.DateTime] = "2019:12:31 23:59:59"
            Image.new("RGB", (4, 3)).save(image_path, exif=exif)

            _, date_for_name, _ = get_exif_data_and_dates(str(image_path))

        self.assertEqual(date_for_name, "20191231-235959")

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

    def test_filesystem_fallback_includes_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.jpg"
            Image.new("RGB", (4, 3)).save(image_path)

            with patch.object(renamer.os.path, "getctime",
                              return_value=1714986489):
                _, date_for_name, date_for_label = (
                    get_exif_data_and_dates(str(image_path)))

        fallback_datetime = renamer.datetime.fromtimestamp(1714986489)
        self.assertEqual(
            date_for_name,
            fallback_datetime.strftime("%Y%m%d-%H%M%S"),
        )
        self.assertEqual(
            date_for_label,
            fallback_datetime.strftime("%Y:%m:%d %H:%M:%S"),
        )

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

    def test_sanitize_to_slug_removes_unsafe_punctuation(self):
        self.assertEqual(
            sanitize_to_slug(" © Field Site A: #2! "),
            "field-site-a-2",
        )

    def test_output_filename_uses_timestamp_and_site_not_stamp_notes(self):
        self.assertEqual(
            build_output_filename(
                "20240506-070809", "Rangiora Field Site", ".JPG"),
            "20240506-070809-rangiora-field-site.jpg",
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

    def test_stamp_strip_adds_black_only_below_image(self):
        image = Image.new("RGB", (40, 30), (20, 80, 140))

        stamped = add_bottom_stamp_strip(image, "", strip_height=12)

        self.assertEqual(stamped.size, (40, 42))
        self.assertEqual(stamped.crop((0, 0, 40, 30)).tobytes(),
                         image.tobytes())
        self.assertEqual(stamped.crop((0, 30, 40, 42)).getextrema(),
                         ((0, 0), (0, 0), (0, 0)))

    def test_stamp_strip_stays_horizontal_below_rotated_photo(self):
        image = Image.new("RGB", (40, 80), (20, 80, 140)).rotate(90,
                                                                 expand=True)

        with patch.object(renamer, "get_scalable_font",
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

    def test_stamp_strip_places_notes_on_second_line(self):
        image = Image.new("RGB", (120, 30), (20, 80, 140))

        with patch.object(renamer, "get_scalable_font",
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

    def test_stamp_strip_grows_to_fit_wrapped_text(self):
        image = Image.new("RGB", (60, 30), (20, 80, 140))

        with patch.object(renamer, "get_scalable_font",
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
        app.current_fingerprint = "previous-fingerprint"
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
        self.assertIsNone(app.current_fingerprint)
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
                    "notes": "North gate",
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
            app.txt_notes = Mock()
            app.update_edited_mockup = Mock()

            with patch.object(renamer.ImageTk, "PhotoImage",
                              return_value=object()):
                app.load_preview()

        self.assertIsNotNone(app.current_pil_img)
        self.assertIsNotNone(app.current_fingerprint)
        self.assertEqual(app.drop_loc.set.call_args_list, [
            call(""),
            call("Field Site"),
        ])
        self.assertEqual(app.txt_notes.delete.call_args_list, [
            call(0, renamer.tk.END),
        ])
        self.assertEqual(app.txt_notes.insert.call_args_list, [
            call(0, "North gate"),
        ])
        app.btn_process.config.assert_called_with(state="normal")
        app.btn_skip.config.assert_called_with(state="normal")
        app.btn_back.config.assert_called_with(state="disabled")
        app.update_edited_mockup.assert_called_once_with()

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
            app.txt_notes = Mock()
            app.update_edited_mockup = Mock()

            with (
                patch.object(
                    renamer,
                    "read_stamp_fields",
                    return_value=("Recovered Site", "Recovered notes"),
                ) as read_stamp,
                patch.object(renamer.ImageTk, "PhotoImage",
                             return_value=object()),
            ):
                app.load_preview()

        self.assertEqual(app.drop_loc.set.call_args_list, [
            call(""),
            call("Recovered Site"),
        ])
        app.txt_notes.insert.assert_called_once_with(0, "Recovered notes")
        self.assertEqual(
            read_stamp.call_args.args[0],
            os.path.join(temp_dir, "photo.png"),
        )
        app.update_edited_mockup.assert_called_once_with()

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
            app.txt_notes = Mock()

            with patch.object(renamer.messagebox, "showerror"):
                app.load_preview()

        self.assertIsNone(app.current_pil_img)
        app.drop_loc.set.assert_called_once_with("")
        app.txt_notes.delete.assert_called_once_with(0, renamer.tk.END)
        app.btn_process.config.assert_called_with(state="disabled")
        app.btn_skip.config.assert_called_with(state="normal")


if __name__ == "__main__":
    unittest.main()
