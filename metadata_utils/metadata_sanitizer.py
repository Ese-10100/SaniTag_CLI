# metadata_sanitizer.py
import os
import re
import logging
import unicodedata
import shutil
from metadata_utils.audio_utils import decode_audio_tags
from pathlib import Path
from tempfile import NamedTemporaryFile
from mutagen import File as MutagenFile
from mutagen.id3 import ID3
from typing import Optional

logging.basicConfig(level=logging.INFO)

# --- CONFIG: whitelist and bad phrases ---
_BAD_PHRASES_RAW = [
    "SongsLover.com", "SonsHub", "FazMusic", "yt1s",
    "lyric_video", "lyric video", "official music video", "Official", "makhits",
    "official video", "Official Lyric Video", "audio", "Audio Only", "audio only",
    "www.SongsLover.pk", "pEZIYGN5HIo", "(Lyrics)", "official audio",
    "naijatrend", "SongsLover.Live", "download link", "FrkMusic", "WaterTower",
    "mp3mansion"
]

_BAD_PHRASES_REGEX = [
    r"\.com", r"\.pk",
    r"\.net", r"\.live", r"\.org", r"\.co",
    r"\.top", r"\.icu", r"\.club", r"\.xyz",
    r"\(\s*official[^)]*\)",
    r"\(\s*lyrics[^)]*\)",
    r"\(\s*audio[^)]*\)",
    r"\s*_low\b",        # strip suffix with preceding space
    r"\s*_144p\b",       # strip low‑res suffix
    r"\s*_hd\b",         # strip HD suffix
]
_BAD_PHRASES = [re.compile(re.escape(p), re.IGNORECASE) for p in _BAD_PHRASES_RAW] + \
               [re.compile(p, re.IGNORECASE) for p in _BAD_PHRASES_REGEX]
_TRAILING_MIX = re.compile(r'[\s\-_.|]+$')

def whitelist_scrub(text: Optional[str]) -> str:
    """Normalize, strip disallowed characters, and remove known bad phrases."""
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
        elif char in "-().":                            # Safe punctuation & paratheses
            allowed.append(char)
    s = "".join(allowed)
    for pat in _BAD_PHRASES:
        s = pat.sub("", s) # This is going to remove each iterated value in bad phrases
    s = re.sub(r'\(\s*\)', "", s).strip() # This should remove orphaned parantheses
    return _TRAILING_MIX.sub("", s).strip()

def _atomic_save_audio(audio_obj, target_path: Path):
    """Save mutagen audio object atomically: write to temp file then replace."""
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
    - Removes junk frames/atoms.
    - Whitelists core tags using whitelist_scrub.
    - Uses atomic save, backup, and verification.
    """
    try:
        if not isinstance(filepath, Path):
            filepath = Path(filepath)
        if not filepath.exists():
            logging.warning("File not found: %s", filepath)
            return

        backup = Path(filepath).with_suffix(filepath.suffix + ".bak")
        try:
            shutil.copy2(filepath, backup)
        except Exception as e:
            logging.error(f"Backup cannot be created due to: {e}")

        ori_size = backup.stat().st_size if backup.exists() else None

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

            try:
                _purge_id3_frames(id3, ("COMM", "TIT3", "TXXX", "WXXX"), filepath)
                _sanitize_id3_tags(id3, ("TIT2", "TPE1"))
                _atomic_save_audio(id3, filepath)

                n_size = filepath.stat().st_size
                if ori_size and n_size < 0.9 * ori_size and n_size < 1024 * 1024:
                    logging.error(f"[ROLLBACK]: {filepath.name} shrank from {ori_size} → {n_size}. Restoring backup.")
                    shutil.copy2(backup, filepath)
                elif ori_size and n_size < 0.9 * ori_size:
                    logging.warning(f"[WARNING]: File size dropped below 90%. {ori_size} → {n_size}")
            finally:
                if backup.exists():
                    backup.unlink()
        
        elif suffix in (".mp4", ".m4a"):
            try:
                # Here we were using the .m4a bytes to assign tags its value e.g tags = audio.tags or {}. But to clear of the bug, we need to first normalize all items, then destructure at runtime
                tags = decode_audio_tags(audio.tags)
                for atom in ("\xa9cmt", "\xa9des", "desc"):
                    if atom in tags:
                        logging.info("PURGING atom %s from %s", atom, filepath.name)
                        tags.pop(atom, None)
                for atom in ("\xa9nam", "\xa9ART", "©nam", "©ART"):
                    if atom in tags and isinstance(tags[atom], list) and tags[atom]:
                        tags[atom][0] = whitelist_scrub(tags[atom][0])
                _atomic_save_audio(audio, filepath)
                # Verification step
                verification = MutagenFile(filepath)
                if not verification or not getattr(verification.info, 'length', None):
                    logging.error(f"[INTEGRITY FAIL] {filepath.name}. Restoring backup.")
                    shutil.copy2(backup, filepath)
            finally:
                # Ensure backup cleanup
                if backup.exists():
                    backup.unlink()
        else:
            logging.debug("File suffix not handled by sanitizer: %s", suffix)

    except Exception:
        logging.exception("Failed internal scrub for %s", getattr(filepath, "name", str(filepath)))
        raise