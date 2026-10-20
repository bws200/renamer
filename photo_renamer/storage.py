import os

def get_unique_output_path(output_dir, output_name):
    """Return an unused output path by appending a number before the extension."""
    stem, extension = os.path.splitext(output_name)
    candidate = os.path.join(output_dir, output_name)
    suffix = 2
    while os.path.exists(candidate):
        candidate = os.path.join(output_dir, f"{stem}-{suffix}{extension}")
        suffix += 1
    return candidate

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
