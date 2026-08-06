import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageDraw, ImageFont, ImageTk

# --- 1. CORE IMAGE PROCESSING FUNCTION ---
def add_rotated_borders(image_path, output_path, filename, description, border_width=80):
    with Image.open(image_path) as img:
        new_width = img.width + (border_width * 2)
        new_height = img.height + (border_width * 2)
        
        bordered_img = Image.new("RGB", (new_width, new_height), "black")
        bordered_img.paste(img, (border_width, border_width))
        
        # Format text depending on whether a description was provided
        if description:
            text_content = f"{filename} - {description}"
        else:
            text_content = filename
            
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
        self.root.title("Interactive Image Border & Metadata Tool")
        self.root.geometry("950x600") # Tweaked size slightly for text entry comfort
        
        self.input_folder = ""
        self.files = []
        self.current_index = 0
        self.tk_preview_img = None
        
        # Updated lists with an explicit blank option ("") at the front
        self.copyright_options = ["", "© 2026 Archive Corp", "Public Domain", "All Rights Reserved", "CC BY-NC"]
        self.location_options = ["", "Headquarters", "Field Site A", "Storage Facility", "External Lab"]
        self.status_options = ["", "Final", "Draft", "Confidential", "Archival"]

        self.create_layout()

    def create_layout(self):
        # Left Panel (Inputs)
        self.left_panel = ttk.Frame(self.root, padding=15, width=380)
        self.left_panel.pack(side="left", fill="y")
        self.left_panel.pack_propagate(False)
        
        # Right Panel (Preview)
        self.right_panel = ttk.Frame(self.root, padding=15)
        self.right_panel.pack(side="right", expand=True, fill="both")

        # --- LEFT PANEL COMPONENTS ---
        self.btn_browse = ttk.Button(self.left_panel, text="Select Image Folder", command=self.browse_folder)
        self.btn_browse.pack(pady=(0, 10), fill="x")
        
        self.lbl_folder = ttk.Label(self.left_panel, text="No folder selected", wraplength=340, foreground="gray")
        self.lbl_folder.pack(pady=(0, 15))

        # Dropdowns (State changed from "readonly" to "normal" so users can clear text or type custom info)
        ttk.Label(self.left_panel, text="Select Copyright/Owner:").pack(anchor="w", pady=2)
        self.drop_copy = ttk.Combobox(self.left_panel, values=self.copyright_options, state="normal")
        self.drop_copy.set(self.copyright_options[1]) # Default to the first actual text option
        self.drop_copy.pack(fill="x", pady=(0, 12))

        ttk.Label(self.left_panel, text="Select Location/Site:").pack(anchor="w", pady=2)
        self.drop_loc = ttk.Combobox(self.left_panel, values=self.location_options, state="normal")
        self.drop_loc.set(self.location_options[1])
        self.drop_loc.pack(fill="x", pady=(0, 12))

        ttk.Label(self.left_panel, text="Select Status:").pack(anchor="w", pady=2)
        self.drop_status = ttk.Combobox(self.left_panel, values=self.status_options, state="normal")
        self.drop_status.set(self.status_options[1])
        self.drop_status.pack(fill="x", pady=(0, 12))

        # NEW: Free Text Section
        ttk.Label(self.left_panel, text="Custom Notes / Free Text:").pack(anchor="w", pady=2)
        self.txt_notes = ttk.Entry(self.left_panel)
        self.txt_notes.pack(fill="x", pady=(0, 25))

        # Workflow Control Buttons
        self.btn_process = tk.Button(self.left_panel, text="Process & Next", bg="#2ecc71", fg="white", 
                                     font=("Arial", 11, "bold"), command=self.process_current, state="disabled")
        self.btn_process.pack(fill="x", pady=5)
        
        self.btn_skip = tk.Button(self.left_panel, text="Skip Image", bg="#95a5a6", fg="white", 
                                  font=("Arial", 11), command=self.skip_current, state="disabled")
        self.btn_skip.pack(fill="x", pady=5)

        # --- RIGHT PANEL COMPONENTS ---
        self.lbl_counter = ttk.Label(self.right_panel, text="Please load a folder to preview files", font=("Arial", 11, "bold"))
        self.lbl_counter.pack(pady=(0, 5))
        
        self.lbl_filename = ttk.Label(self.right_panel, text="", font=("Arial", 9, "italic"), wraplength=500)
        self.lbl_filename.pack(pady=(0, 10))

        self.preview_canvas = tk.Label(self.right_panel, bg="#eaeaea", relief="sunken", borderwidth=1)
        self.preview_canvas.pack(expand=True, fill="both")

    def browse_folder(self):
        selected = filedialog.askdirectory()
        if not selected:
            return
            
        self.input_folder = selected
        self.lbl_folder.config(text=f"Folder: {self.input_folder}", foreground="black")
        
        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
        self.files = [f for f in os.listdir(self.input_folder) if f.lower().endswith(valid_extensions)]
        
        if not self.files:
            messagebox.showinfo("No Images", "No valid images found in the selected folder.")
            self.btn_process.config(state="disabled")
            self.btn_skip.config(state="disabled")
            return
            
        self.current_index = 0
        self.btn_process.config(state="normal")
        self.btn_skip.config(state="normal")
        
        self.load_current_image_preview()

    def load_current_image_preview(self):
        if self.current_index >= len(self.files):
            messagebox.showinfo("Done", "All target folder images have been reviewed.")
            self.lbl_counter.config(text="Review Complete!")
            self.lbl_filename.config(text="")
            self.preview_canvas.config(image="")
            self.btn_process.config(state="disabled")
            self.btn_skip.config(state="disabled")
            return

        filename = self.files[self.current_index]
        self.lbl_counter.config(text=f"Reviewing Image {self.current_index + 1} of {len(self.files)}")
        self.lbl_filename.config(text=filename)

        full_path = os.path.join(self.input_folder, filename)
        try:
            with Image.open(full_path) as img:
                img.thumbnail((520, 420))
                self.tk_preview_img = ImageTk.PhotoImage(img)
                self.preview_canvas.config(image=self.tk_preview_img)
        except Exception as e:
            self.preview_canvas.config(image="")
            messagebox.showerror("Preview Error", f"Could not preview {filename}\nError: {e}")

    def process_current(self):
        current_file = self.files[self.current_index]
        in_path = os.path.join(self.input_folder, current_file)
        
        output_folder = os.path.join(self.input_folder, "bordered_output")
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            
        out_path = os.path.join(output_folder, f"bordered_{current_file}")
        filename_slug = os.path.splitext(current_file)[0]
        
        # Collect values and filter out empty strings
        metadata_pieces = [
            self.drop_copy.get().strip(),
            self.drop_loc.get().strip(),
            self.drop_status.get().strip(),
            self.txt_notes.get().strip()
        ]
        
        # Join only the non-empty fields using the | symbol
        valid_pieces = [piece for piece in metadata_pieces if piece]
        combined_description = " | ".join(valid_pieces)
        
        # Process image
        add_rotated_borders(in_path, out_path, filename_slug, combined_description)
        
        # Clear the free-text entry box for the next photo (optional workflow choice)
        self.txt_notes.delete(0, tk.END)
        
        # Step forward
        self.current_index += 1
        self.load_current_image_preview()

    def skip_current(self):
        # Clear the free-text field on skip too so old entries don't roll over accidentally
        self.txt_notes.delete(0, tk.END)
