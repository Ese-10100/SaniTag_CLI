import os
import re
import sys
import time
import random
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4
import musicbrainzngs
from logging.handlers import RotatingFileHandler
from metadata_sanitizer import whitelist_scrub, deep_sanitize_metadata

# --- LOGGING FILTERS ---
class IgnoreTypeIdFilter(logging.Filter):
    def filter(self, record):
        return "uncaught attribute type-id" not in record.getMessage()

class OnlyTypeIdFilter(logging.Filter):
    def filter(self, record):
        return "uncaught attribute type-id" in record.getMessage()

# --- DEVSECOPS CONFIG ---
load_dotenv()

AD_PATTERNS = [
    r"\| SonsHub\.com", r"^yt1s\s*-\s*(.+)$", r"www\.sonshub\.com",
    r"SonsHub\.com", r"SongsLover\.(com|club|icu)", r"songslover\.(com|club|icu)",
    r"www\.", r"\.com", r"\.club", r"naijatrend", r"fazmusic", r"yt1s",
    r"melodydel", r"kuwo", r"Tooxclusive", r"Naijaloaded", r"SonsHub"
]

MB_EMAIL = os.getenv("MB_EMAIL")
if not MB_EMAIL:
    sys.exit("Critical Error: MB_EMAIL missing from environment.")
musicbrainzngs.set_useragent("SaniTag-CLI", "1.3", MB_EMAIL)

RAW_PATH = "/data/data/com.termux/files/home/storage/downloads/SaniTag_CLI" ''' or os.getenv("MUSIC_DIRECTORY")'''
if not RAW_PATH:
    sys.exit("Configuration Error: MUSIC_DIRECTORY not set.")
SAFE_ZONE = Path(RAW_PATH).resolve()

# --- UTILITIES ---
def is_path_safe(target):
    try:
        Path(target).resolve().relative_to(SAFE_ZONE)
        return True
    except ValueError:
        return False

def clean_string(text):
    if not text:
        return ""
    for pattern in AD_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return text

def backoff_api_call(func, *args, **kwargs):
    retries, max_retries, base_delay = 0, 5, 1.0
    while retries < max_retries:
        try:
            return func(*args, **kwargs)
        except (musicbrainzngs.NetworkError, musicbrainzngs.ResponseError) as e:
            retries += 1
            if retries == max_retries:
                logging.error(f"Max retries reached: {e}")
                return None
            wait_time = (base_delay * (2**retries)) + random.uniform(0, 1)
            logging.warning(f"Throttled. Retrying in {wait_time:.2f}s...")
            time.sleep(wait_time)
    return None

def fetch_metadata(title, artist):
    clean_t = clean_string(title)
    clean_a = clean_string(artist)

    def mb_query():
        time.sleep(1)  # API rate limit compliance
        query = f"recording:{clean_t} AND artist:{clean_a}"
        return musicbrainzngs.search_recordings(query=query, limit=1)

    result = backoff_api_call(mb_query)
    if result and result.get("recording-list"):
        match = result["recording-list"][0]
        score = int(match.get("ext:score", 0))
        if score > 90:
            return clean_string(match["title"]), clean_string(match["artist-credit"][0]["artist"]["name"])
        else:
            logging.warning(f"[LOW SIGNAL] Score {score}: API guess rejected for {title}.")
    return clean_t, clean_a

def secure_sanitize(text):
    clean = re.sub(r'[\\/*?:"<>|]', "", text)
    return clean.strip() or "Unknown"

