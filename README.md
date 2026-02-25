SaniTag_CLI

  

📖 Overview

SaniTag_CLI is a hardened DevSecOps -oriented command line tool for auditing and sanitizing music metadata filenames. It removes ad watermarks, enforces safe naming, prevents path traversal exploits, and integrates with MusicBrainz for cloud metadata enhancement.

🌟 Features & Technical Pillars
Polyglot Metadata Extraction: Seamlessly abstracts metadata retrieval across multiple containers using EasyID3 for MP3 and mutagen.mp4 for M4A/AAC files.

Regex-Based Signal Recovery: Implements compiled regular expressions to identify and strip high-frequency "ad-watermarks" (e.g., yt1s -), restoring the filename to its canonical metadata state.

Environment-Agnostic Configuration: Utilizes os.getenv with safe defaults (./MP3), ensuring the tool is portable across Windows, Linux, and CI/CD runners without hardcoded path dependencies.

Atomic Audit Logic: Employs a decoupled "Plan-then-Execute" workflow. The modify_music_title function generates a transition mapping, which is then audited and logged before any filesystem rename operations occur.

Defensive Logging: Standardizes system telemetry using Python’s logging module, providing timestamps and severity levels suitable for sysadmin oversight.

CLI flags for dry run, apply, auto approve, and log file output

🚀 Installation

git clone https://github.com/Ese-10100/SaniTag_CLI.git
cd SaniTag_CLI
pip install -r requirements.txt

Create a .env file:

MB_EMAIL=your_email@example.com
MUSIC_DIRECTORY=/path/to/music

📝 Usage

Dry run (safe mode)

python rewriteMusicTitle.py --dry-run

Apply changes

python rewriteMusicTitle.py --apply

Automation mode

python rewriteMusicTitle.py --apply --auto-approve

Log to file

python rewriteMusicTitle.py --apply --auto-approve --log-file /var/log/sanitag.log

⚡ Collision Handling

Interactive mode: prompts [S]kip, [O]verwrite, [R]ename with suffix

Automation mode: automatically appends _dup

📜 Logs

Main logs: console or specified log file

Debug logs: sanitag-debug.log captures suppressed MusicBrainz messages

Rotating handlers prevent uncontrolled growth

🔄 CI/CD Integration

Add .github/workflows/sanitag-ci.yml:

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
    - run: python rewriteMusicTitle.py --dry-run --auto-approve

✅ Best Practices

Always test with --dry-run before applying

Use --log-file in production for audit trails

Keep .env secure (never commit it)

Rotate logs for sysadmin safety

This README gives developers everything they need to install, configure, and run SaniTag_CLI, plus CI/CD integration and badges for visibility.

📜 License

SaniTag_CLI is licensed under a custom license designed to allow free use for personal and community purposes while requiring commercial users to obtain a paid license.

Key Points:

Commercial Use: Requires a paid license agreement with the author. Commercial users must contact the author to negotiate terms and royalties.

Modification: Allowed for personal and community use. Commercial modifications require licensing.

Distribution: Allowed for non-commercial purposes. Commercial distribution requires licensing.

Private Use: Fully allowed without restrictions.

This licensing approach enables broad community collaboration and use while protecting the author's rights to earn royalties from commercial exploitation.

Formal Licensing and Enforcement

To enforce royalties and commercial licensing, formal legal agreements are necessary:

Software License Agreement: Defines user rights, restrictions, royalty terms, reporting, audits, and enforcement.

Royalty Agreement: Specifies royalty calculations, payment schedules, and consequences of non-payment.

Terms and Conditions: Users must agree to these before commercial use.

Commercial Contracts: Separate agreements for commercial customers outlining negotiated terms.

These documents create legally binding contracts enabling the enforcement of royalty payments and usage restrictions.

For inquiries about commercial licensing, please contact the author at eseokpongs13@gmail.com.

# SaniTag_CLI
SaniTag_CLI is a hardened DevSecOps‑oriented command line tool for auditing and sanitizing music metadata filenames. It removes ad watermarks, enforces safe naming, prevents path traversal exploits, and integrates with MusicBrainz for cloud metadata enhancement.