# 🎬 Konten Niche Pro

**Auto-Discovery & Upload** — A desktop application for discovering, downloading, editing, and uploading short-form video content to YouTube, Instagram, TikTok, and Facebook.

## Features

- **Multi-platform search** — Find trending videos across niches (Gaming, Cooking, Comedy, etc.)
- **Parallel download** — Download multiple videos simultaneously with retry logic
- **Anti-copyright filter** — Automated video transformations (mirror, speed, color grading, crop to 9:16)
- **AI-powered captions** — Generate viral captions using Gemini or OpenAI
- **Multi-platform upload** — Upload to YouTube, Instagram, TikTok, Facebook
- **Scheduled uploads** — Set delay between uploads
- **Auto-cleanup** — Automatically delete local files after successful upload

## Tech Stack

| Component | Technology |
|-----------|-----------|
| GUI | CustomTkinter (dark mode) |
| Database | SQLAlchemy + SQLite |
| Scraping | yt-dlp |
| Video Editing | MoviePy |
| AI Captions | Google Gemini / OpenAI |
| Upload Automation | Composio |
| Public URL Tunneling | pyngrok |

## Quick Start

### 1. Prerequisites

- Python 3.12+ ([download](https://python.org))
- FFmpeg (required by MoviePy) — [install guide](https://ffmpeg.org/download.html)

### 2. Setup

```bash
# Clone the repo
git clone <your-repo-url>
cd scking

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate
# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
notepad .env          # Windows
nano .env             # Linux/macOS
```

**Minimum required:**
- `COOKIES_FILE` — Export browser cookies for yt-dlp ([guide](https://github.com/yt-dlp/yt-dlp#cookies))

**Optional (for AI captions):**
- `GEMINI_API_KEY` — Get from [Google AI Studio](https://aistudio.google.com/)
- `OPENAI_API_KEY` — Get from [OpenAI Platform](https://platform.openai.com/)

**Optional (for uploads):**
- `NGROK_AUTHTOKEN` — Get from [ngrok](https://ngrok.com/)
- `COMPOSIO_API_KEY` — Get from [Composio](https://composio.dev/)
- `GOOGLE_CLIENT_SECRETS_FILE` — YouTube OAuth2 credentials

### 4. Run

```bash
python main.py
```

## Usage

1. **Select a niche** from the dropdown (or enter a custom keyword)
2. **Click "Cari Video"** to search for videos
3. **Click "Download"** to download all discovered videos
4. **Configure options:**
   - ✨ AI Caption: Select Gemini or OpenAI
   - 🛡 Anti-Copyright: Enable video transformations
   - 🧹 Auto-Cleanup: Delete files after upload
   - ⏱ Delay: Set minutes between uploads
5. **Click "Upload"** to start uploading

## Project Structure

```
scking/
├── main.py              # GUI app (CustomTkinter)
├── config.py            # Environment & constants
├── database.py          # SQLAlchemy models & session
├── scraper.py           # yt-dlp search & download
├── video_editor.py      # MoviePy anti-copyright processing
├── content_generator.py # AI caption generation
├── uploader.py          # Platform upload handlers
├── .env.example         # Environment template
├── .gitignore           # Git ignore rules
└── requirements.txt     # Python dependencies
```

## Security Notes

- **Never commit `.env`** — It contains API keys
- **Ngrok exposure is restricted** — Only explicitly allowed files are served
- **API keys are validated** — Whitespace is stripped, missing keys show clear errors

## License

Private project. All rights reserved.
