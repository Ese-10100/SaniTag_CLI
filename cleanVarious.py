import os
import re
import sys
import logging
from pathlib import Path
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4

music_dir = Path(r"C:/Users/HP/Music/mp3")

# Regex to remove leading numbers and "Various Artists -"
yt1s_PATTERN = re.compile(r"^yt1s\s*-\s*(.+)$", re.IGNORECASE) 
def sanitize_filename(name: str) -> str: 
    match = yt1s_PATTERN.match(name) 
    if match: 
        return match.group(1).strip() 
    return name

def modify_music_title():
    plan = []
    for music in music_dir.rglob("*"):
        if music.suffix.lower() not in [".mp3", ".m4a"]:
            continue
        try:
            if music.suffix.lower() == ".mp3":
                audio = EasyID3(music)
                title = audio.get("title", [music.stem])[0]
            else:
                audio = MP4(music)
                title = audio.get("\xa9nam", [music.stem])[0]

            clean_title = sanitize_filename(title)
            new_name = f"{clean_title}{music.suffix}"
            target_path = music.parent / new_name

            if music.name != new_name:
                plan.append((music, target_path))
        except Exception as e:
            logging.exception(f"File failed due to: {e}")
    return plan

def run_operation():
    logging.info("[Running]...")
    plan = modify_music_title()
    if not plan:
        logging.info("Audit Complete: Environment is clean.")
        return
    for old, new in plan:
        print(f"[AUDIT PENDING]: {old.name} -> {new.name}")
        try:
            os.rename(old, new)
            logging.info(f"Renamed: {old.name} -> {new.name}")
        except Exception as e:
            logging.exception(f"Failed to rename {old.name} due to: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    run_operation()
