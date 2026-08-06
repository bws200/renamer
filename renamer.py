import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageDraw, ImageFont

# --- 1. CORE IMAGE PROCESSING FUNCTION ---
def add_rotated_borders(image_path, output_path, filename, description, border_width=80):
    with Image.open(image_path) as img:
        new_width = img.width + (border_width * 2)
        new_height = img.height + (border_width * 2)
        
        bordered_img = Image.new("RGB", (new_width, new_height), "black")
        bordered_img.paste(img, (border_width, border_width))
        
        text_content = f"{filename} - {description}"
        draw = ImageDraw.Draw(bordered_img)
        font_size = int(border_width * 0.4)
        
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        # Measure text size
        text_bbox = draw.textbbox((0, 0), text_content, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        # Top Border
        top_x = (new_width - text_w) // 2
        top_y = (border_width - text_h) // 2
        draw.text((top_x, top_y), text_content, fill="white", font=font)

        # Base canvas for rotated text side-rendering
        txt_canvas = Image.new("RGBA", (text_w, text_h + 10), (0, 0, 0, 0))
        txt_draw = ImageDraw.Draw(txt_canvas)
        txt_draw.text((0, 0), text_content, fill="white", font=font)
        
        # Bottom Border (180 deg)
        bottom_txt = txt_canvas.rotate(180, expand=True).convert("RGB")
        bot_x = (new_width - bottom_txt.width) // 2
        bot_y = new_height - border_width + ((border_width - bottom_txt.height) // 2)
        bordered_img.paste(bottom_txt, (bot_x, bot_y))

        # Left Border (90 deg)
        left_txt = txt_canvas.rotate(90, expand=True).convert("RGB")
        left_x = (border_width - left_txt.width) // 2
        left_y = (new_height - left_txt.height) // 2
        bordered_img.paste(left_txt, (left_x, left_y))

        # Right Border (270 deg)
        right_txt = txt_canvas.rotate(270, expand=True).convert("RGB")
        right_x = new_width - border_width + ((border_width - right_txt.width) // 2)
        right_y = (new_height - right_txt.height) // 2
        bordered_img.paste(right_txt, (right_x, right_y))

        bordered_img.save(output_path)

# --- 2. GUI APPLICATION ---
class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Border & Metadata Tool")
        self.root.geometry("500x350")
        
        # Dropdown Option Lists (Customise these categories as needed!)
        self.copyright_options = ["© 2026 Archive Corp", "Public Domain", "All Rights Reserved", "CC BY-NC"]
        self.location_options = ["Headquarters", "Field Site A", "Storage Facility", "External Lab"]
        self.status_options = ["Final", "Draft", "Confidential", "Archival"]

        self.create_widgets()

    def create_widgets(self):
        # Folder Selection
        self.btn_browse = ttk.Button(self.root, text="Select Image Folder", command=self.browse_folder)
        self.btn_browse.pack(pady=15)
        
        self.lbl_folder = ttk.Label(self.root, text="No folder selected", wraplength=400, foreground="gray")
        self.lbl_folder.pack(pady=5)

        # Dropdown 1: Copyright / Owner
        ttk.Label(self.root, text="Select Copyright/Owner:").pack(pady=5)
        self.drop_copy = ttk.Combobox(self.root, values=self.copyright_options, state="readonly", width=40)
        self.drop_copy.set(self.copyright_options[0])
        self.drop_copy.pack()

        # Dropdown 2: Location / Site
        ttk.Label(self.root, text="Select Location/Site:").pack(pady=5)
        self.drop_loc = ttk.Combobox(self.root, values=self.location_options, state="readonly", width=40)
        self.drop_loc.set(self.location_options[0])
        self.drop_loc.pack()

        # Dropdown 3: Status
        ttk.Label(self.root, text="Select Status:").pack(pady=5)
        self.drop_status = ttk.Combobox(self.root, values=self.status_options, state="readonly", width=40)
        self.drop_status.set(self.status_options[0])
        self.drop_status.pack()

        # Process Button
        self.btn_run = ttk.Button(self.root, text="Process Images", command=self.process_images)
        self.btn_run.pack(pady=25)

        self.input_folder = ""

    def browse_folder(self):
        self.input_folder = filedialog.askdirectory()
        if self.input_folder:
            self.lbl_folder.config(text=f"Selected: {self.input_folder}", foreground="black")

    def process_images(self):
        if not self.input_folder:
            messagebox.showerror("Error", "Please select an input folder first.")
            return

        # Combine dropdown selections into a single description string
        combined_description = f"{self.drop_copy.get()} | {self.drop_loc.get()} | {self.drop_status.get()}"
        
        output_folder = os.path.join(self.input_folder, "bordered_output")
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
        files = [f for f in os.listdir(self.input_folder) if f.lower().endswith(valid_extensions)]

        if not files:
            messagebox.showinfo("No Images", "No valid images found in the selected folder.")
            return

        for file in files:
            in_path = os.path.join(self.input_folder, file)
            out_path = os.path.join(output_folder, f"bordered_{file}")
            filename_slug = os.path.splitext(file)[0]
            
            add_rotated_borders(in_path, out_path, filename_slug, combined_description)

        messagebox.showinfo("Success", f"Processed {len(files)} images successfully!\nSaved to 'bordered_output' folder.")

# Run the app
if __name__ == "__main__":
    root = tk.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()
