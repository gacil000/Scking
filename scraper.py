import yt_dlp
import os
import logging
import random
import shutil
import requests
from config import (COOKIES_FILE, DOWNLOAD_DIR, SEARCH_OVERFETCH,
                    RAPIDAPI_KEY, RAPIDAPI_HOST_TIKTOK, RAPIDAPI_HOST_FB, RAPIDAPI_HOST_IG)


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
    "Custom (Tanpa Tipe)": "", # tidak ditambah apa-apa
}

# ═══════════════════════════════════════════════════════════════
# PLATFORM SEARCH MODIFIERS — Tailored per platform agar konten
# yang ditemukan via YouTube cocok untuk di-reupload ke target
# ═══════════════════════════════════════════════════════════════
PLATFORM_SEARCH_STYLE = {
    "youtube": "creative commons no copyright shorts",
    "instagram": "reels short video vertical no copyright",
    "tiktok": "tiktok short video vertical trending no copyright",
    "facebook": "viral video facebook reupload no copyright",
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


def _get_modifier_str(content_type=None):
    """Helper: dapatkan modifier string dari content_type dropdown."""
    if content_type in CONTENT_TYPE_MAP:
        mapped_val = CONTENT_TYPE_MAP[content_type]
        if mapped_val is not None:
            return mapped_val
            
    # Fallback jika None (misal: Random (Acak))
    num_modifiers = random.randint(1, 2)
    chosen_mods = random.sample(REMIX_MODIFIERS, num_modifiers)
    return " ".join(chosen_mods)


def _build_remix_query(keyword, platform, limit, content_type=None):
    """
    Membangun search query YouTube (ytsearch) yang disesuaikan per platform.
    
    yt-dlp hanya mendukung native search di YouTube. Untuk platform lain
    (Instagram, TikTok, Facebook), kita tetap cari via YouTube tapi dengan
    modifier khusus agar konten yang ditemukan cocok untuk di-reupload ke
    platform target (misal: short/vertical untuk IG & TikTok, viral untuk FB).
    
    Args:
        keyword: Kata kunci pencarian (niche)
        platform: Platform target (youtube, instagram, tiktok, facebook)
        limit: Jumlah hasil yang diminta
        content_type: Tipe konten dari dropdown (opsional). 
                      Jika None atau "Random (Acak)", modifier dipilih acak.
    """
    # Tentukan modifier berdasarkan content_type dropdown
    modifier_str = _get_modifier_str(content_type)
    
    # Platform style modifier (short/vertical/viral/etc.)
    platform_style = PLATFORM_SEARCH_STYLE.get(platform, "no copyright")
    
    # Semua platform pakai ytsearch — satu-satunya search yang reliable di yt-dlp
    search_query = f"ytsearch{limit}:{keyword} {modifier_str} {platform_style}"
    
    logging.info(f"Search query [{platform}]: {search_query}")
    return search_query


# ═══════════════════════════════════════════════════════════════
# TIER 1: RAPIDAPI SPECIALIZED SCRAPERS (TEMPLATES)
# ═══════════════════════════════════════════════════════════════

def _search_tiktok_rapidapi(query, limit):
    """
    Template RapidAPI Tiktok Scraper (ex: TIKWM API)
    Ganti logic ekstrak JSON sesuai docs RapidAPI saat berlangganan.
    """
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST_TIKTOK:
        return []
        
    url = f"https://{RAPIDAPI_HOST_TIKTOK}/feed/list"
    querystring = {"region": "ID", "keywords": query, "count": limit}
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST_TIKTOK
    }
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        # Menggunakan struktur JSON riil dari tiktok-scraper7 (mereturn list di dalam key "data")
        items = data.get("data", []) 
        for item in items[:limit]:
            vid_url = item.get("play") # URL video asli no-watermark
            title = item.get("title", "TikTok Video")
            if vid_url:
                results.append({'title': title, 'url': vid_url, 'platform': 'tiktok'})
        return results
    except Exception as e:
        logging.error(f"RapidAPI TikTok Error: {e}")
        return []

