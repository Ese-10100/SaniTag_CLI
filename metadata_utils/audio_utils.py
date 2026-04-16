# metadata_utils/audio_utils.py
import os
import logging
import re
from dotenv import load_dotenv
from pathlib import Path
from mutagen import File as MutagenFile

logging.basicConfig(level=logging.INFO)
load_dotenv()

def view_audio_file(file_path: Path):
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    #Ensure that it's a legit/supported audio file
    if not file_path.is_file() or suffix not in ['.mp3', '.m4a']:
        logging.warning(f"{suffix} is not a supported audio format or the file is not valid: {file_path}")
        return None
    audio = MutagenFile(file_path, easy=False)

    if audio and audio.tags:
        if suffix == '.m4a':
            logging.info(f"[TAGS] Metadata read directly for {file_path.name}")
            title = audio.tags.get("©nam", ["Unknown Title"])[0]
            artist = audio.tags.get("©ART", ["Unknown Artist"])[0]
            album = audio.tags.get("©alb", ["Unknown Album"])[0]
            year = audio.tags.get("©day", ["Unknown Year"])[0]
            genre = audio.tags.get("©gen", ["Unknown Genre"])[0]
            tracknumber = audio.tags.get("trkn", ["Unknown Track Number"])[0]
        elif suffix == '.mp3':
            logging.info(f"[TAGS] Metadata read directly for {file_path.name}")
            title = str(audio.tags.get("TIT2", ["Unknown Title"])[0]) if "TIT2" in audio.tags else "Unknown Title"
            artist = str(audio.tags.get("TPE1", ["Unknown Artist"])[0]) if "TPE1" in audio.tags else "Unknown Artist"
            album = str(audio.tags.get("TALB", ["Unknown Album"])[0]) if "TALB" in audio.tags else "Unknown Album"
            year = str(audio.tags.get("TYER", ["Unknown Year"])[0]) if "TYER" in audio.tags else "Unknown Year"
            genre = str(audio.tags.get("TCON", ["Unknown Genre"])[0]) if "TCON" in audio.tags else "Unknown Genre"
            tracknumber = str(audio.tags.get("TRCK", ["Unknown Track Number"])[0]) if "TRCK" in audio.tags else "Unknown Track Number"
    else:
        # Fallback to filename parsing
        stem = re.sub(r'^\d{1,4}\s*-\s*', '', file_path.stem)  # strip leading track number
        parts = stem.split(" - ")
        if len(parts) == 2:
            artist, title = parts
            logging.info(f"[FALLBACK] Parsed artist/title from filename for {Path(file_path).name}")
        else:
            title = Path(file_path).stem
            artist = "Unknown Artist"
            logging.info(f"[FALLBACK] Using filename stem as title for {Path(file_path).name}")
        album, year, genre, tracknumber = (
            "Unknown Album", "Unknown Year", "Unknown Genre", "Unknown Track Number"
        )

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "year": year,
        "genre": genre,
        "tracknumber": tracknumber
    }

# Safe frame whitelist for MP3s
FRAME_MAP = {
    "TIT2": "title",       # Title/song name
    "TPE1": "artist",      # Lead performer
    "TALB": "album",       # Album name
    "APIC": "cover art",   # Cover art
    "TRCK": "track number",
    "TYER": "year",
    "USLT": "lyrics"       # Keep embedded lyrics
}

def extract_basic_tags(audio):# mp3 use case
    """
    Extracts basic metadata tags (title, artist, album, etc.) from a Mutagen audio file object.
    """
    tags = {}
    if audio and audio.tags:
        for frame, label in FRAME_MAP.items():
            if frame in audio.tags:
                value = audio.tags[frame]
                if isinstance(value, list):
                    tags[label] = str(value[0])
                else:
                    tags[label] = str(value)
    return tags

""" Normalize audio tag keys to strings.
    Mutagen's MP4/M4A tags occasionally expose atom keys as bytes; this helper
    safely decodes them to UTF-8 strings (falling back to str() if decoding fails).
    Values are preserved unchanged.
"""

def decode_audio_tags(tags):
    """Normalize tag keys to strings, decoding bytes if necessary."""

    if not tags:
        return{}
    normalized_tags = {}
    for p, q in (tags or {}).items():
        if p and isinstance(p,bytes):
            try:
                p = p.decode("utf-8", errors = "ignore") 
            except Exception: #Ensure that it falls back to the original string if decoding breaks
                p = str(p)
        normalized_tags[p] = q
    return normalized_tags