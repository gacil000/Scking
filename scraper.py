import yt_dlp
import os
import logging
import random
import shutil
from config import COOKIES_FILE, DOWNLOAD_DIR, SEARCH_OVERFETCH


def _find_ffmpeg():
    """
    Mendeteksi apakah ffmpeg tersedia di sistem.
    Returns path ke ffmpeg jika ditemukan, None jika tidak.
    """
    # 1. Cek di PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)

    # 2. Cek lokasi umum di Windows
    common_paths = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\tools\ffmpeg\bin",
    ]
    for p in common_paths:
        if os.path.isdir(p):
            candidate = os.path.join(p, "ffmpeg.exe")
            if os.path.isfile(candidate):
                return p
            # WinGet menyimpan di sub-folder, cari rekursif 1 level
            for sub in os.listdir(p):
                candidate = os.path.join(p, sub, "ffmpeg-*", "bin", "ffmpeg.exe")
                import glob as _g
                matches = _g.glob(os.path.join(p, sub, "**", "ffmpeg.exe"), recursive=True)
                if matches:
                    return os.path.dirname(matches[0])

    return None


FFMPEG_DIR = _find_ffmpeg()
HAS_FFMPEG = FFMPEG_DIR is not None
if HAS_FFMPEG:
    logging.getLogger(__name__).info(f"FFmpeg ditemukan di: {FFMPEG_DIR}")
else:
    logging.getLogger(__name__).warning(
        "FFmpeg TIDAK ditemukan di PATH. Download akan menggunakan format single-stream (kualitas mungkin lebih rendah). "
        "Install ffmpeg lalu restart aplikasi untuk kualitas terbaik."
    )

# Keyword modifier untuk memastikan hasil pencarian adalah video REMIX/KOMPILASI
# yang di-reupload orang lain, bukan konten original (mengurangi risiko copyright).
REMIX_MODIFIERS = [
    "compilation",
    "kompilasi",
    "remix",
    "editan",
    "edit",
    "funny moments",
    "best moments",
    "tiktok compilation",
    "reupload",
    "top moments",
    "highlights",
    "meme",
    "kumpulan",
]

# Mapping tipe konten dropdown -> search modifier
CONTENT_TYPE_MAP = {
    "Kompilasi": "compilation kompilasi",
    "Remix": "remix editan",
    "Funny Moments": "funny moments lucu",
    "Best Moments": "best moments highlights",
    "Highlights": "highlights top",
    "Meme": "meme funny",
    "Tips & Tricks": "tips tricks tutorial",
    "Random (Acak)": None,  # akan dipilih acak
}

def get_base_ydl_opts(download=False, output_path=None):
    """
    Konfigurasi dasar yt-dlp.
    Menggunakan cookies.txt jika file tersebut ada untuk scrape dari Sosmed yang dikunci (misal IG).
    Otomatis menambahkan ffmpeg_location jika ffmpeg ditemukan di lokasi non-PATH.
    """
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': not download,
    }
    
    # Tambahkan lokasi ffmpeg jika ditemukan
    if HAS_FFMPEG and FFMPEG_DIR:
        opts['ffmpeg_location'] = FFMPEG_DIR
    
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
        
    if download and output_path:
        # PENGAMANAN EDGE CASE: Tambahkan extractor/platform_name sbg prefix 
        # Untuk mencegah penimpaan file ID yg kebetulan kembar lintas platform
        opts['outtmpl'] = os.path.join(output_path, '%(extractor)s_%(id)s.%(ext)s')
        
    return opts

