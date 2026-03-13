# file: metadata_sanitizer.py
import os
import re
import logging
import unicodedata
from pathlib import Path
from tempfile import NamedTemporaryFile
from mutagen import File as MutagenFile
from mutagen.id3 import ID3
from typing import Optional

# --- CONFIG: whitelist and bad phrases ---
_BAD_PHRASES_RAW = [
    "SongsLover.com", "SonsHub", "FazMusic", "yt1s",
    "lyric_video", "lyric video", "official music video",
    "official video", "audio", "www.SongsLover.pk"
]
_BAD_PHRASES_REGEX = [r"\.com", r"\.pk"]
_BAD_PHRASES = [re.compile(re.escape(p), re.IGNORECASE) for p in _BAD_PHRASES_RAW] + \
               [re.compile(p, re.IGNORECASE) for p in _BAD_PHRASES_REGEX]
_TRAILING_MIX = re.compile(r'[\s\-_.|]+$')

def whitelist_scrub(text: Optional[str]) -> str:
    """
    Normalize, strip disallowed characters, and remove known bad phrases.
    Returns an empty string for falsy input (preserve distinction from "Unknown").
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    allowed = []
    for char in s:
        cat = unicodedata.category(char)
        if cat.startswith("L") or cat.startswith("N"):   # Letters & Numbers
            allowed.append(char)
        elif cat == "Zs":                               # Space separator
            allowed.append(" ")
        elif char in "-().":                            # Safe punctuation
            allowed.append(char)
    s = "".join(allowed)
    for pat in _BAD_PHRASES:
        s = pat.sub("", s)
    return _TRAILING_MIX.sub("", s).strip()

def _atomic_save_audio(audio_obj, target_path: Path):
    """
    Save mutagen audio object atomically: write to temp file then replace.
    """
    with NamedTemporaryFile(delete=False, dir=target_path.parent) as tmp:
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

def _purge_id3_frames(id3, frames, filepath):
    for frame in frames:
        if frame in id3:
            logging.info("PURGING frame %s from %s", frame, filepath.name)
            id3.delall(frame)

def _sanitize_id3_tags(id3, keys):
    for key in keys:
        if key in id3 and getattr(id3[key], "text", None):
            original = id3[key].text[0]
            id3[key].text = [whitelist_scrub(original)]

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
            try:
                id3 = audio if isinstance(audio, ID3) else ID3(filepath)
            except Exception:
                id3 = ID3()
                try:
                    id3.save(str(filepath))
                    id3 = ID3(filepath)
                except Exception:
                    logging.exception("Unable to initialize ID3 for %s", filepath)
                    return

            _purge_id3_frames(id3, ("COMM", "TIT3", "TXXX"), filepath)
            _sanitize_id3_tags(id3, ("TIT2", "TPE1"))
            _atomic_save_audio(id3, filepath)

        elif suffix in (".mp4", ".m4a"):
            tags = audio.tags or {}
            for atom in ("\xa9cmt", "\xa9des", "desc"):
                if atom in tags:
                    logging.info("PURGING atom %s from %s", atom, filepath.name)
                    tags.pop(atom, None)
            for atom in ("\xa9nam", "\xa9ART", "©nam", "©ART"):
                if atom in tags and isinstance(tags[atom], list) and tags[atom]:
                    tags[atom][0] = whitelist_scrub(tags[atom][0])
            _atomic_save_audio(audio, filepath)

        else:
            logging.debug("File suffix not handled by sanitizer: %s", suffix)

    except Exception:
        logging.exception("Failed internal scrub for %s", getattr(filepath, "name", str(filepath)))
        raise
