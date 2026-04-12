import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load variabel lingkungan dari .env
load_dotenv()

# ═══════════════════════════════════════════════════════════════
# BASE PATH — Absolute path agar tidak terpengaruh os.chdir()
# ═══════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════════════════════════
# KONFIGURASI GLOBAL
# ═══════════════════════════════════════════════════════════════
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", os.path.join(BASE_DIR, "downloads"))
GOOGLE_CLIENT_SECRETS = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "client_secrets.json")

# Log file menggunakan absolute path agar CWD change tidak mempengaruhi
_log_file_raw = os.getenv("LOG_FILE", "app.log")
LOG_FILE = _log_file_raw if os.path.isabs(_log_file_raw) else os.path.join(BASE_DIR, _log_file_raw)

LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO")

# AI & Proxy Settings — strip whitespace untuk mencegah silent auth failure
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ═══════════════════════════════════════════════════════════════
# NAMED CONSTANTS — Eliminasi magic numbers di seluruh codebase
# ═══════════════════════════════════════════════════════════════
MAX_WORKERS = 3                  # Jumlah thread paralel untuk download/upload
TITLE_TRUNCATE_LEN = 65          # Panjang maksimal judul ditampilkan di tabel UI
SEARCH_OVERFETCH = 30            # Jumlah tambahan fetch untuk filter duplikat
NGROK_PORT = 8000                # Port untuk Ngrok HTTP server
VIDEO_OUTPUT_WIDTH = 720         # Lebar standar output video vertikal
VIDEO_OUTPUT_HEIGHT = 1280       # Tinggi standar output video vertikal
RENDER_THREADS = 4               # Jumlah thread untuk video rendering
CAPTION_MAX_TOKENS = 400         # Max token untuk AI caption generation
UPLOAD_POLL_DELAY = 2            # Delay (detik) setelah upload API call

# ── Google Trends Configuration ──
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST_TRENDS = os.getenv("RAPIDAPI_HOST_TRENDS", "google-trends-api.p.rapidapi.com").strip()
RAPIDAPI_HOST_TIKTOK = os.getenv("RAPIDAPI_HOST_TIKTOK", "tiktok-scraper7.p.rapidapi.com").strip()
RAPIDAPI_HOST_FB = os.getenv("RAPIDAPI_HOST_FB", "facebook-pages-scraper.p.rapidapi.com").strip()
RAPIDAPI_HOST_IG = os.getenv("RAPIDAPI_HOST_IG", "instagram-scraper-stable-api.p.rapidapi.com").strip()

MIN_TREND_SCORE = int(os.getenv("MIN_TREND_SCORE", "40"))
ENABLE_TRENDS_CHECK = os.getenv("ENABLE_TRENDS_CHECK", "True").lower() in ('true', '1', 't')

# Parsing LOG_LEVEL string ke integer object
numeric_level = getattr(logging, LOG_LEVEL_STR.upper(), logging.INFO)

def setup_logging():
    """
    Konfigurasi logging ke file dan konsol (rotating file handler).
    Mencegah file log membengkak tanpa batas (maksimal 5MB, simpan 3 backup).
    """
    logger = logging.getLogger()
    logger.setLevel(numeric_level)
    
    # Hindari menambahkan handler berulang kali jika dipanggil beberapa kali
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] %(message)s')

        # 1. Handler untuk File (Rotating, max 5MB, keep 3 backups)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        
        # 2. Handler untuk Konsol (stdout)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
    return logger

def cleanup_temp_files():
    """Membersihkan file ytdl residual dan file temp audio sisa moviepy di direktori downloads."""
    if not os.path.exists(DOWNLOAD_DIR):
        return
    deleted_count = 0
    for fname in os.listdir(DOWNLOAD_DIR):
        if fname.endswith(".part") or fname.endswith(".ytdl") or fname.startswith("temp-audio-") or fname.endswith(".temp"):
            filepath = os.path.join(DOWNLOAD_DIR, fname)
            try:
                os.remove(filepath)
                deleted_count += 1
            except OSError:
                pass
    if deleted_count > 0:
        logging.getLogger(__name__).info(f"Cleanup: Berhasil menghapus {deleted_count} file sementara/residual.")

def ensure_directories():
    """Memastikan bahwa folder esensial ada saat aplikasi startup."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        logging.getLogger(__name__).info(f"Direktori {DOWNLOAD_DIR} berhasil dibuat.")
    cleanup_temp_files()
