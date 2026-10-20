import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from PIL import Image, ImageTk, ImageOps

from .history import get_file_fingerprint, load_processing_history, save_processing_history
from .image_ops import (
    add_bottom_stamp_strip, estimate_four_side_crops, resize_to_fit,
    strip_four_side_border, to_clean_rgb,
)
from .metadata import build_output_filename, get_exif_data_and_dates
from .settings import (
    OUTPUT_FOLDER, PREVIEW_DEBOUNCE_MS, PREVIEW_MAX_DIMENSION,
    PROCESSING_HISTORY_FILE, SITES_FILE, get_site_dropdown_height, load_sites,
)
from .stamp_ocr import pytesseract, read_stamp_fields
from .storage import get_unique_output_path, save_image_exclusively


class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Dual-Preview Photo Workflow Tool")
        self.root.geometry("1240x820")

        self.input_folder = ""
        self.files = []
        self.current_index = 0
        self.processing_history = {}

        self.current_pil_img = None
        self.current_fingerprint = None
        self.rotation_angle = 0
        self._preview_after_id = None
        self._ocr_warning_shown = False

        self.tk_orig_img = None
        self.tk_edit_img = None

        sites_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), SITES_FILE)
        try:
            self.locs = load_sites(sites_path)
        except OSError as exc:
            self.locs = []
            messagebox.showerror(
                "Site Settings Error",
                f"Could not read the site list at:\n{sites_path}\n\n{exc}",
                parent=self.root,
            )

        self.create_layout()

    def create_layout(self):
        self.left = ttk.Frame(self.root, padding=15, width=360)
        self.left.pack(side="left", fill="y")
        self.left.pack_propagate(False)

        self.right = ttk.Frame(self.root, padding=15)
        self.right.pack(side="right", expand=True, fill="both")

        ttk.Button(self.left,
                   text="Select Image Folder",
                   command=self.browse_folder).pack(fill="x", pady=(0, 10))

        self.lbl_folder = ttk.Label(
            self.left,
            text="No folder selected",
            wraplength=330,
            foreground="gray",
        )
        self.lbl_folder.pack(pady=(0, 10))

        ttk.Label(self.left, text="Location / Site").pack(anchor="w")
        self.drop_loc = ttk.Combobox(self.left,
                                     values=self.locs,
                                     height=get_site_dropdown_height(
                                         self.locs),
                                     state="normal")
        self.drop_loc.pack(fill="x", pady=(0, 5))

        ttk.Label(self.left, text="Line 1 - Short text (filename + stamp)").pack(
            anchor="w")
        self.txt_short = ttk.Entry(self.left)
        self.txt_short.pack(fill="x", pady=(0, 5))

        ttk.Label(self.left, text="Line 2 - Description (stamp only)").pack(
            anchor="w")
        self.txt_notes = tk.Text(self.left, height=3, wrap="word")
        self.txt_notes.pack(fill="x", pady=(0, 10))

        crop_frame = ttk.LabelFrame(self.left,
                                    text="Trim Existing Borders (%)",
                                    padding=8)
        crop_frame.pack(fill="x", pady=(0, 10))

        self.lbl_left = ttk.Label(crop_frame, text="Left: 0.0%")
        self.lbl_left.pack(anchor="w")
        self.slider_left = ttk.Scale(
            crop_frame,
            from_=0.0,
            to=25.0,
            value=0.0,
            command=self.on_slider_change,
        )
        self.slider_left.pack(fill="x", pady=(0, 4))

        self.lbl_right = ttk.Label(crop_frame, text="Right: 0.0%")
        self.lbl_right.pack(anchor="w")
        self.slider_right = ttk.Scale(
            crop_frame,
            from_=0.0,
            to=25.0,
            value=0.0,
            command=self.on_slider_change,
        )
        self.slider_right.pack(fill="x", pady=(0, 4))

        self.lbl_top = ttk.Label(crop_frame, text="Top: 0.0%")
        self.lbl_top.pack(anchor="w")
        self.slider_top = ttk.Scale(
            crop_frame,
            from_=0.0,
            to=25.0,
            value=0.0,
            command=self.on_slider_change,
        )
        self.slider_top.pack(fill="x", pady=(0, 4))

        self.lbl_bottom = ttk.Label(crop_frame, text="Bottom: 0.0%")
        self.lbl_bottom.pack(anchor="w")
        self.slider_bottom = ttk.Scale(
            crop_frame,
            from_=0.0,
            to=25.0,
            value=0.0,
            command=self.on_slider_change,
        )
        self.slider_bottom.pack(fill="x", pady=(0, 4))

        self.drop_loc.bind("<<ComboboxSelected>>",
                           lambda e: self.schedule_edited_preview())
        self.drop_loc.bind("<KeyRelease>",
                           lambda e: self.schedule_edited_preview())

        self.txt_short.bind("<KeyRelease>",
                            lambda e: self.schedule_edited_preview())
        self.txt_short.bind("<FocusOut>",
                            lambda e: self.schedule_edited_preview())
        self.txt_notes.bind("<KeyRelease>",
                            lambda e: self.schedule_edited_preview())
        self.txt_notes.bind("<FocusOut>",
                            lambda e: self.schedule_edited_preview())

        ttk.Label(self.left,
                  text="Rotate Image Orientation:").pack(anchor="w",
                                                         pady=(2, 2))

        rot_frame = ttk.Frame(self.left)
        rot_frame.pack(fill="x", pady=(0, 15))

        ttk.Button(
            rot_frame,
            text="↺ 90° Left",
            command=lambda: self.rotate_image(90),
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))

        ttk.Button(
            rot_frame,
            text="↻ 90° Right",
            command=lambda: self.rotate_image(-90),
        ).pack(side="right", expand=True, fill="x", padx=(5, 0))

        self.btn_process = tk.Button(
            self.left,
            text="Process & Save",
            command=self.process_current,
            bg="#2ecc71",
            fg="white",
            font=("Arial", 11, "bold"),
            state="disabled",
        )
        self.btn_process.pack(fill="x", pady=3)

        self.btn_back = tk.Button(
            self.left,
            text="Previous Image",
            command=self.prev_current,
            bg="#34495e",
            fg="white",
            font=("Arial", 11),
            state="disabled",
        )
        self.btn_back.pack(fill="x", pady=3)

        self.btn_skip = tk.Button(
            self.left,
            text="Skip Image",
            command=self.skip_current,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 11),
            state="disabled",
        )
        self.btn_skip.pack(fill="x", pady=3)

        self.lbl_cnt = ttk.Label(
            self.right,
            text="Load a folder to run previews",
            font=("Arial", 12, "bold"),
        )
        self.lbl_cnt.pack()

        name_preview_frame = ttk.Frame(self.right, padding=(0, 5, 0, 10))
        name_preview_frame.pack(fill="x")

        self.lbl_old_fn = ttk.Label(
            name_preview_frame,
            text="Original File: --",
            font=("Arial", 9),
            foreground="#555555",
            anchor="center",
        )
        self.lbl_old_fn.pack(fill="x")

        self.lbl_new_fn = ttk.Label(
            name_preview_frame,
            text="New File: --",
            font=("Arial", 9, "bold"),
            foreground="#27ae60",
            anchor="center",
        )
        self.lbl_new_fn.pack(fill="x")

        container = ttk.Frame(self.right)
        container.pack(expand=True, fill="both")

        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)

        self.canvas_orig = tk.Label(container, bg="#eaeaea")
        self.canvas_orig.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.canvas_edit = tk.Label(container, bg="#eaeaea")
        self.canvas_edit.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

    def _cancel_scheduled_preview(self):
        if self._preview_after_id is not None:
            self.root.after_cancel(self._preview_after_id)
            self._preview_after_id = None

    def schedule_edited_preview(self):
        self._cancel_scheduled_preview()
        self._preview_after_id = self.root.after(
            PREVIEW_DEBOUNCE_MS,
            self._run_scheduled_preview,
        )

    def _run_scheduled_preview(self):
        self._preview_after_id = None
        self.update_edited_mockup()

    def _update_navigation_buttons(self):
        has_files = bool(self.files)
        has_current_file = (
            has_files and 0 <= self.current_index < len(self.files))
        has_current_image = (
            has_current_file and self.current_pil_img is not None)
        can_go_back = has_files and self.current_index > 0

        self.btn_process.config(
            state="normal" if has_current_image else "disabled")
        self.btn_skip.config(
            state="normal" if has_current_file else "disabled")
        self.btn_back.config(state="normal" if can_go_back else "disabled")

    def _show_empty_state(self):
        self._cancel_scheduled_preview()
        self.current_pil_img = None
        self.current_fingerprint = None
        self.rotation_angle = 0
        self.tk_orig_img = None
        self.tk_edit_img = None
        self.lbl_cnt.config(text="No supported images found")
        self.lbl_old_fn.config(text="Original File: --")
        self.lbl_new_fn.config(text="New File: --")
        self.canvas_orig.config(image="")
        self.canvas_edit.config(image="")
        self.drop_loc.set("")
        self.txt_short.delete(0, tk.END)
        self.txt_notes.delete("1.0", tk.END)
        self._update_navigation_buttons()

    def _show_complete_state(self):
        self._cancel_scheduled_preview()
        self.lbl_cnt.config(text="Batch complete")
        self._update_navigation_buttons()

    def on_slider_change(self, val):
        l = self.slider_left.get()
        r = self.slider_right.get()
        t = self.slider_top.get()
        b = self.slider_bottom.get()

        self.lbl_left.config(text=f"Left: {l:.1f}%")
        self.lbl_right.config(text=f"Right: {r:.1f}%")
        self.lbl_top.config(text=f"Top: {t:.1f}%")
        self.lbl_bottom.config(text=f"Bottom: {b:.1f}%")

        self.schedule_edited_preview()

    def browse_folder(self):
        selected = filedialog.askdirectory()
        if not selected:
            return

        output_dir = os.path.join(selected, OUTPUT_FOLDER)
        history_path = os.path.join(output_dir, PROCESSING_HISTORY_FILE)
        try:
            processing_history = load_processing_history(history_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Processing History Error",
                f"Could not read processing history at:\n{history_path}\n\n{exc}",
                parent=self.root,
            )
            return

        self.input_folder = selected
        self.processing_history = processing_history
        self.lbl_folder.config(text=f"Folder: {selected}", foreground="black")

        exts = (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
        self.files = sorted(f for f in os.listdir(selected)
                            if f.lower().endswith(exts))

        if not self.files:
            self.current_index = 0
            self._show_empty_state()
            messagebox.showinfo("No Images", "No valid images found.")
            return

        self.current_index = 0
        self.load_preview()

    def load_preview(self):
        self._cancel_scheduled_preview()
        if not self.files:
            self._show_empty_state()
            return
        if self.current_index >= len(self.files):
            self._show_complete_state()
            return

        self.rotation_angle = 0
        filename = self.files[self.current_index]
        self.current_pil_img = None
        self.current_fingerprint = None
        self.tk_orig_img = None
        self.tk_edit_img = None
        self.drop_loc.set("")
        self.txt_short.delete(0, tk.END)
        self.txt_notes.delete("1.0", tk.END)
        self._update_navigation_buttons()

        self.lbl_cnt.config(
            text=f"Image {self.current_index + 1} of {len(self.files)}")
        self.lbl_old_fn.config(text=f"Original File: {filename}")
        self.lbl_new_fn.config(text="New File: --")
        self.canvas_orig.config(image="")
        self.canvas_edit.config(image="")

        try:
            path = os.path.join(self.input_folder, filename)
            self.current_fingerprint = get_file_fingerprint(path)
            previous_record = self.processing_history.get(
                self.current_fingerprint)
            if previous_record:
                self.drop_loc.set(previous_record["site"])
                self.txt_short.insert(0, previous_record["short_text"])
                self.txt_notes.insert("1.0", previous_record["notes"])
            else:
                try:
                    stamp_fields = read_stamp_fields(path)
                except (
                        OSError,
                        pytesseract.TesseractNotFoundError,
                        pytesseract.TesseractError) as exc:
                    if not self._ocr_warning_shown:
                        messagebox.showwarning(
                            "Stamp OCR Unavailable",
                            "Could not read text from the selected photo:\n"
                            f"{path}\n\n{exc}\n\n"
                            "Install the Tesseract OCR engine and ensure "
                            "it is available on PATH to enable OCR recovery.",
                            parent=self.root,
                        )
                        self._ocr_warning_shown = True
                else:
                    if stamp_fields.site:
                        self.drop_loc.set(stamp_fields.site)
                    if stamp_fields.short_text:
                        self.txt_short.insert(0, stamp_fields.short_text)
                    if stamp_fields.description:
                        self.txt_notes.insert("1.0", stamp_fields.description)

            with Image.open(path) as raw_img:
                transposed = ImageOps.exif_transpose(raw_img)
                self.current_pil_img = to_clean_rgb(transposed)
            self._update_navigation_buttons()

            est_l, est_r, est_t, est_b = estimate_four_side_crops(
                self.current_pil_img, black_cutoff=1)

            self.slider_left.set(est_l)
            self.slider_right.set(est_r)
            self.slider_top.set(est_t)
            self.slider_bottom.set(est_b)

            self.lbl_left.config(text=f"Left: {est_l:.1f}%")
            self.lbl_right.config(text=f"Right: {est_r:.1f}%")
            self.lbl_top.config(text=f"Top: {est_t:.1f}%")
            self.lbl_bottom.config(text=f"Bottom: {est_b:.1f}%")

            thumb = resize_to_fit(self.current_pil_img, 320)

            self.tk_orig_img = ImageTk.PhotoImage(thumb)
            self.canvas_orig.config(image=self.tk_orig_img)

            self.update_edited_mockup()

        except Exception as exc:
            self.current_pil_img = None
            self.tk_orig_img = None
            self.tk_edit_img = None
            self.canvas_orig.config(image="")
            self.canvas_edit.config(image="")
            self.lbl_cnt.config(text=f"Could not load {filename}")
            self._update_navigation_buttons()
            messagebox.showerror("Error",
                                 f"Failed to preview {filename}\n\n{exc}")

    def rotate_image(self, angle):
        if self.current_pil_img is None:
            messagebox.showerror("Error", "No image loaded to rotate.")
            return
        self.rotation_angle = (self.rotation_angle + angle) % 360
        self.schedule_edited_preview()

    def update_edited_mockup(self):
        if not self.files or self.current_index >= len(self.files):
            return
        if self.current_pil_img is None:
            messagebox.showerror("Error", "No image loaded to update preview.")
            return

        img = resize_to_fit(self.current_pil_img, PREVIEW_MAX_DIMENSION)
        preview_max_dimension = max(img.size)

        l = self.slider_left.get()
        r = self.slider_right.get()
        t = self.slider_top.get()
        b = self.slider_bottom.get()

        if l > 0 or r > 0 or t > 0 or b > 0:
            img = strip_four_side_border(img,
                                         pct_left=l,
                                         pct_right=r,
                                         pct_top=t,
                                         pct_bottom=b)

        if self.rotation_angle:
            img = img.rotate(self.rotation_angle, expand=True)

        filename = self.files[self.current_index]
        input_path = os.path.join(self.input_folder, filename)

        _, date_file_str, date_label_str = get_exif_data_and_dates(input_path)

        loc_val = self.drop_loc.get().strip()
        short_text_val = self.txt_short.get().strip()
        description_val = self.txt_notes.get("1.0", "end-1c").strip()

        ext = os.path.splitext(filename)[1]
        new_filename = build_output_filename(
            date_file_str, loc_val, short_text_val, ext)
        output_dir = os.path.join(self.input_folder, OUTPUT_FOLDER)
        new_filename = os.path.basename(
            get_unique_output_path(output_dir, new_filename))

        self.lbl_old_fn.config(text=f"Original File: {filename}")
        self.lbl_new_fn.config(text=f"New File Preview: {new_filename}")

        first_stamp_line = " | ".join(
            part for part in (date_label_str, loc_val, short_text_val) if part)

        strip_height = max(24, int(max(img.size) * 0.05))
        full_bordered = add_bottom_stamp_strip(
            img,
            first_stamp_line,
            description_val,
            strip_height=strip_height)

        scale_factor = 320.0 / preview_max_dimension

        preview_w = max(1, int(full_bordered.width * scale_factor))
        preview_h = max(1, int(full_bordered.height * scale_factor))

        preview_bordered = full_bordered.resize((preview_w, preview_h),
                                                Image.Resampling.LANCZOS)

        self.tk_edit_img = ImageTk.PhotoImage(preview_bordered)
        self.canvas_edit.config(image=self.tk_edit_img)

    def process_current(self):
        if self.current_index >= len(self.files):
            return
        if self.current_pil_img is None:
            messagebox.showerror("Error", "No image loaded to process.")
            return
        if self.current_fingerprint is None:
            messagebox.showerror(
                "Error",
                "The current image has no processing-history fingerprint.")
            return

        filename = self.files[self.current_index]
        input_path = os.path.join(self.input_folder, filename)

        output_dir = os.path.join(self.input_folder, OUTPUT_FOLDER)
        os.makedirs(output_dir, exist_ok=True)

        ext = os.path.splitext(filename)[1]

        exif_obj, date_file_str, date_label_str = get_exif_data_and_dates(
            input_path)

        loc_val = self.drop_loc.get().strip()
        short_text_val = self.txt_short.get().strip()
        description_val = self.txt_notes.get("1.0", "end-1c").strip()

        output_name = build_output_filename(
            date_file_str, loc_val, short_text_val, ext)
        output_path = get_unique_output_path(output_dir, output_name)
        output_name = os.path.basename(output_path)

        confirm = messagebox.askyesno(
            "Confirm Save",
            f"Save processed photo to subfolder?\n\nFile: {output_name}\nLocation: {output_dir}",
            icon="question",
        )
        if not confirm:
            return

        img = self.current_pil_img.copy()

        l = self.slider_left.get()
        r = self.slider_right.get()
        t = self.slider_top.get()
        b = self.slider_bottom.get()

        if l > 0 or r > 0 or t > 0 or b > 0:
            img = strip_four_side_border(img,
                                         pct_left=l,
                                         pct_right=r,
                                         pct_top=t,
                                         pct_bottom=b)

        if self.rotation_angle:
            img = img.rotate(self.rotation_angle, expand=True)

        first_stamp_line = " | ".join(
            part for part in (date_label_str, loc_val, short_text_val) if part)

        strip_height = max(24, int(max(img.size) * 0.05))
        final_img = add_bottom_stamp_strip(
            img,
            first_stamp_line,
            description_val,
            strip_height=strip_height)

        save_kwargs = {}
        if exif_obj and ext.lower() in (".jpg", ".jpeg", ".tiff"):
            exif_obj[0x0112] = 1
            save_kwargs["exif"] = exif_obj.tobytes()

        # Disable JPEG subsampling and enforce high quality to prevent text compression blur
        if ext.lower() in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 98
            save_kwargs["subsampling"] = 0

        image_format = Image.registered_extensions().get(ext.lower())
        if image_format is None:
            messagebox.showerror(
                "Error", f"Unsupported output image extension: {ext}")
            return

        try:
            save_image_exclusively(final_img, output_path, image_format,
                                   save_kwargs)
        except FileExistsError:
            messagebox.showerror(
                "Save Conflict",
                f"The output file was created after confirmation and was not overwritten:\n\n{output_path}",
            )
            return
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save Error",
                                 f"Failed to save {output_path}:\n\n{exc}")
            return

        updated_history = dict(self.processing_history)
        updated_history[self.current_fingerprint] = {
            "site": loc_val,
            "short_text": short_text_val,
            "notes": description_val,
            "source_name": filename,
            "output_name": output_name,
        }
        history_path = os.path.join(output_dir, PROCESSING_HISTORY_FILE)
        try:
            save_processing_history(history_path, updated_history)
        except (OSError, ValueError) as exc:
            messagebox.showwarning(
                "Processing History Not Saved",
                f"The photo was saved as {output_name}, but its metadata "
                f"could not be saved to processing history:\n\n{exc}",
            )
        else:
            self.processing_history = updated_history

        self.current_index += 1
        self.load_preview()

    def skip_current(self):
        if self.current_index >= len(self.files):
            return
        self.current_index += 1
        self.load_preview()

    def prev_current(self):
        if self.current_index <= 0:
            return
        self.current_index -= 1
        self.load_preview()
