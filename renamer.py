import os
import re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageDraw, ImageFont, ImageTk
from PIL.ExifTags import TAGS


def get_date_taken(image_path):
    """Extracts EXIF Date (YYYYMMDD). Falls back to system file creation date."""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif:
                for tag_id, value in exif.items():
                    if TAGS.get(tag_id) in ("DateTimeOriginal", "DateTime"):
                        date_str = value.split()[0].replace(":", "")
                        if len(date_str) == 8 and date_str.isdigit():
                            return date_str
    except Exception:
        pass
    try:
        timestamp = os.path.getctime(image_path)
        return datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
    except Exception:
        return datetime.now().strftime("%Y%m%d")


def sanitize_to_slug(text):
    """Cleans text into alphanumeric hyphenated segments."""
    if not text: return ""
    text = text.replace("©", "").strip()
    slug = re.sub(r'[\s\-_:\|\.\,\/\\]+', '-', text)
    return slug.strip('-')


def add_rotated_borders(image_path,
                        output_path,
                        dynamic_label,
                        border_width=80):
    with Image.open(image_path) as img:
        new_w, new_h = img.width + (border_width *
                                    2), img.height + (border_width * 2)
        bordered_img = Image.new("RGB", (new_w, new_h), "black")
        bordered_img.paste(img, (border_width, border_width))

        draw = ImageDraw.Draw(bordered_img)
        font_size = int(border_width * 0.4)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        # Measure text dimensions
        bbox = draw.textbbox((0, 0), dynamic_label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Top
        draw.text(((new_w - tw) // 2, (border_width - th) // 2),
                  dynamic_label,
                  fill="white",
                  font=font)

        # Base for rotated canvas text
        canvas = Image.new("RGBA", (tw, th + 10), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((0, 0),
                                    dynamic_label,
                                    fill="white",
                                    font=font)

        # Bottom (180)
        bot_txt = canvas.rotate(180, expand=True).convert("RGB")
        bordered_img.paste(
            bot_txt, ((new_w - bot_txt.width) // 2, new_h - border_width +
                      ((border_width - bot_txt.height) // 2)))

        # Left (90)
        l_txt = canvas.rotate(90, expand=True).convert("RGB")
        bordered_img.paste(l_txt, (((border_width - l_txt.width) // 2),
                                   (new_h - l_txt.height) // 2))

        # Right (270)
        r_txt = canvas.rotate(270, expand=True).convert("RGB")
        bordered_img.paste(
            r_txt, (new_w - border_width + ((border_width - r_txt.width) // 2),
                    (new_h - r_txt.height) // 2))

        bordered_img.save(output_path)


class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Custom Metadata Stamping Tool")
        self.root.geometry("980x620")

        self.input_folder, self.files, self.current_index, self.tk_preview_img = "", [], 0, None
        self.opts = [
            "", "© 2026 Archive Corp", "Public Domain", "All Rights Reserved",
            "CC BY-NC"
        ]
        self.locs = [
            "", "Headquarters", "Field Site A", "Storage Facility",
            "External Lab"
        ]
        self.stats = ["", "Final", "Draft", "Confidential", "Archival"]
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
        self.lbl_folder = ttk.Label(self.left,
                                    text="No folder selected",
                                    wraplength=330,
                                    foreground="gray")
        self.lbl_folder.pack(pady=(0, 15))

        ttk.Label(self.left, text="Select Copyright/Owner:").pack(anchor="w")
        self.drop_copy = ttk.Combobox(self.left,
                                      values=self.opts,
                                      state="normal")
        self.drop_copy.pack(fill="x", pady=(0, 12))

        ttk.Label(self.left, text="Select Location/Site:").pack(anchor="w")
        self.drop_loc = ttk.Combobox(self.left,
                                     values=self.locs,
                                     state="normal")
        self.drop_loc.pack(fill="x", pady=(0, 12))

        ttk.Label(self.left, text="Select Status:").pack(anchor="w")
        self.drop_status = ttk.Combobox(self.left,
                                        values=self.stats,
                                        state="normal")
        self.drop_status.pack(fill="x", pady=(0, 12))

        ttk.Label(self.left, text="Custom Notes / Free Text:").pack(anchor="w")
        self.txt_notes = ttk.Entry(self.left)
        self.txt_notes.pack(fill="x", pady=(0, 25))

        self.btn_process = tk.Button(self.left,
                                     text="Process & Next",
                                     bg="#2ecc71",
                                     fg="white",
                                     font=("Arial", 11, "bold"),
                                     command=self.process_current,
                                     state="disabled")
        self.btn_process.pack(fill="x", pady=5)

        self.btn_skip = tk.Button(self.left,
                                  text="Skip Image",
                                  bg="#95a5a6",
                                  fg="white",
                                  font=("Arial", 11),
                                  command=self.skip_current,
                                  state="disabled")
        self.btn_skip.pack(fill="x", pady=5)

        self.lbl_cnt = ttk.Label(self.right,
                                 text="Load a folder to run step previews",
                                 font=("Arial", 11, "bold"))
        self.lbl_cnt.pack(pady=(0, 5))
        self.lbl_fn = ttk.Label(self.right,
                                text="",
                                font=("Arial", 9, "italic"),
                                wraplength=500)
        self.lbl_fn.pack(pady=(0, 10))
        self.canvas = tk.Label(self.right,
                               bg="#eaeaea",
                               relief="sunken",
                               borderwidth=1)
        self.canvas.pack(expand=True, fill="both")

    def browse_folder(self):
        selected = filedialog.askdirectory()
        if not selected: return
        self.input_folder = selected
        self.lbl_folder.config(text=f"Folder: {self.input_folder}",
                               foreground="black")

        exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
        self.files = [
            f for f in os.listdir(self.input_folder)
            if f.lower().endswith(exts)
        ]
        if not self.files:
            messagebox.showinfo("No Images", "No valid images found.")
            return
        self.current_index = 0
        self.btn_process.config(state="normal")
        self.btn_skip.config(state="normal")
        self.load_preview()

    def load_preview(self):
        if self.current_index >= len(self.files):
            messagebox.showinfo("Done", "All images reviewed.")
            self.lbl_cnt.config(text="Review Complete!")
            self.lbl_fn.config(text="")
            self.canvas.config(image="")
            self.btn_process.config(state="disabled")
            self.btn_skip.config(state="disabled")
            return

        filename = self.files[self.current_index]
        self.lbl_cnt.config(
            text=f"Image {self.current_index + 1} of {len(self.files)}")
        self.lbl_fn.config(text=filename)

        try:
            with Image.open(os.path.join(self.input_folder, filename)) as img:
                img.thumbnail((540, 440))
                self.tk_preview_img = ImageTk.PhotoImage(img)
                self.canvas.config(image=self.tk_preview_img)
        except Exception as e:
            self.canvas.config(image="")
            messagebox.showerror("Error", f"Failed to preview {filename}: {e}")

    def process_current(self):
        cur_file = self.files[self.current_index]
        in_p = os.path.join(self.input_folder, cur_file)
        out_dir = os.path.join(self.input_folder, "bordered_output")
        os.makedirs(out_dir, exist_ok=True)

        slugs = [
            get_date_taken(in_p),
            sanitize_to_slug(self.drop_copy.get()),
            sanitize_to_slug(self.drop_loc.get()),
            sanitize_to_slug(self.drop_status.get()),
            sanitize_to_slug(self.txt_notes.get())
        ]
        label = "-".join([s for s in slugs if s])
        add_rotated_borders(in_p, os.path.join(out_dir,
                                               f"bordered_{cur_file}"), label)

        self.txt_notes.delete(0, tk.END)
        self.current_index += 1
        self.load_preview()

    def skip_current(self):
        self.txt_notes.delete(0, tk.END)
        self.current_index += 1
        self.load_preview()


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()
