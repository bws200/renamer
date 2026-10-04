import math
import os
import re
import sys
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageOps


def to_clean_rgb(img):
    """Safely converts any PIL image mode (RGBA, P, L, CMYK) to RGB without color corruption.

    Transparent pixels are composited onto a solid white background.
    """
    if img.mode == "RGB":
        return img

    img_rgba = img.convert("RGBA")
    background = Image.new("RGBA", img_rgba.size, (255, 255, 255, 255))
    composited = Image.alpha_composite(background, img_rgba)

    return composited.convert("RGB")


def get_exif_data_and_dates(image_path):
    """Extract raw EXIF bytes alongside YYYYMMDD date string for both file naming and stamp labeling.

    Returns: (raw_exif_dict, date_file_str, date_label_str)
    """
    date_str = None
    exif_obj = None

    try:
        with Image.open(image_path) as img:
            exif_obj = img.getexif()
            if exif_obj:
                date_tags = [
                    (Image.ExifTags.TAGS.get(tag_id), value)
                    for tag_id, value in exif_obj.items()
                ]
                exif_ifd = exif_obj.get_ifd(Image.ExifTags.IFD.Exif)
                date_tags.extend(
                    (Image.ExifTags.TAGS.get(tag_id), value)
                    for tag_id, value in exif_ifd.items()
                )

                for tag_name in ("DateTimeOriginal", "DateTime"):
                    for name, value in date_tags:
                        if name == tag_name:
                            raw = str(value).strip()
                            parts = raw.split()
                            if parts:
                                date_clean = parts[0].replace(":", "")
                                if (len(date_clean) == 8
                                        and date_clean.isdigit()):
                                    date_str = date_clean
                            break
                    if date_str:
                        break
    except Exception:
        pass

    if not date_str:
        try:
            timestamp = os.path.getctime(image_path)
            dt = datetime.fromtimestamp(timestamp)
            date_str = dt.strftime("%Y%m%d")
        except Exception:
            dt = datetime.now()
            date_str = dt.strftime("%Y%m%d")

    return exif_obj, date_str, date_str


