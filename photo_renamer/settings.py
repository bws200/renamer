PREVIEW_MAX_DIMENSION = 1200
PREVIEW_DEBOUNCE_MS = 120
SITE_DROPDOWN_MAX_HEIGHT = 20
SITES_FILE = "sites.txt"
PROCESSING_HISTORY_FILE = "processing_history.json"
OUTPUT_FOLDER = "bordered_output"


def load_sites(settings_path):
    """Load site names from a UTF-8 text file, one site per line."""
    with open(settings_path, encoding="utf-8-sig") as settings_file:
        return [
            line.strip()
            for line in settings_file
            if line.strip() and not line.lstrip().startswith("#")
        ]


def get_site_dropdown_height(sites):
    """Show every site when possible, up to the dropdown's 20-row limit."""
    return max(1, min(len(sites), SITE_DROPDOWN_MAX_HEIGHT))
