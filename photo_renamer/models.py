from dataclasses import dataclass


@dataclass(frozen=True)
class StampFields:
    site: str = ""
    short_text: str = ""
    description: str = ""
