SaniTag-CLI
Media Extraction & Delimiter Sanitization Automator

A robust Python CLI tool designed to reclaim order from chaotic music libraries. Specifically optimized for handling aggressive web-blog watermarks and inconsistent metadata delimiters.

🚀 Features
Recursive Refactoring: Traverses deep directory trees to standardize naming.

Nuclear Ad-Scrub: Regex-based eradication of domain watermarks (e.g., SonsHub, Naijatrend).

Collision Protection: Automatic index-suffixing (_1, _2) to prevent data loss.

Hybrid Extraction: Supports ID3 (MP3) and MP4 (M4A) metadata with filename fallback.

🛠️ Setup
pip install -r requirements.txt

Configure your MUSIC_DIRECTORY in a .env file.

Run python main.py (Default: Dry Run mode).