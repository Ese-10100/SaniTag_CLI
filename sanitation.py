#sanitation.py
import os
import re
import sys
import time
import random
import logging
import argparse
import shutil, subprocess
import ssl
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from mutagen import File as MutagenFile
from datetime import datetime
import musicbrainzngs
from logging.handlers import RotatingFileHandler
from metadata_utils.audio_utils import view_audio_file, extract_basic_tags, decode_audio_tags # helper function to view metadata of a file, used for debugging and testing
from metadata_utils.metadata_sanitizer import whitelist_scrub, deep_sanitize_metadata  #those helpers inside the folder metadata_utils

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
    r"SonsHub\.com", r"SongsLover\.(com|club|icu)", r"songslover\.(com|club|icu|live)",
    r"www\.", r"\.com", r"\.club", r"naijatrend", r"fazmusic", r"yt1s",
    r"melodydel", r"kuwo", r"Tooxclusive", r"Naijaloaded", r"SonsHub", r"Marvarid\.net", r"\[.*?\]",
    r"SongsLover\.Live"
]

MB_EMAIL = os.getenv("MB_EMAIL")
if not MB_EMAIL:
    sys.exit("Critical Error: MB_EMAIL missing from environment.")
musicbrainzngs.set_useragent("SaniTag-CLI", "1.3", MB_EMAIL)

RAW_PATH = os.getenv("MUSIC_DIRECTORY")
if not RAW_PATH:
    sys.exit("Configuration Error: MUSIC_DIRECTORY not set.")
SAFE_ZONE = Path(RAW_PATH).resolve()

''' This concept warns the user that their music directory does not have the supported audio files and it should be filled.'''

if not any(Path(RAW_PATH).rglob("*.mp3")) and not any(Path(RAW_PATH).rglob("*.m4a")):
    sys.exit(f"Environment Warning: {RAW_PATH} contains no supported audio files to process.") 

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
    text = re.sub(r'\s*\[.*?\]\s*', "", text).strip()
    text = re.sub(r'\s+([.,;:!?])', r"\1", text).strip()
    return text

def __initSQL__():
    try:
        logging.info("Initializing metadata cache database...")
        cache = Path("metadata_cache.db")
        conn = sqlite3.connect(cache)
        cur = conn.cursor()
        # cur.execute("DROP TABLE IF EXISTS metadata_cache")
        cur.execute("""
                CREATE TABLE metadata_cache (
                    title TEXT,
                    artist TEXT,
                    UNIQUE (title, artist)
                )
            """)
        conn.commit()
        conn.close()    
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
    
    return str(cache)

CACHE_DB = __initSQL__()

def backoff_api_call(func, *args, **kwargs):
    retries, max_retries, base_delay = 0, 5, 1.0
    while retries < max_retries:
        try:
            return func(*args, **kwargs)
        except (musicbrainzngs.NetworkError, musicbrainzngs.ResponseError, ssl.SSLError) as e:
            retries += 1
            if retries == max_retries:
                logging.error(f"Max retries reached: {e}")
                return None
            wait_time = (base_delay * (2**retries)) + random.uniform(0, 1)
            logging.warning(f"Throttled. Retrying in {wait_time:.2f}s...")
            time.sleep(wait_time)
    return None

#Helper function to cache hits
    