def sanitize_to_slug(text):
    """Convert text into a clean filename-safe slug."""
    if not text:
        return ""
    text = text.replace("©", "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def get_unique_output_path(output_dir, output_name):
    """Return an unused output path by appending a number before the extension."""
    stem, extension = os.path.splitext(output_name)
    candidate = os.path.join(output_dir, output_name)
    suffix = 2
    while os.path.exists(candidate):
        candidate = os.path.join(output_dir, f"{stem}-{suffix}{extension}")
        suffix += 1
    return candidate


def get_scalable_font(font_size):
    """Cross-platform TrueType font loader checking explicit system paths."""
    font_names = [
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
        "Helvetica.ttf",
        "LiberationSans-Regular.ttf",
        "SegoeUI.ttf",
    ]

    # Platform-specific font lookup directories
    search_dirs = []
    if sys.platform.startswith("win"):
        search_dirs.append(
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"))
    elif sys.platform == "darwin":
        search_dirs.extend([
            "/Library/Fonts", "/System/Library/Fonts",
            "/System/Library/Fonts/Supplemental"
        ])
    else:
        search_dirs.extend([
            "/usr/share/fonts", "/usr/share/fonts/truetype",
            "/usr/local/share/fonts"
        ])

    # Search system directories first
    for folder in search_dirs:
        if os.path.exists(folder):
            for font_name in font_names:
                full_path = os.path.join(folder, font_name)
                if os.path.exists(full_path):
                    try:
                        return ImageFont.truetype(full_path, font_size)
                    except OSError:
                        continue

    # Fallback to current environment or default
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, font_size)
        except OSError:
            continue

    return ImageFont.load_default()


def estimate_four_side_crops(img, black_cutoff=1, span_ratio=0.50):
    """Scans outward from center to find 50% lines that are pure black (RGB <= 1)."""
    gray = np.array(img.convert("L"))
    h, w = gray.shape

    cx, cy = w // 2, h // 2

    half_w_span = int((w * span_ratio) / 2)
    half_h_span = int((h * span_ratio) / 2)

    x_start, x_end = max(0, cx - half_w_span), min(w, cx + half_w_span)
    y_start, y_end = max(0, cy - half_h_span), min(h, cy + half_h_span)

    def is_50pct_black_line(line_segment):
        if len(line_segment) == 0:
            return False
        dark_ratio = np.sum(line_segment <= black_cutoff) / len(line_segment)
        return dark_ratio >= 0.95

    top_y = 0
    for y in range(cy, -1, -1):
        if is_50pct_black_line(gray[y, x_start:x_end]):
            top_y = y
            break

    bottom_y = h - 1
    for y in range(cy, h):
        if is_50pct_black_line(gray[y, x_start:x_end]):
            bottom_y = y
            break

    left_x = 0
    for x in range(cx, -1, -1):
        if is_50pct_black_line(gray[y_start:y_end, x]):
            left_x = x
            break

    right_x = w - 1
    for x in range(cx, w):
        if is_50pct_black_line(gray[y_start:y_end, x]):
            right_x = x
            break

    pct_left = (left_x / w) * 100.0 if left_x > 0 else 0.0
    pct_right = (((w - 1 - right_x) / w) * 100.0 if right_x < (w - 1) else 0.0)
    pct_top = (top_y / h) * 100.0 if top_y > 0 else 0.0
    pct_bottom = (((h - 1 - bottom_y) / h) * 100.0 if bottom_y < (h -
                                                                  1) else 0.0)

    return (
        min(pct_left, 25.0),
        min(pct_right, 25.0),
        min(pct_top, 25.0),
        min(pct_bottom, 25.0),
    )


def strip_four_side_border(img,
                           pct_left=0.0,
                           pct_right=0.0,
                           pct_top=0.0,
                           pct_bottom=0.0):
    """Crops individual percentage depths off Left, Right, Top, and Bottom edges."""
    if pct_left <= 0 and pct_right <= 0 and pct_top <= 0 and pct_bottom <= 0:
        return img

    w, h = img.size
    px_left = int(w * (pct_left / 100.0))
    px_right = w - int(w * (pct_right / 100.0))
    px_top = int(h * (pct_top / 100.0))
    px_bottom = h - int(h * (pct_bottom / 100.0))

    if px_right > px_left + 10 and px_bottom > px_top + 10:
        return img.crop((px_left, px_top, px_right, px_bottom))

    return img


def add_uniform_bordered_text(base_img, border_text, border_width=80):
    """Renders crisp full-resolution borders and sharp text stamps directly on solid RGB background."""
    base_rgb = to_clean_rgb(base_img)
    w, h = base_rgb.size
    new_w = w + (border_width * 2)
    new_h = h + (border_width * 2)

    canvas = Image.new("RGB", (new_w, new_h), (0, 0, 0))
    canvas.paste(base_rgb, (border_width, border_width))

    if not border_text:
        return canvas

    # Dynamic target font size scaled directly to border pixel height
    target_font_size = max(16, int(border_width * 0.45))
    font = get_scalable_font(target_font_size)

    draw_temp = ImageDraw.Draw(canvas)
    bbox = draw_temp.textbbox((0, 0), border_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    ts_w = max(1, int(math.ceil(tw)) + 20)
    ts_h = max(1, int(math.ceil(th)) + 12)

    # Render on solid black RGB surface to ensure perfectly anti-aliased white text without alpha fringe
    text_strip = Image.new("RGB", (ts_w, ts_h), (0, 0, 0))
    strip_draw = ImageDraw.Draw(text_strip)
    strip_draw.text((10, 2), border_text, fill=(255, 255, 255), font=font)

    # Lossless rotations for border orientations
    top_strip = text_strip
    # Use rotate() for compatibility with Pillow typing; expand to preserve full bounds
    bottom_strip = text_strip.rotate(180, expand=True)
    left_strip = text_strip.rotate(90, expand=True)
    right_strip = text_strip.rotate(270, expand=True)

    # Paste Top
    canvas.paste(
        top_strip,
        (
            (new_w - top_strip.width) // 2,
            (border_width - top_strip.height) // 2,
        ),
    )

    # Paste Bottom
    canvas.paste(
        bottom_strip,
        (
            (new_w - bottom_strip.width) // 2,
            new_h - border_width + ((border_width - bottom_strip.height) // 2),
        ),
    )

    # Paste Left
    if left_strip.height <= h:
        canvas.paste(
            left_strip,
            (
                (border_width - left_strip.width) // 2,
                (new_h - left_strip.height) // 2,
            ),
        )

    # Paste Right
    if right_strip.height <= h:
        canvas.paste(
            right_strip,
            (
                new_w - border_width +
                ((border_width - right_strip.width) // 2),
                (new_h - right_strip.height) // 2,
            ),
        )

    return canvas


class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Dual-Preview Photo Workflow Tool")
        self.root.geometry("1240x820")

        self.input_folder = ""
        self.files = []
        self.current_index = 0

        self.current_pil_img = None
        self.rotation_angle = 0

        self.tk_orig_img = None
        self.tk_edit_img = None

        self.opts = [
            "",
            "© 2026 Archive Corp",
            "Public Domain",
            "All Rights Reserved",
            "CC BY-NC",
        ]
        self.locs = [
            "",
            "Headquarters",
            "Field Site A",
            "Storage Facility",
            "External Lab",
        ]
        self.stats = ["", "Final", "Draft", "Confidential", "Archival"]

        self.create_layout()
        self.bind_hotkeys()

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

        ttk.Label(self.left, text="Copyright / Owner").pack(anchor="w")
        self.drop_copy = ttk.Combobox(self.left, values=self.opts)
        self.drop_copy.pack(fill="x", pady=(0, 5))

        ttk.Label(self.left, text="Location / Site").pack(anchor="w")
        self.drop_loc = ttk.Combobox(self.left, values=self.locs)
        self.drop_loc.pack(fill="x", pady=(0, 5))

        ttk.Label(self.left, text="Status").pack(anchor="w")
        self.drop_status = ttk.Combobox(self.left, values=self.stats)
        self.drop_status.pack(fill="x", pady=(0, 5))

        ttk.Label(self.left, text="Notes").pack(anchor="w")
        self.txt_notes = ttk.Entry(self.left)
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

        for widget in (self.drop_copy, self.drop_loc, self.drop_status):
            widget.bind("<<ComboboxSelected>>",
                        lambda e: self.update_edited_mockup())
            widget.bind("<KeyRelease>", lambda e: self.update_edited_mockup())

        self.txt_notes.bind("<FocusOut>",
                            lambda e: self.update_edited_mockup())
        self.txt_notes.bind("<Return>", lambda e: self.update_edited_mockup())

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
            text="Process & Save (Space)",
            command=self.process_current,
            bg="#2ecc71",
            fg="white",
            font=("Arial", 11, "bold"),
            state="disabled",
        )
        self.btn_process.pack(fill="x", pady=3)

        self.btn_back = tk.Button(
            self.left,
            text="Previous Image (Left)",
            command=self.prev_current,
            bg="#34495e",
            fg="white",
            font=("Arial", 11),
            state="disabled",
        )
        self.btn_back.pack(fill="x", pady=3)

        self.btn_skip = tk.Button(
            self.left,
            text="Skip Image (Right)",
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

    def bind_hotkeys(self):
        self.root.bind("<Right>", lambda e: self.skip_current())
        self.root.bind("<Left>", lambda e: self.prev_current())
        self.root.bind("<space>", self.process_current_event)

    def on_slider_change(self, val):
        l = self.slider_left.get()
        r = self.slider_right.get()
        t = self.slider_top.get()
        b = self.slider_bottom.get()

        self.lbl_left.config(text=f"Left: {l:.1f}%")
        self.lbl_right.config(text=f"Right: {r:.1f}%")
        self.lbl_top.config(text=f"Top: {t:.1f}%")
        self.lbl_bottom.config(text=f"Bottom: {b:.1f}%")

        self.update_edited_mockup()

    def browse_folder(self):
        selected = filedialog.askdirectory()
        if not selected:
            return

        self.input_folder = selected
        self.lbl_folder.config(text=f"Folder: {selected}", foreground="black")

        exts = (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
        self.files = sorted(f for f in os.listdir(selected)
                            if f.lower().endswith(exts))

        if not self.files:
            messagebox.showinfo("No Images", "No valid images found.")
            return

        self.current_index = 0
        self.btn_process.config(state="normal")
        self.btn_back.config(state="normal")
        self.btn_skip.config(state="normal")

        self.load_preview()

    def load_preview(self):
        if not self.files or self.current_index >= len(self.files):
            return

        self.rotation_angle = 0
        filename = self.files[self.current_index]

        self.lbl_cnt.config(
            text=f"Image {self.current_index + 1} of {len(self.files)}")

        try:
            path = os.path.join(self.input_folder, filename)
            raw_img = Image.open(path)

            transposed = ImageOps.exif_transpose(raw_img)
            self.current_pil_img = to_clean_rgb(transposed)

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

            thumb = self.current_pil_img.copy()
            thumb.thumbnail((320, 320), Image.Resampling.LANCZOS)

            self.tk_orig_img = ImageTk.PhotoImage(thumb)
            self.canvas_orig.config(image=self.tk_orig_img)

            self.update_edited_mockup()

        except Exception as exc:
            messagebox.showerror("Error",
                                 f"Failed to preview {filename}\n\n{exc}")

    def rotate_image(self, angle):
        if self.current_pil_img is None:
            messagebox.showerror("Error", "No image loaded to rotate.")
            return
        self.rotation_angle = (self.rotation_angle + angle) % 360
        self.update_edited_mockup()

    def update_edited_mockup(self):
        if not self.files or self.current_index >= len(self.files):
            return
        if self.current_pil_img is None:
            messagebox.showerror("Error", "No image loaded to update preview.")
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

        filename = self.files[self.current_index]
        input_path = os.path.join(self.input_folder, filename)

        _, date_file_str, date_label_str = get_exif_data_and_dates(input_path)

        copy_val = self.drop_copy.get().strip()
        loc_val = self.drop_loc.get().strip()
        status_val = self.drop_status.get().strip()
        notes_val = self.txt_notes.get().strip()

        ext = os.path.splitext(filename)[1]
        new_fn_parts = [
            date_file_str,
            sanitize_to_slug(copy_val),
            sanitize_to_slug(loc_val),
            sanitize_to_slug(status_val),
            sanitize_to_slug(notes_val),
        ]
        new_filename = ("-".join(part for part in new_fn_parts if part) +
                        ext.lower())
        output_dir = os.path.join(self.input_folder, "bordered_output")
        new_filename = os.path.basename(
            get_unique_output_path(output_dir, new_filename))

        self.lbl_old_fn.config(text=f"Original File: {filename}")
        self.lbl_new_fn.config(text=f"New File Preview: {new_filename}")

        parts = [
            date_label_str,
            copy_val,
            loc_val,
            status_val,
            notes_val,
        ]
        border_text = " | ".join(p for p in parts if p)

        border_thickness = int(max(img.size) * 0.05)
        full_bordered = add_uniform_bordered_text(
            img, border_text, border_width=border_thickness)

        orig_w, orig_h = self.current_pil_img.size
        if self.rotation_angle in (90, 270):
            orig_w, orig_h = orig_h, orig_w

        max_orig_dim = max(orig_w, orig_h)
        scale_factor = 320.0 / max_orig_dim if max_orig_dim > 0 else 1.0

        preview_w = max(1, int(full_bordered.width * scale_factor))
        preview_h = max(1, int(full_bordered.height * scale_factor))

        preview_bordered = full_bordered.resize((preview_w, preview_h),
                                                Image.Resampling.LANCZOS)

        self.tk_edit_img = ImageTk.PhotoImage(preview_bordered)
        self.canvas_edit.config(image=self.tk_edit_img)

    def process_current_event(self, event):
        focused = self.root.focus_get()
        if isinstance(focused, (ttk.Entry, ttk.Combobox, tk.Entry)):
            return
        if self.btn_process["state"] == "normal":
            self.process_current()

    def process_current(self):
        if self.current_index >= len(self.files):
            return

        filename = self.files[self.current_index]
        input_path = os.path.join(self.input_folder, filename)

        output_dir = os.path.join(self.input_folder, "bordered_output")
        os.makedirs(output_dir, exist_ok=True)

        ext = os.path.splitext(filename)[1]

        exif_obj, date_file_str, date_label_str = get_exif_data_and_dates(
            input_path)

        copy_val = self.drop_copy.get().strip()
        loc_val = self.drop_loc.get().strip()
        status_val = self.drop_status.get().strip()
        notes_val = self.txt_notes.get().strip()

        filename_parts = [
            date_file_str,
            sanitize_to_slug(copy_val),
            sanitize_to_slug(loc_val),
            sanitize_to_slug(status_val),
            sanitize_to_slug(notes_val),
        ]
        output_name = ("-".join(part for part in filename_parts if part) +
                       ext.lower())
        output_path = get_unique_output_path(output_dir, output_name)
        output_name = os.path.basename(output_path)

        confirm = messagebox.askyesno(
            "Confirm Save",
            f"Save processed photo to subfolder?\n\nFile: {output_name}\nLocation: {output_dir}",
            icon="question",
        )
        if not confirm:
            return

        if self.current_pil_img is None:
            messagebox.showerror("Error", "No image loaded to process.")
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

        border_text = " | ".join(
            x for x in
            [date_label_str, copy_val, loc_val, status_val, notes_val] if x)

        border_thickness = int(max(img.size) * 0.05)
        final_img = add_uniform_bordered_text(img,
                                              border_text,
                                              border_width=border_thickness)

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

        output_created = False
        try:
            with open(output_path, "xb") as output_file:
                output_created = True
                final_img.save(output_file,
                               format=image_format,
                               **save_kwargs)
        except FileExistsError:
            messagebox.showerror(
                "Save Conflict",
                f"The output file was created after confirmation and was not overwritten:\n\n{output_path}",
            )
            return
        except (OSError, ValueError) as exc:
            if output_created:
                try:
                    os.remove(output_path)
                except FileNotFoundError:
                    pass
                except OSError as cleanup_error:
                    messagebox.showerror(
                        "Save Error",
                        f"Failed to save {output_path}:\n\n{exc}\n\n"
                        f"Could not remove the incomplete output file:\n{cleanup_error}",
                    )
                    return
            messagebox.showerror("Save Error",
                                 f"Failed to save {output_path}:\n\n{exc}")
            return

        self.txt_notes.delete(0, tk.END)
        self.current_index += 1
        self.load_preview()

    def skip_current(self):
        if self.current_index >= len(self.files):
            return
        self.txt_notes.delete(0, tk.END)
        self.current_index += 1
        self.load_preview()

    def prev_current(self):
        if self.current_index <= 0:
            return
        self.txt_notes.delete(0, tk.END)
        self.current_index -= 1
        self.load_preview()


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()
