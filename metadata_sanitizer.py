# file: metadata_sanitizer.py
import os
import re
import logging
import unicodedata
from pathlib import Path
from tempfile import NamedTemporaryFile
from mutagen import File as MutagenFile
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from typing import Optional

# --- CONFIG: whitelist and bad phrases ---
_WHITELIST_RE = re.compile(r'[^A-Za-z0-9\s\-\(\)\.]')
_BAD_PHRASES_RAW = [
    "SongsLover", "SonsHub", "FazMusic", "yt1s",
    "lyric_video", "lyric video", "official music video", "official video", "audio"
]
_BAD_PHRASES = [re.compile(re.escape(p), re.IGNORECASE) for p in _BAD_PHRASES_RAW]
_TRAILING_MIX = re.compile(r'[\s\-_.|]+$')
def whitelist_scrub(text: Optional[str]) -> str:
    """
    Normalize, strip disallowed characters, and remove known bad phrases.
    Returns an empty string for falsy input (preserve distinction from "Unknown").
    """
    if not text:
        return ""
    # Normalize to reduce homoglyphs and combining characters
    s = unicodedata.normalize("NFKC", str(text))
    # Remove disallowed characters
    s = _WHITELIST_RE.sub("", s)
    # Remove bad phrases (case-insensitive)
    for pat in _BAD_PHRASES:
        s = pat.sub("", s)
    return _TRAILING_MIX.sub("", s).strip()

def _atomic_save_audio(audio_obj, target_path: Path):
    """
    Save mutagen audio object atomically: write to temp file then replace.
    """
    # Some mutagen save methods accept a filename; use a temp file and replace.
    with NamedTemporaryFile(delete=False) as tmp:
        tmp_name = tmp.name
    try:
        audio_obj.save(tmp_name)
        os.replace(tmp_name, str(target_path))
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass

def deep_sanitize_metadata(filepath: Path):
    """
    Sanitize metadata for MP3 and MP4/M4A files.
    - Removes comment/subtitle/user frames/atoms.
    - Whitelists core tags (title, artist) using whitelist_scrub.
    - Uses atomic save and robust logging.
    """
    try:
        if not isinstance(filepath, Path):
            filepath = Path(filepath)

        if not filepath.exists():
            logging.warning("File not found: %s", filepath)
            return

        suffix = filepath.suffix.lower()
        audio = MutagenFile(filepath, easy=False)
        if audio is None:
            logging.warning("Unsupported or unrecognized file type: %s", filepath)
            return

        if suffix == ".mp3":
            # Ensure ID3 object
            try:
                id3 = audio if isinstance(audio, ID3) else ID3(filepath)
            except Exception:
                # Try to create an empty ID3 if missing
                id3 = ID3()
                try:
                    id3.save(str(filepath))
                    id3 = ID3(filepath)
                except Exception:
                    logging.exception("Unable to initialize ID3 for %s", filepath)
                    return

            # Purge frames
            for frame in ("TIT3", "COMM", "TXXX"):
                if frame in id3:
                    logging.info("PURGING frame %s from %s", frame, filepath.name)
                    id3.delall(frame)

            # Sanitize core tags safely
            for key in ("TIT2", "TPE1"):
                if key in id3 and getattr(id3[key], "text", None):
                    original = id3[key].text[0]
                    cleaned = whitelist_scrub(original)
                    id3[key].text = [cleaned]

            _atomic_save_audio(id3, filepath)

        elif suffix in (".mp4", ".m4a"):
            tags = audio.tags or {}
            # Purge common comment/description atoms
            for atom in ("\xa9cmt", "\xa9des", "desc"):
                if atom in tags:
                    logging.info("PURGING atom %s from %s", atom, filepath.name)
                    try:
                        del tags[atom]
                    except KeyError:
                        pass

            # Sanitize common name/artist atoms if present
            for atom in ("\xa9nam", "\xa9ART", "©nam", "©ART"):
                if atom in tags and isinstance(tags[atom], list) and tags[atom]:
                    original = tags[atom][0]
                    tags[atom] = [whitelist_scrub(original)]

            _atomic_save_audio(audio, filepath)

        else:
            logging.debug("File suffix not handled by sanitizer: %s", suffix)

    except Exception:
        logging.exception("Failed internal scrub for %s", getattr(filepath, "name", str(filepath)))
        # Re-raise if you want the caller to handle failures; otherwise return.
        raise
