# File Photo Renamer

A small desktop app for reviewing and processing image batches. It previews
each image, lets you trim borders and rotate it, adds a stamped black strip
below the image, and saves a processed copy with a descriptive filename.

## Features

- Browse supported images in a selected folder (not recursive).
- Preview the original and processed image side by side.
- Adjust crop percentages independently on all four edges.
- Rotate images in 90-degree increments.
- Choose a site/location and short line-one text for the filename and stamp,
  then enter a longer description for the stamp only.
- Detect dark borders as an initial crop suggestion.
- Debounce editing gestures and render interactive previews at reduced
  resolution for smoother work with large photos.
- Save processed images to a `bordered_output` subfolder without replacing
  existing files.
- Recover site and notes from older processed images using OCR when available.

## Requirements

- Python 3.10 or newer
- Tk support in the Python installation

The app uses Pillow for image handling and NumPy for border detection. On Linux,
you may need to install your distribution's Tk package (often named `python3-tk`).
OCR recovery also uses the `pytesseract` Python package and requires the
Tesseract OCR engine to be installed separately and available on `PATH`.
On Windows, install Tesseract using the installer linked from the
[UB Mannheim Tesseract page](https://github.com/UB-Mannheim/tesseract/wiki), then
open a new terminal and check `tesseract --version`. You can also install it
from Windows Package Manager:

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
tesseract --version
```

If Windows cannot find the command, add the Tesseract installation folder (the
folder containing `tesseract.exe`) to your `PATH`, then restart the app.

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
   `.bmp`, or `.tiff` extensions are listed in filename order. The app does not
   search subfolders, so photos in `bordered_output` are not included when you
   select its parent folder. You can select `bordered_output` itself to edit the
   images inside it.
2. Review the crop suggestion and adjust the sliders or rotation if needed.
3. Choose or type a site/location, enter optional short line-one text, and add
   an optional longer description for the stamp.
4. Choose **Process & Save**. The processed copy is written to
   `bordered_output`; the source image is left unchanged.

   The app stores the chosen site, short text, and description in
   `bordered_output/processing_history.json`, keyed by a SHA-256 fingerprint of
   the original photo. When the same photo is loaded again, those fields are
   restored; unrecognized or changed photos start with blank fields. This
   history is created for photos processed with this feature and does not
   recover metadata from older output files. Older history records remain
   readable; their short-text field is treated as blank.

   If no history match exists, the app uses Tesseract OCR on the selected
   selected photo itself; it does not scan subfolders. Text following a
   timestamp on the same line is treated as the site; if the timestamp is on
   its own line, the next line is treated as the site.
   Additional text after the site on that line becomes the short text;
   remaining lines are combined into the longer description. OCR results can
   be imperfect and should be checked before saving. This fallback requires the separately
   installed Tesseract engine; a warning is shown if it is missing.

   The Location/Site dropdown is populated from `sites.txt` next to `renamer.py`.
   Edit that file with one site per line and restart the app to load your list.
   Blank lines and lines whose first non-space character is `#` are ignored. The
   dropdown remains editable for locations not in the list. It shows all sites
   when there are 20 or fewer; longer lists show 20 at a time and can be scrolled.

Empty folders show a no-images state with processing and navigation disabled.
When the folder queue is exhausted, the app shows **Batch complete**, disables
process/skip, and keeps Previous available so you can revisit an image.

The filename starts with the capture timestamp (`YYYYMMDD-HHMMSS`) when a time
is available, followed by the site/location and optional short text as
lowercase, hyphen-separated slugs. The longer description does not affect the
filename. The first stamp line shows the capture timestamp, site/location, and
short text; the longer description is stamped on following lines.
The border label includes the same timestamp in `YYYY:MM:DD HH:MM:SS` form. If
EXIF provides only a date, only the date is included. The app reads
`DateTimeOriginal` first, then `DateTime`; if neither contains a usable date, it
uses the filesystem timestamp: creation time on Windows and metadata-change
time on many Unix-like systems.

The stamp is rendered in a black strip appended below the image after cropping
and rotation, so it remains at the bottom in every photo orientation. Its first
line shows the capture timestamp, site/location, and optional short text;
following line(s) show the longer description. When both the first line and
description are present, the black strip is twice as tall to give the text more
room. Stamp text wraps to additional centered lines when it would exceed the
photo's width, and the strip grows to fit those lines.

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
