import os
import re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from PIL import Image, ImageDraw, ImageFont, ImageTk
from PIL.ExifTags import TAGS


def get_date_taken(image_path):
    """Extract EXIF date (YYYYMMDD), falling back to file creation date."""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()

            if exif:
                for tag_id, value in exif.items():
                    if TAGS.get(tag_id) in ("DateTimeOriginal", "DateTime"):
                        date_clean = str(value).split()[0].replace(":", "")

                        if len(date_clean) == 8 and date_clean.isdigit():
                            return date_clean

    except Exception:
        pass

    try:
        timestamp = os.path.getctime(image_path)
        return datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
    except Exception:
        return datetime.now().strftime("%Y%m%d")


def sanitize_to_slug(text):
    """Convert text into a clean filename-safe slug."""
    if not text:
        return ""

    text = text.replace("©", "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def create_bordered_preview(base_img, border_text, border_width=40):
    """Generate preview image with border text."""
    preview_img = base_img.copy()
    preview_img.thumbnail((300, 300))

    new_w = preview_img.width + (border_width * 2)
    new_h = preview_img.height + (border_width * 2)

    mockup = Image.new("RGB", (new_w, new_h), "black")
    mockup.paste(preview_img, (border_width, border_width))

    draw = ImageDraw.Draw(mockup)
    font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), border_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    draw.text(
        ((new_w - tw) // 2, (border_width - th) // 2),
        border_text,
        fill="white",
        font=font,
    )

    return mockup


def add_rotated_borders(base_img, output_path, border_text, border_width=80):
    """Save image with text added to all four borders."""
    new_w = base_img.width + (border_width * 2)
    new_h = base_img.height + (border_width * 2)

    bordered_img = Image.new("RGB", (new_w, new_h), "black")
    bordered_img.paste(base_img, (border_width, border_width))

    draw = ImageDraw.Draw(bordered_img)

    font_size = int(border_width * 0.4)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), border_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    draw.text(
        ((new_w - tw) // 2, (border_width - th) // 2),
        border_text,
        fill="white",
        font=font,
    )

    canvas = Image.new("RGBA", (tw, th + 10), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text(
        (0, 0),
        border_text,
        fill="white",
        font=font,
    )

    bottom = canvas.rotate(180, expand=True).convert("RGB")
    left = canvas.rotate(90, expand=True).convert("RGB")
    right = canvas.rotate(270, expand=True).convert("RGB")

    bordered_img.paste(
        bottom,
        (
            (new_w - bottom.width) // 2,
            new_h - border_width + ((border_width - bottom.height) // 2),
        ),
    )

    bordered_img.paste(
        left,
        (
            (border_width - left.width) // 2,
            (new_h - left.height) // 2,
        ),
    )

    bordered_img.paste(
        right,
        (
            new_w - border_width + ((border_width - right.width) // 2),
            (new_h - right.height) // 2,
        ),
    )

    bordered_img.save(output_path)


class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Dual-Preview Photo Workflow Tool")
        self.root.geometry("1200x650")

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

        self.stats = [
            "",
            "Final",
            "Draft",
            "Confidential",
            "Archival",
        ]

        self.create_layout()
        self.bind_hotkeys()

    def create_layout(self):
        self.left = ttk.Frame(self.root, padding=15, width=340)
        self.left.pack(side="left", fill="y")
        self.left.pack_propagate(False)

        self.right = ttk.Frame(self.root, padding=15)
        self.right.pack(side="right", expand=True, fill="both")

        ttk.Button(
            self.left,
            text="Select Image Folder",
            command=self.browse_folder,
        ).pack(fill="x", pady=(0, 10))

        self.lbl_folder = ttk.Label(
            self.left,
            text="No folder selected",
            wraplength=310,
            foreground="gray",
        )
        self.lbl_folder.pack(pady=(0, 15))

        ttk.Label(self.left, text="Copyright / Owner").pack(anchor="w")
        self.drop_copy = ttk.Combobox(self.left, values=self.opts)
        self.drop_copy.pack(fill="x", pady=(0, 10))

        ttk.Label(self.left, text="Location / Site").pack(anchor="w")
        self.drop_loc = ttk.Combobox(self.left, values=self.locs)
        self.drop_loc.pack(fill="x", pady=(0, 10))

        ttk.Label(self.left, text="Status").pack(anchor="w")
        self.drop_status = ttk.Combobox(self.left, values=self.stats)
        self.drop_status.pack(fill="x", pady=(0, 10))

        ttk.Label(self.left, text="Notes").pack(anchor="w")
        self.txt_notes = ttk.Entry(self.left)
        self.txt_notes.pack(fill="x", pady=(0, 15))

        for widget in (
                self.drop_copy,
                self.drop_loc,
                self.drop_status,
        ):
            widget.bind(
                "<<ComboboxSelected>>",
                lambda e: self.update_edited_mockup(),
            )
            widget.bind(
                "<KeyRelease>",
                lambda e: self.update_edited_mockup(),
            )

        self.txt_notes.bind(
            "<KeyRelease>",
            lambda e: self.update_edited_mockup(),
        )

        ttk.Label(
            self.left,
            text="Rotate Image Orientation:",
        ).pack(anchor="w", pady=(5, 2))

        rot_frame = ttk.Frame(self.left)
        rot_frame.pack(fill="x", pady=(0, 20))

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
            text="Process & Next (Space)",
            command=self.process_current,
            bg="#2ecc71",
            fg="white",
            font=("Arial", 11, "bold"),
            state="disabled",
        )
        self.btn_process.pack(fill="x", pady=4)

        self.btn_back = tk.Button(
            self.left,
            text="Previous Image (Left)",
            command=self.prev_current,
            bg="#34495e",
            fg="white",
            font=("Arial", 11),
            state="disabled",
        )
        self.btn_back.pack(fill="x", pady=4)

        self.btn_skip = tk.Button(
            self.left,
            text="Skip Image (Right)",
            command=self.skip_current,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 11),
            state="disabled",
        )
        self.btn_skip.pack(fill="x", pady=4)

        self.lbl_cnt = ttk.Label(
            self.right,
            text="Load a folder to run previews",
            font=("Arial", 12, "bold"),
        )
        self.lbl_cnt.pack()

        self.lbl_fn = ttk.Label(
            self.right,
            text="",
            font=("Arial", 9, "italic"),
        )
        self.lbl_fn.pack(pady=(0, 10))

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

    def browse_folder(self):
        selected = filedialog.askdirectory()

        if not selected:
            return

        self.input_folder = selected

        self.lbl_folder.config(
            text=f"Folder: {selected}",
            foreground="black",
        )

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
        if not self.files:
            return

        if self.current_index >= len(self.files):
            messagebox.showinfo("Done", "All images reviewed.")

            self.lbl_cnt.config(text="Review Complete!")
            self.lbl_fn.config(text="")

            self.canvas_orig.config(image="")
            self.canvas_edit.config(image="")

            self.btn_process.config(state="disabled")
            self.btn_skip.config(state="disabled")

            return

        self.rotation_angle = 0

        filename = self.files[self.current_index]

        self.lbl_cnt.config(
            text=f"Image {self.current_index + 1} of {len(self.files)}")
        self.lbl_fn.config(text=filename)

        try:
            path = os.path.join(self.input_folder, filename)

            self.current_pil_img = Image.open(path)

            thumb = self.current_pil_img.copy()
            thumb.thumbnail((340, 340))

            self.tk_orig_img = ImageTk.PhotoImage(thumb)
            self.canvas_orig.config(image=self.tk_orig_img)

            self.update_edited_mockup()

        except Exception as exc:
            messagebox.showerror(
                "Error",
                f"Failed to preview {filename}\n\n{exc}",
            )

    def rotate_image(self, angle):
        if self.current_pil_img is None:
            return

        self.rotation_angle = (self.rotation_angle + angle) % 360
        self.update_edited_mockup()

    def get_current_working_image(self):
        if self.current_pil_img is None:
            return None

        if self.rotation_angle:
            return self.current_pil_img.rotate(
                self.rotation_angle,
                expand=True,
            )

        return self.current_pil_img.copy()

    def update_edited_mockup(self):
        img = self.get_current_working_image()

        if img is None:
            return

        filename = self.files[self.current_index]
        stem = os.path.splitext(filename)[0]

        parts = [
            stem,
            self.drop_copy.get().strip(),
            self.drop_loc.get().strip(),
            self.drop_status.get().strip(),
            self.txt_notes.get().strip(),
        ]

        border_text = " | ".join(p for p in parts if p)

        preview = create_bordered_preview(img, border_text)
        preview.thumbnail((340, 340))

        self.tk_edit_img = ImageTk.PhotoImage(preview)
        self.canvas_edit.config(image=self.tk_edit_img)

    def process_current_event(self, event):
        if (self.btn_process["state"] == "normal"
                and self.root.focus_get() != self.txt_notes):
            self.process_current()

    def process_current(self):
        if self.current_index >= len(self.files):
            return

        filename = self.files[self.current_index]

        input_path = os.path.join(self.input_folder, filename)

        output_dir = os.path.join(
            self.input_folder,
            "bordered_output",
        )
        os.makedirs(output_dir, exist_ok=True)

        ext = os.path.splitext(filename)[1]
        stem = os.path.splitext(filename)[0]

        date_taken = get_date_taken(input_path)

        copy_val = self.drop_copy.get().strip()
        loc_val = self.drop_loc.get().strip()
        status_val = self.drop_status.get().strip()
        notes_val = self.txt_notes.get().strip()

        border_text = " | ".join(x for x in [
            stem,
            copy_val,
            loc_val,
            status_val,
            notes_val,
        ] if x)

        filename_parts = [
            date_taken,
            sanitize_to_slug(copy_val),
            sanitize_to_slug(loc_val),
            sanitize_to_slug(status_val),
            sanitize_to_slug(notes_val),
        ]

        output_name = ("-".join(part for part in filename_parts if part) +
                       ext.lower())

        output_path = os.path.join(output_dir, output_name)

        final_img = self.get_current_working_image()

        add_rotated_borders(
            final_img,
            output_path,
            border_text,
        )

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
