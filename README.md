# SaniTag_CLI

SaniTag_CLI is a hardened DevSecOps-oriented command-line tool for auditing and sanitizing music metadata filenames. It removes ad watermarks, enforces safe naming, prevents path traversal exploits, and integrates with MusicBrainz for cloud metadata enhancement.

---

## 📖 Overview

SaniTag_CLI scans a configured music directory and its subdirectories for `.mp3` and `.m4a` files, audits their metadata, and renames them to a clean, canonical format — stripping platform-injected watermarks (e.g. `yt1s`, `SonsHub`, `FazMusic`) and resolving missing metadata via the MusicBrainz API.

All operations run as a dry-run audit by default. No file is renamed until you explicitly authorize it.

---

## 🌟 Features

- **Polyglot Metadata Extraction** — supports `.mp3` (EasyID3) and `.m4a` / `.aac` (mutagen.mp4) containers.
- **Ad Watermark Removal** — compiled regex patterns identify and strip download-platform watermarks, restoring filenames to their canonical metadata state.
- **Cloud Metadata Enhancement** — integrates with MusicBrainz to resolve missing or corrupted title and artist data.
- **Environment-Agnostic Configuration** — portable across Windows, Linux, and CI/CD runners via `.env` — no hardcoded paths.
- **Plan-then-Execute Workflow** — generates a full rename transition map and presents it for review before any filesystem operation is committed.
- **Collision Handling** — interactive `[S]kip / [O]verwrite / [R]ename with suffix` prompt, or automatic `_dup` suffix in automation mode.
- **Defensive Logging** — structured telemetry with timestamps and severity levels, suitable for sysadmin oversight and audit trails.

---

## 🚀 Installation

### Standard

```bash
git clone https://github.com/Ese-10100/SaniTag_CLI.git
cd SaniTag_CLI
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
MB_EMAIL=your_email@example.com
MUSIC_DIRECTORY=/path/to/music
```

> ⚠️ Never commit your `.env` file. Add it to `.gitignore`.

### Docker

```bash
# Build the image
docker build -t sanitag-cli .

# Run against your local music directory
docker run --rm \
  --env-file .env \
  -v /path/to/music:/music \
  sanitag-cli
```

---

## 📝 Usage

**Default — dry-run audit (no changes written):**

```bash
python rewriteMusicTitle.py
```

**Apply renames with interactive confirmation:**

```bash
python rewriteMusicTitle.py --apply
```

**Automation mode — no prompts:**

```bash
python rewriteMusicTitle.py --apply --auto-approve
```

**Log output to a file:**

```bash
python rewriteMusicTitle.py --apply --auto-approve --log-file /your/defined/log/directory/sanitag.log
```

---

## ⚡ Collision Handling

| Mode | Behaviour |
|------|-----------|
| Interactive | Prompts `[S]kip`, `[O]verwrite`, `[R]ename with suffix` |
| Automation (`--auto-approve`) | Automatically appends `_dup` to conflicting filenames |

---

## 📜 Logs

- **Main log** — console output or a specified log file via `--log-file`.
- **Debug log** — `sanitag-debug.log` captures suppressed API messages separately.
- Rotating handlers prevent uncontrolled log growth.

---

## 🧪 Testing

Run the local test suite before applying changes in any new environment:

```bash
pytest
```

The CI pipeline runs tests automatically on every push and pull request to `main`.

---

## 🔄 CI/CD Integration

`.github/workflows/sanitag-ci.yml`:

```yaml
name: SaniTag_CLI Audit

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - run: pip install -r requirements.txt
    - run: pip install bandit safety pytest
    - run: pytest
    - run: bandit -r . -ll
    - run: safety check
    - run: python rewriteMusicTitle.py --auto-approve
```

> Security scanning (Bandit SAST and Safety dependency audit) runs automatically on every push to `main`.

---

## ✅ Best Practices

- Always review the dry-run output before applying changes.
- Use `--log-file` in production environments for persistent audit trails.
- Keep `.env` secure — never commit it to version control.
- Rotate logs regularly in long-running or high-volume environments.

---

## 📜 License

SaniTag_CLI is licensed under a custom license designed to allow free use for personal and community purposes while requiring commercial users to obtain a paid license.

**Key Points:**

- **Commercial Use** — requires a paid license agreement with the author.
- **Modification** — permitted for personal and community use; commercial modifications require licensing.
- **Distribution** — permitted for non-commercial purposes; commercial distribution requires licensing.
- **Private Use** — fully permitted without restriction.

For commercial licensing enquiries, contact: **eseokpongs13@gmail.com**