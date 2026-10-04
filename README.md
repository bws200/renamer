# File Photo Renamer

A small desktop app for reviewing and processing image batches. It previews
each image, lets you trim borders and rotate it, adds a metadata text border,
and saves a processed copy with a descriptive filename.

## Features

- Browse supported images in a selected folder (not recursive).
- Preview the original and processed image side by side.
- Adjust crop percentages independently on all four edges.
- Rotate images in 90-degree increments.
- Add copyright/owner, location, status, and notes to the border and filename.
- Detect dark borders as an initial crop suggestion.
- Debounce editing gestures and render interactive previews at reduced
  resolution for smoother work with large photos.
- Save processed images to a `bordered_output` subfolder without replacing
  existing files.

## Requirements

- Python 3.10 or newer
- Tk support in the Python installation

The app uses Pillow for image handling and NumPy for border detection. On Linux,
you may need to install your distribution's Tk package (often named `python3-tk`).

## Install and run

```powershell
git clone <repository-url>
cd file-photo-renamer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python renamer.py
```

On macOS or Linux, activate the environment with:

```sh
source .venv/bin/activate
```

Then install requirements and run `python renamer.py` as above.

## Workflow and file behavior

1. Select a folder. Images directly in that folder with `.jpg`, `.jpeg`, `.png`,
   `.bmp`, or `.tiff` extensions are listed in filename order.
2. Review the crop suggestion and adjust the sliders or rotation if needed.
3. Enter any metadata to include in the border and output filename.
4. Choose **Process & Save**. The processed copy is written to
   `bordered_output`; the source image is left unchanged. Right Arrow skips,
   Left Arrow goes back, and Space processes the current image when a text
   field is not focused.

Empty folders show a no-images state with processing and navigation disabled.
When the folder queue is exhausted, the app shows **Batch complete**, disables
process/skip, and keeps Previous available so you can revisit an image.

The filename starts with the capture date (`YYYYMMDD`) when available, followed
by non-empty metadata fields as lowercase, hyphen-separated slugs. If the image
has no usable EXIF date, the app uses the filesystem timestamp: creation time
on Windows and metadata-change time on many Unix-like systems.

If a destination name already exists, the app adds a numeric suffix such as
`-2` before the extension. It also opens the destination in exclusive-create
mode, so a file that appears after the confirmation prompt is never silently
overwritten.

Interactive previews are capped at 1200 pixels on their longest edge and
updates are debounced while you adjust controls. Saved output is still rendered
from the full-resolution source image.

Supported source extensions are `.jpg`, `.jpeg`, `.png`, `.bmp`, and `.tiff`.
The output keeps the source extension. The processed pixels are
converted to RGB. EXIF data is re-emitted for JPEG and TIFF output with the
orientation tag reset to match the rendered pixels; other metadata (including
ICC and XMP profiles) is not explicitly copied. PNG and BMP output do not have
EXIF explicitly written by this app.

## Tests

Run the standard-library test suite from the repository root:

```sh
python -m unittest discover -s tests -v
```

GitHub Actions runs this suite on Windows and Ubuntu with Python 3.10 and 3.14.