def list_cache_entries(limit=10):
    logging.info(f"Listing up to {limit} entries from metadata cache...")
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute("SELECT title, artist FROM metadata_cache LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("Cache is empty.")
    else:
        print(f"Showing up to {limit} cached entries:")
        for t, a in rows:
            print(f"{t} - {a}")

def fetch_metadata(title, artist):
    clean_t = clean_string(title)
    clean_a = clean_string(artist)
    
    # set a flag to watch when musicbrainz is triggered
    used_musicbrainz = False
    
    # Guard against None, empty title and artist strings
    if not clean_t and not clean_a:
        logging.warning("[FETCH SKIP]:Invalid title or artist provided.")
        return "", "", used_musicbrainz

    # First check cache
    logging.info(f"Checking cache for [{clean_t}] by [{clean_a}]...")
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute("SELECT title, artist FROM metadata_cache WHERE title=? AND artist=?", (clean_t, clean_a))
    row = cur.fetchone()
    conn.close()
    if row:
        logging.info(f"[CACHE HIT]: {clean_t} by {clean_a}")
        return clean_t, clean_a, False

    
    def mb_query():
        time.sleep(4)  # API rate limit compliance
        query = f"recording:{clean_t} AND artist:{clean_a}"
        return musicbrainzngs.search_recordings(query=query, limit=1)

    result = backoff_api_call(mb_query)
    if result and result.get("recording-list"):
        match = result["recording-list"][0]
        score = int(match.get("ext:score", 0))
        if score > 95: # Harmonic mean score threshold for high confidence
            used_musicbrainz = True
            title = clean_string(match["title"])
            artist = clean_string(match["artist-credit"][0]["artist"]["name"])
            logging.info(f"[MUSICBRAINZ] High-confidence metadata found: {title} - {artist}")
    # then store in cache
            conn = sqlite3.connect(CACHE_DB)
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO metadata_cache VALUES (?, ?)", (title, artist))
            conn.commit()
            conn.close()            
            
            return title, artist, used_musicbrainz
        else:
            logging.warning(f"[LOW SIGNAL] Score {score}: API guess rejected for {title}.")
    return clean_t, clean_a, used_musicbrainz

def search_cache_by_artist(a):
    conn =  sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute("SELECT title, artist FROM metadata_cache WHERE artist LIKE ?", (f'%{a}%',))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print(f"No cache entries found for artist: {a}")
    else:
        print(f"The cache entries for artist: {a}")
        for t, a, in rows:
                print(f"{a} - {t}")
    
# I'll be using that to format the table output for the summary.
def report_heading_table(total_tags, total_mb, total_fallback):
    header = f"{'                                Source': ^20} | {'Count': <20}"
    divider = "_" * len(header)
    rows = [
        f"{'Tags': ^20} | {total_tags: <10,}",
        f"{'MusicBrainz': ^20} | {total_mb: <10,}",
        f"{'Fallback': ^20} | {total_fallback: <10,}"
    ]
    logging.info("\n" + header)
    logging.info(divider)
    for row in rows:
        logging.info(row)


def remux_report_ffmpeg(input_path: Path, output_path: Path)-> bool:
    """This function is supposed to act as an argument parser for all files tagged for remuxing. 
        It should read the file paths from the remux report, and then perform the necessary remuxing operations using ffmpeg or a similar tool. 
        The function should also handle any errors that may occur during the remuxing process and log them appropriately.

        Read needs_remux_report.txt and attempt remux on each listed file with ffmpeg to repair missing/broken moov atoms.
        Uses -c copy (stream copy) - no re-encoding, no quality loss. Returns True on success, False on failure."""
    
    start = time.perf_counter()
    if not shutil.which("ffmpeg"):
        logging.error("[REMUX-REPORT]:ffmpeg not found in PATH. Install it or add it to environment path variables.")
        return False
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c", "copy", str(output_path) #-y overwrite output without prompting, -i input file, Uses -c copy (stream copy) - no re-encoding, output path (temp path, never same as input)
    ]
    try:
        logging.info(f"[REMUX-START]: Attempting remux for {input_path.name}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        end = time.perf_counter()
        logging.info(f"Remux + metadata injection took {end - start:.2f} seconds")
        logging.info(f"[REMUXED]: {output_path.name}")
        return True
    except subprocess.CalledProcessError as e:
        logging.debug("REMUX stack trace",exc_info=True)
        logging.error(f"[REMUX-FAIL]: {input_path.name} → {e}")
        return False

def process_remux_report(report_path: Path, output_dir: Path = None):
    '''
    Attempts to read the report_path, if it does not exist, error out, else attmept remux operation on each file.
    Skip date and hypen headers(dates start with '['). Remux files to a temp remuxed file -remuxed.m4a, then atomically replace those files if success.
    Catch partial failures and enqueue reports and prepare them for future remuxing and analysis.
    If remux operation is successful, clear all files in the report. 
    '''
    skipped, successful = 0, 0
    if not report_path.exists():
        logging.error(f"[REMUX-REPORT]: Report path-{report_path}, not found.")
        return
    with open(report_path, "r", encoding="utf-8") as file:
        lines = [line.strip() for line in file if line.strip() and not line.startswith('[') and not line.startswith('-')]
    if not lines:
        logging.info(f"[REMUX-REPORT]: There are no files to process.")
        return
    failed = []
    for line in lines:
        input_path = Path(line)
        # Fix A01 Path traversal attack
        if not is_path_safe(input_path):
            logging.error(f"[REMUX-BLOCKED]: Security violation - file outside safe zone: {input_path}")
            continue
        if not input_path.exists():
            logging.warning(f"[REMUX-SKIP]: Ffmpeg cannot find {input_path.name} likely has been moved or deleted")
            skipped+=1
            continue    
        if output_dir: # user specified output directory - remux copy write there
            output_path = Path(output_dir)/input_path.name
        else:
            output_path = input_path.with_suffix(".remuxed.m4a") # temp path to help remuxing with original
        success = remux_report_ffmpeg(input_path, output_path)
        
        if success:
            start = time.perf_counter()
            if not output_dir:
                # atomically replace the output directory with a tempoary directory
                output_path.replace(input_path)
                logging.info(f"[REMUX-COMMITTED]: {input_path.name} repaired in place.")
            successful += 1
        else:
            failed.append(line)
    
    # if any remux file  had been skipped
    
    if skipped == len(lines):
        logging.warning(f'No report files found. Results could be stale - [TIP]: rerun the scan.')
        return
    
    # Rewrite report: keep only failures, clear if all succeeded
    if failed:
        with open(report_path, "w", encoding="utf-8") as file:
            file.write(f"[{datetime.now().strftime('%d/%B/%Y')} - RETRY QUEUE] \n")
            for entry in failed:
                file.write(f"- {entry}\n")
        logging.warning(f"[REMUX-REPORT]: {len(failed)} file(s) failed. Report updated.")
    else:
        report_path.write_text("")
        end = time.perf_counter()
        logging.info(f"[REMUX-REPORT]: All files remuxed successfully. Report cleared. Skipped: {skipped}, Successful: {successful}, ran for: {end - start} seconds")

def secure_sanitize(text):
    clean = re.sub(r'[\\{}/*?:"<>|]', "", text)
    return clean.strip() or "Unknown"

# --- CORE ENGINE ---
def run_audit_and_exec(dry_run=True, auto_approve=False, batch_size=150):
    if not SAFE_ZONE.exists():
        logging.critical("Safety Check Failed: Path does not exist.")
        return 0, 0, 0, 0 # I haven't really grasped the concept of returning this values. I'm assuming that for the totals, it must always be returned at inititalisation, rather than call at
    
    logging.info(f"Initiating Secure Scan on {SAFE_ZONE}...")
    #Initialize the total counters for the summary
    total_tags, total_mb, total_fallback, remux = 0, 0, 0, 0
    tags = {} 
    
    all_f = [
        file for file in SAFE_ZONE.rglob("*")
        if file.is_file() and file.suffix.lower() in [".mp3", ".m4a"]
    ]
    
    # A09 error. 
    report = "needs_remux_report.txt"
    header_written = False
    
    for i in range(0, len(all_f), batch_size): #Per file batch processing. Management, API calls, and User friendly logs
        batch = all_f[i:i+batch_size]
        logging.info(f"Processing batch {i//batch_size+1}; length: {len(batch)} files")
        plan = []
        tags_count, mb_count, fallback_count = 0, 0, 0 # each variable counter
        logging.info(f"[BATCH {i//batch_size+1}] START: {len(batch)} files")        
        
        for filepath in batch:
            if filepath.is_dir() or filepath.suffix.lower() not in [".mp3", ".m4a"]:
                continue
            if not is_path_safe(filepath):
                logging.error(f"BLOCKED: Security violation at {filepath}")
                continue

            try:
                # Step 1: Read embedded tags
                if filepath.suffix.lower() == ".mp3":
                    audio = MutagenFile(filepath, easy=False)
                    tags = extract_basic_tags(audio)
                    t, a = tags.get("title"), tags.get("artist")
                else:  # M4A
                    audio = MutagenFile(filepath, easy=False)
                    tags = decode_audio_tags(audio.tags)
                    t = tags.get("©nam", ["Unknown Title"])[0] if audio and audio.tags else None
                    a = tags.get("©ART", ["Unknown Artist"])[0] if audio and audio.tags else None

                # Step 2: If missing/suspicious, query MusicBrainz
                if not t or t.lower() in ["unknown", "www", "videoplayback"]:
                    logging.info(f"[CLOUD QUERY]: Fetching data for {filepath.name}")
                    if t or a:
                        t, a, used_musicbrainz = fetch_metadata(t, a)
                    else:
                        used_musicbrainz = False
                else:
                    used_musicbrainz = False

                # Step 3: If still missing, fallback to filename parsing
                if not t or t.lower() == "unknown":
                    stem = re.sub(r'^\d{1,4}\s*-\s*', '', filepath.stem)
                    parts = stem.split(" - ")
                    if len(parts) == 2:
                        a, t = parts
                    else:
                        t = stem
                        a = "Unknown Artist"

                # Step 4: Scrub and normalize
                # Step 4a: To prevent unpredictable behaviour for secure_sanitize, it must always receive a string argument. If, there are no string arguments, then it should return "Unknown".
                t , a = t if t else "Unknown Title", a if a else "Unknown Artist"
                clean_t = whitelist_scrub(secure_sanitize(t))
                clean_a = whitelist_scrub(secure_sanitize(a))

                if not clean_a or clean_a.lower() in ("unknown", ""):
                    clean_a = "Unknown Artist"
                if not clean_t or clean_t.lower() in ("unknown", ""):
                    clean_t = "Unknown Title"

                # Counters
                if used_musicbrainz:
                    logging.info(f"[MUSICBRAINZ] {filepath.name} renamed using API metadata")
                    mb_count += 1
                elif tags and tags.get("title") and tags.get("artist"):
                    logging.info(f"[TAGS] {filepath.name} renamed using embedded metadata")
                    tags_count += 1
                else:
                    logging.info(f"[FALLBACK] {filepath.name} renamed using filename parsing")
                    fallback_count += 1

                # Rename plan and also guard against artist whitespaces errors
                if not clean_a or not clean_a.strip():
                    clean_a = "Unknown Artist"
                new_name = f"{clean_a} - {clean_t}{filepath.suffix}"
                if filepath.suffix.lower() == ".m4a" and new_name.endswith(".m4a.m4a"):
                    new_name = new_name.replace(".m4a.m4a", ".m4a")
                target_path = filepath.parent / new_name
                if filepath.name != new_name:
                    plan.append((filepath, target_path))
            except Exception as e:
                logging.exception(f"Audit failure for {filepath.name}: {e}")
        
        logging.info(f"[BATCH {i//batch_size+1}] COMPLETE")
        logging.info(f"[SUMMARY BATCH {i//batch_size+1}] "
                     f"{tags_count} via tags, {mb_count} via MusicBrainz, {fallback_count} via filename")
        #total tags should accumulate here
        total_tags += tags_count
        total_mb += mb_count
        total_fallback += fallback_count
        time.sleep(32)
        if not plan:
            logging.info(f"Batch {i//batch_size+1} Audit Complete: Environment is clean.")
            continue
        else:
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
                        #TO clear off 'moov' KEYERRORS, I have to skip it when deep_sanitize_metadata does its job
                        if not old_p.exists():
                            logging.warning(f"[SKIP] The file is missing: {old_p.name}. It may have been deleted or moved.")
                            continue
                        try:
                            deep_sanitize_metadata(old_p)
                        except KeyError as e:
                            #This section is still under the batch loop 
                            if 'moov' in str(e):
                                try:
                                    remux+=1
                                    logging.warning(f"[NEEDS-REMUX]: {old_p.name}. Flagged for structural repair (moov atom missing).")
                                    # Optionally append to a separate report file
                                    if not header_written:
                                        with open(report, "a", encoding="utf-8") as file:
                                            file.write("-" * 200 + "\n")
                                            file.write(f"[{datetime.now().strftime('%d/%B/%Y')}]\n")
                                        header_written = True
                                    with open(report, "a", encoding="utf-8") as file:
                                            file.write(f"{new_p}\n")
                                except Exception as e:
                                    logging.error(f"[REMUX-ERROR]: File creation failed due to: {e}. Review what happened.")
                            else:
                                logging.debug("Sanitation error", exc_info=True)  # full stack trace only at DEBUG
                                logging.error(f"[Sanitation error]: Deep sanitation operation of {old_p.name} failed: {e}")

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
       # Write footer only once after all batches complete
    if header_written and remux > 0:
        with open(report, "a", encoding="utf-8") as file:
            file.write(f"\nTotal files awaiting remuxing: {remux}\n")
    
    return total_tags, total_mb, total_fallback, remux

# --- ENTRYPOINT ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SaniTag-CLI: Hardened Media Sanitizer")
    parser.add_argument("--apply", action="store_true", help="Apply renames (default is dry-run). Use with caution, chain --auto-approve to bypass confirmation.")
    parser.add_argument("--auto-approve", action="store_true", help="Bypass interactive confirmation.")
    parser.add_argument("--log-file", type=Path, help="Path to log file. If omitted, logs go to console only.")
    parser.add_argument("--remux-report", action="store_true", help="Perform remux operations on files flagged in remux-report.txt. Runs independently of audit.")
    parser.add_argument("--remux-output-dir", type=Path, default=None, help="(OPTIONAL): Specify your output directory for remux files. If omitted remuxed files replace original.")
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
        force=True,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers
    )
    logging.getLogger().addFilter(IgnoreTypeIdFilter())
    
    if args.remux_output_dir:
        args.remux_output_dir = args.remux_output_dir.resolve()
    
    if args.remux_report:
        process_remux_report(Path("needs_remux_report.txt"), output_dir=args.remux_output_dir)
        sys.exit(0) # Default cleanup. When successful the terminal exits cleanly. Not alongside audit.

    
    #Timer utility
    
    start = time.perf_counter()
    total_tags, total_mb, total_fallback, remux = run_audit_and_exec(dry_run=not args.apply, auto_approve=args.auto_approve)
    end = time.perf_counter()
    DATE = datetime.now().strftime('%d/%B/%Y')
    logging.info(f"[SUMMARY TOTAL] {total_tags} via tags, "
             f"{total_mb} via MusicBrainz, {total_fallback} via filename, remux needed for {remux} files.")
    report_heading_table(total_tags, total_mb, total_fallback)
    logging.info(f"For {DATE} run, your audit scope ran for {end - start:.2f} seconds.")