def _search_facebook_rapidapi(query, limit):
    """Template RapidAPI FB Pages Scraper (ex: FinCal Insights)"""
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST_FB:
        return []
        
    url = f"https://{RAPIDAPI_HOST_FB}/search/videos"
    querystring = {"query": query, "count": limit} 
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST_FB
    }
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        items = data.get("items", []) 
        for item in items[:limit]:
            vid_url = item.get("video_url")
            title = item.get("title", "Facebook Video")
            if vid_url:
                results.append({'title': title, 'url': vid_url, 'platform': 'facebook'})
        return results
    except Exception as e:
        logging.error(f"RapidAPI FB Error: {e}")
        return []

def _extract_ig_items(data, limit):
    """Helper: ekstrak video items dari berbagai format respon IG RapidAPI (Instagram Scraper Stable API).
    
    Mendukung 2 format respon:
    1. GraphQL hashtag format: {posts: {edges: [{node: {is_video, shortcode, ...}}]}}
       → video_url tidak tersedia langsung, pakai shortcode → https://www.instagram.com/reel/{shortcode}
    2. Generic format: [{video_url, caption, ...}] atau {data: [{...}]}
    """
    results = []
    items = []
    
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # ── FORMAT 1: GraphQL hashtag (dari /search_hashtag.php) ──
        # Struktur: {name, posts: {count, edges: [{node: {...}}]}, top_posts: {...}}
        posts_data = data.get("posts", {})
        top_posts_data = data.get("top_posts", {})
        
        edges = []
        if isinstance(posts_data, dict) and "edges" in posts_data:
            edges.extend(posts_data.get("edges", []))
        if isinstance(top_posts_data, dict) and "edges" in top_posts_data:
            edges.extend(top_posts_data.get("edges", []))
        
        if edges:
            # Pass 1: filter hanya video nodes
            for edge in edges:
                node = edge.get("node", {}) if isinstance(edge, dict) else {}
                if not node.get("is_video", False):
                    continue
                
                shortcode = node.get("shortcode", "")
                if not shortcode:
                    continue
                
                ig_url = f"https://www.instagram.com/reel/{shortcode}/"
                
                caption = "Instagram Reel"
                caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
                if caption_edges:
                    raw_caption = caption_edges[0].get("node", {}).get("text", "")
                    if raw_caption:
                        caption = raw_caption[:200] + "..." if len(raw_caption) > 200 else raw_caption
                
                results.append({
                    'title': caption,
                    'url': ig_url,
                    'platform': 'instagram'
                })
                
                if len(results) >= limit:
                    break
            
            # Pass 2: jika 0 video, ambil SEMUA post (yt-dlp bisa handle /p/ URL juga)
            if not results:
                logging.info("RapidAPI IG: 0 video di hashtag, fallback ke semua post (termasuk image).")
                for edge in edges:
                    node = edge.get("node", {}) if isinstance(edge, dict) else {}
                    shortcode = node.get("shortcode", "")
                    if not shortcode:
                        continue
                    
                    # Gunakan /p/ URL untuk post generic (yt-dlp akan coba download)
                    ig_url = f"https://www.instagram.com/p/{shortcode}/"
                    
                    caption = "Instagram Post"
                    caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
                    if caption_edges:
                        raw_caption = caption_edges[0].get("node", {}).get("text", "")
                        if raw_caption:
                            caption = raw_caption[:200] + "..." if len(raw_caption) > 200 else raw_caption
                    
                    results.append({
                        'title': caption,
                        'url': ig_url,
                        'platform': 'instagram'
                    })
                    
                    if len(results) >= limit:
                        break
            
            return results
        
        # ── FORMAT 2: Generic flat list ──
        inner = (data.get("data", None) or data.get("items", None) 
                 or data.get("reels", None) or data.get("result", None) or data)
        
        if isinstance(inner, dict):
            items = (inner.get("items", None) or inner.get("medias", None) 
                     or inner.get("reels", None) or inner.get("data", None) or [])
            if isinstance(items, dict):
                items = items.get("items", items.get("medias", []))
        elif isinstance(inner, list):
            items = inner
    
    if not isinstance(items, list):
        items = []
    
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        vid_url = (item.get("video_url") or item.get("play") 
                   or item.get("url") or item.get("video_play_url"))
        title = (item.get("caption") or item.get("title") 
                 or item.get("text") or item.get("accessibility_caption") 
                 or "Instagram Reel")
        if isinstance(title, dict):
            title = title.get("text", "Instagram Reel")
        if isinstance(title, str) and len(title) > 200:
            title = title[:200] + "..."
        if vid_url:
            results.append({'title': title, 'url': vid_url, 'platform': 'instagram'})
    return results


