import re

import numpy as np
import pytesseract
from PIL import Image, ImageOps

from .models import StampFields


def parse_stamp_text(ocr_text) -> StampFields:
    """Interpret OCR output as timestamp/site/short text and description."""
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in ocr_text.splitlines()
    ]
    lines = [line for line in lines if line]
    if not lines:
        return StampFields()

    timestamp_match = re.match(
        r"^\d{4}:\d{2}:\d{2}(?:\s+\d{2}:\d{2}:\d{2})?"
        r"\s*(?:\|\s*)?(.*)$",
        lines[0],
    )
    if not timestamp_match:
        return StampFields()

    line_one = timestamp_match.group(1).strip(" |")
    following_lines = lines[1:]
    if not line_one and following_lines:
        line_one = following_lines.pop(0)

    line_one_parts = [part.strip() for part in line_one.split("|")]
    line_one_parts = [part for part in line_one_parts if part]
    site = line_one_parts[0] if line_one_parts else ""
    short_text = " ".join(line_one_parts[1:])
    description = " ".join(following_lines)
    return StampFields(site, short_text, description)


def read_stamp_fields(image_path) -> StampFields:
    """OCR timestamp, site, short text, and description from the image banner."""
    with Image.open(image_path) as source_image:
        image = ImageOps.exif_transpose(source_image).convert("L")
        width, height = image.size
        pixels = np.asarray(image)
        top = height
        for row in range(height - 1, max(-1, height - height // 3 - 1), -1):
            dark_ratio = np.count_nonzero(pixels[row] < 70) / width
            if dark_ratio < 0.5:
                break
            top = row

        if top == height:
            return StampFields()

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
