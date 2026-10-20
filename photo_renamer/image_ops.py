import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont


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


def resize_to_fit(img, max_dimension):
    """Resize an image to fit within a square bound without enlarging it."""
    width, height = img.size
    scale = min(1.0, max_dimension / max(width, height))
    if scale == 1.0:
        return img
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return img.resize(size, Image.Resampling.LANCZOS)


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

def add_bottom_stamp_strip(base_img: Image.Image,
                          first_line: str,
                          second_line: str = "",
                          strip_height: int = 80) -> Image.Image:
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