def _search_instagram_rapidapi(query, limit):
    """Instagram Scraper Stable API (by RockSolid APIs / thetechguy32744).
    
    Verified endpoints (RapidAPI docs):
      1. POST /search_ig.php → Search users + hashtags by keyword
      2. GET  /search_hashtag.php → Get posts & reels from a hashtag
    
    Flow: keyword → search_ig → extract hashtag → search_hashtag → get reels
    Fallback: langsung coba hashtag dari keyword (strip spaces).
    """
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST_IG:
        return []
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST_IG,
    }
    
    # ── TIER A: POST /search_ig.php (search keyword → users + hashtags) ──
    search_url = f"https://{RAPIDAPI_HOST_IG}/search_ig.php"
    try:
        payload = {"search_query": query}
        headers_post = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(search_url, headers=headers_post, data=payload, timeout=15)
        
        if response.status_code == 429:
            logging.warning("RapidAPI IG rate-limited (429) pada /search_ig.php. Kuota habis.")
        elif response.status_code == 403:
            logging.warning("RapidAPI IG 403 pada /search_ig.php — cek subscription.")
        elif response.ok:
            data = response.json()
            # Coba ekstrak video langsung dari search results
            results = _extract_ig_items(data, limit)
            if results:
                logging.info(f"RapidAPI IG berhasil via /search_ig.php ({len(results)} video)")
                return results
            
            # Kalau tidak ada video langsung, cari hashtag dari hasil search
            # lalu pakai /search_hashtag.php untuk ambil reels
            hashtags = []
            if isinstance(data, dict):
                ht_data = data.get("data", data).get("hashtags", data.get("hashtags", []))
                if isinstance(ht_data, list):
                    for ht in ht_data:
                        if isinstance(ht, dict):
                            name = ht.get("name", ht.get("hashtag", ""))
                            if name:
                                hashtags.append(name.lstrip("#"))
            
            if hashtags:
                logging.info(f"RapidAPI IG: ditemukan hashtag dari search: {hashtags[:3]}")
                # Ambil reels dari hashtag pertama
                ht_results = _search_ig_hashtag(hashtags[0], limit, headers)
                if ht_results:
                    return ht_results
        else:
            logging.warning(f"RapidAPI IG /search_ig.php status {response.status_code}: {response.text[:200]}")
    except Exception as e:
        logging.warning(f"RapidAPI IG Error pada /search_ig.php: {e}")
    
    # ── TIER B: GET /search_hashtag.php (langsung dari keyword) ──
    # Buat hashtag dari keyword: "AI Tips" → "aitips"
    hashtag_guess = query.lower().replace(" ", "").replace("-", "")
    logging.info(f"RapidAPI IG: fallback hashtag search dengan '{hashtag_guess}'")
    ht_results = _search_ig_hashtag(hashtag_guess, limit, headers)
    if ht_results:
        return ht_results
    
    # Coba juga keyword asli tanpa modifikasi (kadang hashtag ada spasinya)
    if " " not in query:
        pass  # sudah dicoba di atas
    else:
        # Coba kata pertama saja
        first_word = query.split()[0].lower()
        ht_results = _search_ig_hashtag(first_word, limit, headers)
        if ht_results:
            return ht_results
    
    logging.error(
        "RapidAPI IG: semua endpoint gagal. "
        "Pastikan sudah subscribe di https://rapidapi.com dan kuota belum habis."
    )
    return []


