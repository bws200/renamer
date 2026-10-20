import hashlib
import json
import os
import tempfile


def get_file_fingerprint(file_path):
    """Return a SHA-256 fingerprint for a file's contents."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_processing_history(history_path):
    """Load saved stamp fields indexed by source-file fingerprint."""
    try:
        with open(history_path, encoding="utf-8") as history_file:
            history = json.load(history_file)
    except FileNotFoundError:
        return {}

    if not isinstance(history, dict):
        raise ValueError("Processing history must contain a JSON object.")

    for fingerprint, record in history.items():
        if not isinstance(fingerprint, str) or not isinstance(record, dict):
            raise ValueError("Processing history contains an invalid record.")
        if not all(
                isinstance(record.get(field), str)
                for field in ("site", "notes", "source_name", "output_name")):
            raise ValueError("Processing history contains an incomplete record.")
        short_text = record.setdefault("short_text", "")
        if not isinstance(short_text, str):
            raise ValueError("Processing history contains invalid short text.")

    return history


def save_processing_history(history_path, history):
    """Atomically write processing history so an interrupted save cannot truncate it."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=os.path.dirname(history_path),
                prefix=".processing-history-",
                suffix=".tmp",
                delete=False) as history_file:
            temporary_path = history_file.name
            json.dump(history, history_file, ensure_ascii=False, indent=2)
            history_file.write("\n")
        os.replace(temporary_path, history_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
