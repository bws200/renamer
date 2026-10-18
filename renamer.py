import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
import pytesseract
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageOps

PREVIEW_MAX_DIMENSION = 1200
PREVIEW_DEBOUNCE_MS = 120
SITE_DROPDOWN_MAX_HEIGHT = 20
SITES_FILE = "sites.txt"
PROCESSING_HISTORY_FILE = "processing_history.json"


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
    """Extract EXIF and a date-time value for filenames and border labels.

    Returns: (raw_exif_dict, filename_timestamp, border_timestamp)
    """
    capture_datetime = None
    has_capture_time = False
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
                            for date_format in (
                                    "%Y:%m:%d %H:%M:%S",
                                    "%Y:%m:%d"):
                                try:
                                    capture_datetime = datetime.strptime(
                                        raw, date_format)
                                except ValueError:
                                    continue
                                has_capture_time = "%H:%M:%S" in date_format
                                break
                            break
                    if capture_datetime:
                        break
    except Exception:
        pass

    if not capture_datetime:
        try:
            timestamp = os.path.getctime(image_path)
            capture_datetime = datetime.fromtimestamp(timestamp)
            has_capture_time = True
        except Exception:
            capture_datetime = datetime.now()
            has_capture_time = True

    filename_timestamp = capture_datetime.strftime("%Y%m%d")
    border_timestamp = capture_datetime.strftime("%Y:%m:%d")
    if has_capture_time:
        filename_timestamp += capture_datetime.strftime("-%H%M%S")
        border_timestamp += capture_datetime.strftime(" %H:%M:%S")

    return exif_obj, filename_timestamp, border_timestamp