def _search_ig_hashtag(hashtag, limit, headers):
    """Helper: GET /search_hashtag.php — ambil posts & reels dari hashtag."""
    host = headers.get("x-rapidapi-host", RAPIDAPI_HOST_IG)
    url = f"https://{host}/search_hashtag.php"
    params = {"hashtag": hashtag}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 429:
            logging.warning(f"RapidAPI IG rate-limited (429) pada /search_hashtag.php?hashtag={hashtag}")
            return []
        if response.status_code == 403:
            logging.warning(f"RapidAPI IG 403 pada /search_hashtag.php — cek subscription.")
            return []
            
        response.raise_for_status()
        data = response.json()
        
        results = _extract_ig_items(data, limit)
        if results:
            logging.info(f"RapidAPI IG berhasil via /search_hashtag.php?hashtag={hashtag} ({len(results)} video)")
        return results
    except Exception as e:
        logging.warning(f"RapidAPI IG hashtag search error: {e}")
        return []


def search_videos(keyword, platform='youtube', limit=10, content_type=None):
    """
    Mencari video via YouTube search (ytsearch) untuk SEMUA platform.
    
    Kenapa YouTube search untuk semua?
    → yt-dlp HANYA mendukung native search di YouTube.
      Instagram, TikTok, Facebook tidak punya fitur search di yt-dlp
      (butuh cookies + extractor sering rusak).
    → Konten yang ditemukan di YouTube tetap bisa di-download & di-reupload
      ke platform target manapun.
    → Query disesuaikan per platform (shorts/vertical untuk IG & TikTok, 
      viral untuk FB) agar konten yang ditemukan relevan.
    
    Args:
        keyword: Kata kunci pencarian
        platform: Platform target (menentukan style query)
        limit: Jumlah hasil
        content_type: Tipe konten dari dropdown UI
    """
    results = []
    
    # Clean query khusus untuk RapidAPI native search 
    # (tanpa atribut ytsearch: dan tanpa atribut platform style bawaan yt-dlp)
    modifier_str = _get_modifier_str(content_type)
    clean_rapidapi_query = f"{keyword} {modifier_str}".strip()
    
    search_query = _build_remix_query(keyword, platform, limit, content_type)
    
    # ── TIER 1: RAPIDAPI SCRAPERS ──
    if platform == "tiktok":
        logging.info(f"Mencoba TikTok RapidAPI (Query: '{clean_rapidapi_query}')...")
        results = _search_tiktok_rapidapi(clean_rapidapi_query, limit)
    elif platform == "facebook":
        logging.info(f"Mencoba Facebook RapidAPI (Query: '{clean_rapidapi_query}')...")
        results = _search_facebook_rapidapi(clean_rapidapi_query, limit)
    elif platform == "instagram":
        logging.info(f"Mencoba Instagram RapidAPI (Query: '{clean_rapidapi_query}')...")
        results = _search_instagram_rapidapi(clean_rapidapi_query, limit)
        
    if results:
        logging.info(f"Berhasil mendapat {len(results)} video via RapidAPI Spesialis!")
        return results
        
    logging.warning(f"[{platform}] RapidAPI kosong/error (atau KEY belum diset). Fallback ke yt-dlp YouTube Search...")
    
    # ── TIER 2: FALLBACK YT-DLP YOUTUBE SEARCH ──
    ydl_opts = get_base_ydl_opts(download=False)
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            
            if info and 'entries' in info:
                for entry in info['entries']:
                    if not entry:
                        continue
                    
                    vid_url = entry.get('url') or entry.get('webpage_url')
                    
                    # YouTube search: kalau cuma dapet ID, ubah ke full URL
                    if vid_url and not vid_url.startswith('http'):
                        vid_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                        
                    if vid_url:
                        results.append({
                            'title': entry.get('title', 'Unknown Title'),
                            'url': vid_url,
                            'platform': platform
                        })
    except yt_dlp.utils.DownloadError as e:
        error_str = str(e)
        if any(kw in error_str.lower() for kw in ['cookie', 'login', 'sign in', 'authentication']):
            logging.error(
                f"[{platform}] ⚠ YouTube meminta autentikasi! "
                f"Siapkan cookies.txt dari browser. "
                f"Lihat: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp | Detail: {e}"
            )
        else:
            logging.error(f"Error saat search fallback [{platform}]: {e}")
    except Exception as e:
        logging.error(f"Error Tak Terduga (Search Fallback {platform}): {e}")
        
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
        # FFmpeg TIDAK tersedia: gunakan format single-stream pre-merged ('b')
        ydl_opts['format'] = 'b[ext=mp4]/b'
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