# --- CORE ENGINE ---
def run_audit_and_exec(dry_run=True, auto_approve=False):
    if not SAFE_ZONE.exists():
        logging.critical("Safety Check Failed: Path does not exist.")
        return

    plan = []
    logging.info(f"Initiating Secure Scan on {SAFE_ZONE}...")

    for filepath in SAFE_ZONE.rglob("*"):
        if filepath.is_dir() or filepath.suffix.lower() not in [".mp3", ".m4a"]:
            continue
        if not is_path_safe(filepath):
            logging.error(f"BLOCKED: Security violation at {filepath}")
            continue

        try:
            if filepath.suffix.lower() == ".mp3":
                audio = EasyID3(filepath)
                t, a = whitelist_scrub(audio.get("title", ["Unknown"])[0]), whitelist_scrub(audio.get("artist", ["Unknown"])[0])
            else:
                audio = MP4(filepath)
                t, a = whitelist_scrub(audio.get("\xa9nam", ["Unknown"])[0]), whitelist_scrub(audio.get("\xa9ART", ["Unknown"])[0])

            if any(x in t.lower() for x in ["unknown", "www", "videoplayback"]) or not t:
                logging.info(f"[CLOUD QUERY]: Fetching data for {filepath.name}")
                t, a = fetch_metadata(t, a)
            if not t or t.lower() == "unknown":
                t = filepath.stem

            clean_t, clean_a = secure_sanitize(t), secure_sanitize(a)
            if clean_a.lower() == "unknown":
                clean_a = "Various Artists"

            new_name = f"{clean_a} - {clean_t}{filepath.suffix}"
            target_path = filepath.parent / new_name
            if filepath.name != new_name:
                plan.append((filepath, target_path))
        except Exception as e:
            logging.exception(f"Audit failure for {filepath.name}: {e}")

    if not plan:
        logging.info("Audit Complete: Environment is clean.")
        return

    for old, new in plan:
        print(f"[AUDIT PENDING]: {old.name} -> {new.name}")

    confirm = "Y" if auto_approve else input(f"\nAuthorize {len(plan)} changes? (Y/N): ")
    if confirm.upper() == "Y":
        for old_p, new_p in plan:
            try:
                if dry_run:
                    logging.info(f"DRY RUN: rename {old_p.name} -> {new_p.name}")
                else:
                    logging.info(f"Hardening Header: {old_p.name}")
                    deep_sanitize_metadata(old_p)

                    if is_path_safe(new_p):
                        if new_p.exists():
                            logging.warning(f"[Collision]: {new_p.name} already exists.")
                            if auto_approve:
                                alt_path = new_p.with_name(new_p.stem + "_dup" + new_p.suffix)
                                old_p.rename(alt_path)
                                logging.info(f"RENAMED WITH SUFFIX: {alt_path.name}")
                            else:
                                choice = input(f"{new_p.name} exists. [S]kip, [O]verwrite, [R]ename with suffix? ").upper()
                                if choice == "S":
                                    logging.info(f"Skipped {old_p.name}")
                                elif choice == "O":
                                    old_p.rename(new_p)
                                    logging.info(f"OVERWRITTEN: {new_p.name}")
                                elif choice == "R":
                                    alt_path = new_p.with_name(new_p.stem + "_dup" + new_p.suffix)
                                    old_p.rename(alt_path)
                                    logging.info(f"RENAMED WITH SUFFIX: {alt_path.name}")
                                else:
                                    logging.info("Invalid choice. Skipping.")
                        else:
                            old_p.rename(new_p)
                            logging.info(f"COMMITTED: {new_p.name}")
            except Exception as e:
                logging.exception(f"Rename failed for {old_p.name}: {e}")

# --- ENTRYPOINT ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SaniTag-CLI: Hardened Media Sanitizer")
    parser.add_argument("--apply", action="store_true", help="Apply renames (default is dry-run)")
    parser.add_argument("--auto-approve", action="store_true", help="Bypass interactive confirmation")
    parser.add_argument("--log-file", type=Path, help="Path to log file. If omitted, logs go to console only.")
    args = parser.parse_args()

    handlers = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        handlers.append(RotatingFileHandler(args.log_file, maxBytes=5*1024*1024, backupCount=3))
        debug_handler = RotatingFileHandler("sanitag-debug.log", maxBytes=2*1024*1024, backupCount=2)
        debug_handler.setLevel(logging.INFO)
        debug_handler.addFilter(OnlyTypeIdFilter())
        logging.getLogger().addHandler(debug_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers
    )
    logging.getLogger().addFilter(IgnoreTypeIdFilter())