def sanitize_to_slug(text):
    """Convert text into a clean filename-safe slug."""
    if not text:
        return ""
    text = text.replace("©", "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def build_output_filename(timestamp, site, extension):
    """Build a filename from the timestamp and site; notes remain stamp-only."""
    parts = [timestamp, sanitize_to_slug(site)]
    return "-".join(part for part in parts if part) + extension.lower()


def load_sites(settings_path):
    """Load site names from a UTF-8 text file, one site per line."""
    with open(settings_path, encoding="utf-8-sig") as settings_file:
        return [
            line.strip()
            for line in settings_file
            if line.strip() and not line.lstrip().startswith("#")
        ]


def get_site_dropdown_height(sites):
    """Show every site when possible, up to the dropdown's 20-row limit."""
    return max(1, min(len(sites), SITE_DROPDOWN_MAX_HEIGHT))


def resize_to_fit(img, max_dimension):
    """Resize an image to fit within a square bound without enlarging it."""
    width, height = img.size
    scale = min(1.0, max_dimension / max(width, height))
    if scale == 1.0:
        return img
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return img.resize(size, Image.Resampling.LANCZOS)


def get_unique_output_path(output_dir, output_name):
    """Return an unused output path by appending a number before the extension."""
    stem, extension = os.path.splitext(output_name)
    candidate = os.path.join(output_dir, output_name)
    suffix = 2
    while os.path.exists(candidate):
        candidate = os.path.join(output_dir, f"{stem}-{suffix}{extension}")
        suffix += 1
    return candidate


def get_file_fingerprint(file_path):
    """Return a SHA-256 fingerprint for a file's contents."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_prior_processed_output(source_path, output_dir):
    """Find the newest output whose filename starts with the source timestamp."""
    _, timestamp, _ = get_exif_data_and_dates(source_path)
    source_extension = os.path.splitext(source_path)[1].lower()
    candidates = []
    try:
        with os.scandir(output_dir) as entries:
            for entry in entries:
                stem, extension = os.path.splitext(entry.name)
                if (entry.is_file()
                        and extension.lower() == source_extension
                        and (stem == timestamp
                             or stem.startswith(f"{timestamp}-"))):
                    candidates.append(entry.path)
    except FileNotFoundError:
        return None

    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def parse_stamp_text(ocr_text):
    """Interpret OCR output as the stamped site line followed by notes."""
    lines = [
        re.sub(r"\s+", " ", line).strip(" |")
        for line in ocr_text.splitlines()
    ]
    lines = [line for line in lines if line]
    if not lines:
        return "", ""

    timestamp_match = re.match(
        r"^\d{4}:\d{2}:\d{2}(?:\s+\d{2}:\d{2}:\d{2})?"
        r"\s*(?:\|\s*)?(.*)$",
        lines[0],
    )
    if timestamp_match:
        site = timestamp_match.group(1).strip()
        notes = " ".join(lines[1:])
    else:
        site = lines[0]
        notes = " ".join(lines[1:])
    return site, notes


def read_stamp_fields(image_path):
    """OCR the black strip at the bottom of a previously processed image."""
    with Image.open(image_path) as source_image:
        image = ImageOps.exif_transpose(source_image).convert("L")
        width, height = image.size
        pixels = np.asarray(image)
        top = height
        for row in range(height - 1, max(-1, height - height // 3 - 1), -1):
            if np.count_nonzero(pixels[row] < 70) / width < 0.85:
                break
            top = row

        if top == height:
            return "", ""

        strip = image.crop((0, top, width, height))
        scale = min(3.0, max(1.0, 1600.0 / width))
        if scale > 1:
            strip = strip.resize(
                (int(width * scale), max(1, int(strip.height * scale))),
                Image.Resampling.LANCZOS,
            )
        text = pytesseract.image_to_string(
            ImageOps.autocontrast(strip),
            config="--psm 6",
        )
    return parse_stamp_text(text)


def load_processing_history(history_path):
    """Load saved site and note values indexed by source-file fingerprint."""
    try:
        with open(history_path, encoding="utf-8") as history_file:
            history = json.load(history_file)
    except FileNotFoundError:
        return {}

    if not isinstance(history, dict):
        raise ValueError("Processing history must contain a JSON object.")

    for fingerprint, record in history.items():
        if not isinstance(fingerprint, str) or not isinstance(record, dict):
            raise ValueError("Processing history contains an invalid record.")
        if not all(
                isinstance(record.get(field), str)
                for field in ("site", "notes", "source_name", "output_name")):
            raise ValueError("Processing history contains an incomplete record.")

    return history


def save_processing_history(history_path, history):
    """Atomically write processing history so an interrupted save cannot truncate it."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=os.path.dirname(history_path),
                prefix=".processing-history-",
                suffix=".tmp",
                delete=False) as history_file:
            temporary_path = history_file.name
            json.dump(history, history_file, ensure_ascii=False, indent=2)
            history_file.write("\n")
        os.replace(temporary_path, history_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass


def save_image_exclusively(image, output_path, image_format, save_kwargs=None):
    """Save an image without replacing an existing file."""
    output_created = False
    try:
        with open(output_path, "xb") as output_file:
            output_created = True
            image.save(output_file, format=image_format, **(save_kwargs or {}))
    except FileExistsError:
        raise
    except (OSError, ValueError) as save_error:
        if output_created:
            try:
                os.remove(output_path)
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                raise OSError(
                    f"Failed to save {output_path}: {save_error}. "
                    f"Could not remove the incomplete output file: "
                    f"{cleanup_error}") from save_error
        raise


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


def wrap_stamp_text(text, font, max_width):
    """Wrap stamp text at word boundaries, splitting overlong words as needed."""
    measure_image = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(measure_image)

    def text_width(value):
        bbox = draw.textbbox((0, 0), value, font=font)
        return bbox[2] - bbox[0]

    wrapped_lines = []

    for paragraph in text.splitlines() or [text]:
        words = paragraph.split()
        if not words:
            continue

        current_line = ""
        for word in words:
            candidate = f"{current_line} {word}".strip()
            if text_width(candidate) <= max_width:
                current_line = candidate
                continue

            if current_line:
                wrapped_lines.append(current_line)
                current_line = ""

            remaining_word = word
            while remaining_word:
                fitting_word = ""
                for character in remaining_word:
                    candidate = fitting_word + character
                    if text_width(candidate) > max_width:
                        break
                    fitting_word = candidate

                if not fitting_word:
                    fitting_word = remaining_word[0]
                remaining_word = remaining_word[len(fitting_word):]
                if remaining_word:
                    wrapped_lines.append(fitting_word)
                else:
                    current_line = fitting_word

        if current_line:
            wrapped_lines.append(current_line)

    return wrapped_lines


def add_bottom_stamp_strip(base_img,
                          first_line,
                          second_line="",
                          strip_height=80):
    """Append a black strip containing up to two centered stamp lines."""
    base_rgb = to_clean_rgb(base_img)
    w, h = base_rgb.size
    stamp_fields = [line for line in (first_line, second_line) if line]
    has_two_stamp_fields = len(stamp_fields) > 1
    if has_two_stamp_fields:
        strip_height *= 2

    target_font_size = max(
        1,
        int(strip_height * (0.32 if has_two_stamp_fields else 0.45)),
    )
    font = get_scalable_font(target_font_size)
    lines = []
    for field in stamp_fields:
        lines.extend(wrap_stamp_text(field, font, max(1, w - 20)))

    if lines:
        draw_measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        line_boxes = [
            draw_measure.textbbox((0, 0), line, font=font) for line in lines
        ]
        line_heights = [bbox[3] - bbox[1] for bbox in line_boxes]
        line_gap = max(1, target_font_size // 8) if len(lines) > 1 else 0
        total_text_height = sum(line_heights) + line_gap * (len(lines) - 1)
        vertical_padding = max(4, target_font_size // 4)
        strip_height = max(
            strip_height,
            total_text_height + vertical_padding * 2,
        )
    else:
        line_boxes = []
        line_heights = []
        line_gap = 0

    canvas = Image.new("RGB", (w, h + strip_height), (0, 0, 0))
    canvas.paste(base_rgb, (0, 0))
    if not lines:
        return canvas

    draw = ImageDraw.Draw(canvas)
    total_text_height = sum(line_heights) + line_gap * (len(lines) - 1)
    text_y = h + (strip_height - total_text_height) // 2

    for line, bbox, line_height in zip(lines, line_boxes, line_heights):
        text_width = bbox[2] - bbox[0]
        text_x = (w - text_width) // 2 - bbox[0]
        draw.text((text_x, text_y - bbox[1]),
                  line,
                  fill=(255, 255, 255),
                  font=font)
        text_y += line_height + line_gap

    return canvas


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

        sites_path = os.path.join(os.path.dirname(__file__), SITES_FILE)
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

        self.drop_loc.bind("<<ComboboxSelected>>",
                           lambda e: self.schedule_edited_preview())
        self.drop_loc.bind("<KeyRelease>",
                           lambda e: self.schedule_edited_preview())

        self.txt_notes.bind("<FocusOut>",
                            lambda e: self.schedule_edited_preview())
        self.txt_notes.bind("<Return>",
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

        output_dir = os.path.join(selected, "bordered_output")
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
        self.txt_notes.delete(0, tk.END)
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
                self.txt_notes.insert(0, previous_record["notes"])
            else:
                output_dir = os.path.join(
                    self.input_folder, "bordered_output")
                prior_output = find_prior_processed_output(path, output_dir)
                if prior_output:
                    try:
                        site, notes = read_stamp_fields(prior_output)
                    except (
                            OSError,
                            pytesseract.TesseractNotFoundError,
                            pytesseract.TesseractError) as exc:
                        if not self._ocr_warning_shown:
                            messagebox.showwarning(
                                "Stamp OCR Unavailable",
                                "Could not read text from the previous "
                                f"processed image:\n{prior_output}\n\n{exc}\n\n"
                                "Install the Tesseract OCR engine and ensure "
                                "it is available on PATH to enable OCR recovery.",
                                parent=self.root,
                            )
                            self._ocr_warning_shown = True
                    else:
                        if site:
                            self.drop_loc.set(site)
                        if notes:
                            self.txt_notes.insert(0, notes)

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
        notes_val = self.txt_notes.get().strip()

        ext = os.path.splitext(filename)[1]
        new_filename = build_output_filename(date_file_str, loc_val, ext)
        output_dir = os.path.join(self.input_folder, "bordered_output")
        new_filename = os.path.basename(
            get_unique_output_path(output_dir, new_filename))

        self.lbl_old_fn.config(text=f"Original File: {filename}")
        self.lbl_new_fn.config(text=f"New File Preview: {new_filename}")

        first_stamp_line = " | ".join(
            part for part in (date_label_str, loc_val) if part)

        strip_height = max(24, int(max(img.size) * 0.05))
        full_bordered = add_bottom_stamp_strip(
            img,
            first_stamp_line,
            notes_val,
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

        output_dir = os.path.join(self.input_folder, "bordered_output")
        os.makedirs(output_dir, exist_ok=True)

        ext = os.path.splitext(filename)[1]

        exif_obj, date_file_str, date_label_str = get_exif_data_and_dates(
            input_path)

        loc_val = self.drop_loc.get().strip()
        notes_val = self.txt_notes.get().strip()

        output_name = build_output_filename(date_file_str, loc_val, ext)
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
            part for part in (date_label_str, loc_val) if part)

        strip_height = max(24, int(max(img.size) * 0.05))
        final_img = add_bottom_stamp_strip(
            img,
            first_stamp_line,
            notes_val,
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
            "notes": notes_val,
            "source_name": filename,
            "output_name": output_name,
        }
        history_path = os.path.join(output_dir, PROCESSING_HISTORY_FILE)
        try:
            save_processing_history(history_path, updated_history)
        except (OSError, ValueError) as exc:
            messagebox.showwarning(
                "Processing History Not Saved",
                f"The photo was saved as {output_name}, but its site and notes "
                f"could not be saved to processing history:\n\n{exc}",
            )
        else:
            self.processing_history = updated_history

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
