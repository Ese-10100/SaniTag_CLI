#unit_test.py
import os
import sys
import pytest
import sqlite3
from pathlib import Path
from sanitation import run_audit_and_exec, __initSQL__, fetch_metadata, is_path_safe, clean_string

@pytest.fixture()

def cache_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("data")/"test_cache.db"
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """ 
            CREATE TABLE metadata_cache(
                title TEXT,
                artist TEXT,
                album TEXT,
                genre TEXT,
                PRIMARY KEY (title, artist)
            )
            """
        )
        conn.commit()
        conn.close()        
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise e    
    return str(db_path)

def test_clean_string():
    assert clean_string("Yesterday [www.Marvarid.net].mp3") == "Yesterday.mp3"

def test_is_path_safe(tmp_path, monkeypatch):
    file = tmp_path/"Yesterday - Imagine Dragons.mp3"
    file.write_text("honeypot")
    monkeypatch.setattr("sanitation.SAFE_ZONE", tmp_path)
    assert is_path_safe(file)

def test_cache_and_lookup():
    cache_db = __initSQL__()
    conn = sqlite3.connect(cache_db)
    cur = conn.cursor()
    cur.execute(
                 "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata_cache'",
                )
    assert cur.fetchone() is not None
    cur.execute(
                 "INSERT INTO metadata_cache VALUES (?, ?)",
                 ("Yesterday.mp3", "Imagine Dragons")
                )
    conn.commit()
    conn.close()
    #simulation
    conn = sqlite3.connect(cache_db)
    cur = conn.cursor()
    cur.execute("SELECT title, artist FROM metadata_cache WHERE title=? AND artist=? ", ("Yesterday.mp3", "Imagine Dragons"))
    row = cur.fetchone()
    conn.close()
    assert row == ( "Yesterday.mp3", "Imagine Dragons",)
    
def test_run_audit_and_exec(tmp_path, monkeypatch):
    file = tmp_path/"Yesterday - Imagine Dragons.mp3"
    file.write_text("honeypot")
    monkeypatch.setattr("sanitation.SAFE_ZONE", tmp_path)
    run_audit_and_exec(dry_run=True, auto_approve=True, batch_size=1)
    # Check if the file has been renamed
    assert file.exists()
