import os
import re
from datetime import datetime
from PIL import Image


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


def build_output_filename(timestamp, site, short_text, extension):
    """Build a filename from the timestamp, site, and short line-one text."""
    parts = [timestamp, sanitize_to_slug(site), sanitize_to_slug(short_text)]
    return "-".join(part for part in parts if part) + extension.lower()