def _build_remix_query(keyword, platform, limit, content_type=None):
    """
    Membangun search query yang menargetkan konten REMIX/KOMPILASI.
    
    Args:
        keyword: Kata kunci pencarian (niche)
        platform: Platform target (youtube, instagram, facebook)
        limit: Jumlah hasil yang diminta
        content_type: Tipe konten dari dropdown (opsional). 
                      Jika None atau "Random (Acak)", modifier dipilih acak.
    """
    # Tentukan modifier berdasarkan content_type dropdown
    if content_type and content_type in CONTENT_TYPE_MAP and CONTENT_TYPE_MAP[content_type]:
        modifier_str = CONTENT_TYPE_MAP[content_type]
    else:
        # Fallback: pilih 1-2 modifier secara acak
        num_modifiers = random.randint(1, 2)
        chosen_mods = random.sample(REMIX_MODIFIERS, num_modifiers)
        modifier_str = " ".join(chosen_mods)
    
    if platform == 'youtube':
        search_query = f"ytsearch{limit}:{keyword} {modifier_str} creative commons no copyright shorts"
    elif platform == 'instagram':
        search_query = f"{keyword} {modifier_str} no copyright"
    elif platform == 'tiktok':
        search_query = f"{keyword} {modifier_str} tiktok edit no copyright"
    elif platform == 'facebook':
        search_query = f"{keyword} {modifier_str} no copyright"
    else:
        search_query = f"{keyword} {modifier_str} no copyright"
    
    logging.info(f"Search query [{platform}] (remix mode): {search_query}")
    return search_query

def search_videos(keyword, platform='youtube', limit=10, content_type=None):
    """
    Mencari video berdasarkan platform.
    Otomatis menargetkan konten remix/kompilasi untuk mengurangi risiko copyright.
    
    Args:
        keyword: Kata kunci pencarian
        platform: Platform target
        limit: Jumlah hasil
        content_type: Tipe konten dari dropdown UI
    """
    results = []
    
    search_query = _build_remix_query(keyword, platform, limit, content_type)
    
    ydl_opts = get_base_ydl_opts(download=False)
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            
            if 'entries' in info:
                for entry in info['entries']:
                    if not entry: continue
                    
                    vid_url = entry.get('url') or entry.get('webpage_url')
                    # Khusus YouTube, kalau cuma dapet ID, kita ubah ke URL
                    if platform == 'youtube' and vid_url and not vid_url.startswith('http'):
                        vid_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                        
                    results.append({
                        'title': entry.get('title', 'Unknown Title'),
                        'url': vid_url,
                        'platform': platform
                    })
    except yt_dlp.utils.DownloadError as e:
        logging.error(f"Error Jaringan saat {platform}: {e}")
    except Exception as e:
        logging.error(f"Error Tak Terduga (Scraping): {e}")
        
    return results

from tenacity import retry, wait_exponential, stop_after_attempt
import glob

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10), 
    stop=stop_after_attempt(3), 
    retry=lambda retry_state: isinstance(retry_state.outcome.exception(), yt_dlp.utils.DownloadError) if retry_state.outcome.failed else False,
    reraise=True
)
def download_video(url, output_dir=DOWNLOAD_DIR):
    """
    Mendownload ke lokasi target dengan mekanisme Tenacity exponential retry.
    Hanya retry pada DownloadError (network issues), bukan PermissionError dll.
    
    Returns:
        filepath dari file yang berhasil diunduh, atau None jika gagal.
    """
    os.makedirs(output_dir, exist_ok=True)
        
    ydl_opts = get_base_ydl_opts(download=True, output_path=output_dir)
    
    if HAS_FFMPEG:
        # FFmpeg tersedia: bisa merge video+audio terpisah untuk kualitas terbaik
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    else:
        # FFmpeg TIDAK tersedia: gunakan format single-stream (sudah gabungan)
        ydl_opts['format'] = 'best[ext=mp4]/best'
        logging.info("Menggunakan format single-stream (ffmpeg tidak tersedia)")
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        # Validasi: yt-dlp kadang merge video+audio sehingga extension berubah
        # Contoh: prepare_filename returns .webm tapi output jadi .mkv
        if os.path.exists(filename):
            return filename
        
        # Fallback: cari file berdasarkan nama tanpa extension
        base_name = os.path.splitext(filename)[0]
        matches = glob.glob(f"{base_name}.*")
        if matches:
            # Pilih file terbaru (yang baru saja di-download)
            matches.sort(key=os.path.getmtime, reverse=True)
            logging.info(f"Filename mismatch resolved: {filename} -> {matches[0]}")
            return matches[0]
        
        logging.warning(f"Downloaded file not found at expected path: {filename}")
        return filename
