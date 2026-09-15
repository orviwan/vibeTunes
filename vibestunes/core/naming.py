import re

def clean_fat32_name(name: str) -> str:
    """Sanitizes strings for FAT32 filesystems on iPods."""
    name = re.sub(r"[:]", " - ", name)
    name = re.sub(r"[\"\*\/\<\>\?\\\|]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "Unknown"
