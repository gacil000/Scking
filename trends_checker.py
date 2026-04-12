import requests
import json
import logging
from pytrends.request import TrendReq
from config import RAPIDAPI_KEY, RAPIDAPI_HOST_TRENDS

logger = logging.getLogger(__name__)


def sanitize_keyword(keyword, content_type_str, is_custom=False):
    """
    Menyiapkan string final yang akan dicek ke Google Trends.
    Mitigasi Kueri Terlalu Panjang / Edge Cases.
    """
    if is_custom:
        # Jika custom keyword terdiri dari lebih dari 2 kata,
        # kita anggap itu kalimat spesifik dan JANGAN tambahkan tipe konten
        # agar tidak di-score 0 mutlak oleh Google Trends.
        words = keyword.split()
        if len(words) > 2:
            return " ".join(words[:5])  # Potong max 5 kata agar tidak 400 Bad Request
        else:
            final_str = f"{keyword} {content_type_str}"
    else:
        final_str = f"{keyword} {content_type_str}"
    
    # Ambil maksimal 5 kata inti
    final_words = final_str.strip().split()
    return " ".join(final_words[:5])


def _fetch_rapidapi(query):
    """
    Layer 1: Ambil data SEO dari RapidAPI 
    Target Provider: "Google Keyword Insight" (by Hexaplay)
    """
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST_TRENDS:
        logger.warning("RAPIDAPI_KEY atau HOST kosong, loncat ke Fallback pytrends.")
        return None
        
    url = f"https://{RAPIDAPI_HOST_TRENDS}/keysuggest"
    # Endpoint Hexaplay biasanya membutuhkan seed keyword
    querystring = {"keyword": query, "country": "id", "language": "id"}
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST_TRENDS
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Mengakomodir jika response JSON berbentuk list [...] atau dict {...}
        if isinstance(data, list):
            items = data
        else:
            items = data.get("data", [])
        
        if items and isinstance(items, list):
            # Asumsi items[0] adalah keyword pencocokan pertama
            first_match = items[0]
            
            # API google-keyword-insight1 menggunakan key 'volume', API lain pakai 'search_volume' / 'sv'
            search_volume = first_match.get("volume", first_match.get("search_volume", first_match.get("sv", 0)))
            
            # --- KONVERSI SEARCH VOLUME KE SKOR TREND (0-100) ---
            # Asumsi: > 10.000 pencarian/bulan = Skor 100 (Sangat Viral)
            # Maka: (Volume / 100). Misal: 4000 volume = Skor 40.
            score = int(search_volume / 100)
            
            # Cap maksimum 100
            score = min(score, 100)
            return score
            
        return 0
    except requests.exceptions.RequestException as e:
        logger.error(f"RapidAPI (Hexaplay) Request Error: {e}")
        return None
    except Exception as e:
        logger.error(f"RapidAPI (Hexaplay) Parse Error: {e}")
        return None


def _fetch_pytrends(query):
    """Layer 2: Fallback pakai Pytrends lokal (Rawan Blokir)."""
    try:
        # Init pytrends. hl=id-ID (Indonesia), tz=420 (WITA)
        pytrends = TrendReq(hl='id-ID', tz=420, timeout=(10,25))
        pytrends.build_payload([query], cat=0, timeframe='today 1-m', geo='ID')
        
        df = pytrends.interest_over_time()
        if df.empty:
            return 0
            
        # Kolom sesuai query, ambil rata-rata
        mean_score = df[query].mean()
        return int(mean_score)
    except Exception as e:
        logger.error(f"Pytrends Error: {e}")
        return None


def check_trend_score(keyword, content_type_str, is_custom=False):
    """
    Mengecek rata-rata skor Google Trends dalam sebulan terakhir.
    Mengembalikan (score_int, status_str).
    status_str: 'OK_VIRAL', 'GAGAL_VIRAL', 'API_ERROR_FAILSAFE'
    """
    final_query = sanitize_keyword(keyword, content_type_str, is_custom)
    logger.info(f"Cek Google Trends untuk: '{final_query}'")
    
    # 1. Coba RapidAPI
    score = _fetch_rapidapi(final_query)
    source = "RapidAPI"
    
    # 2. Jika gagal, coba Pytrends
    if score is None:
        logger.warning(f"RapidAPI gagal/kosong, pindah ke pytrends untuk '{final_query}'")
        score = _fetch_pytrends(final_query)
        source = "Pytrends"
        
    # 3. Jika gagal semua, Soft-Fail
    if score is None:
        logger.error(f"Semua metode cek Trends DOWN untuk '{final_query}'. Aktifkan Soft-Fail.")
        return 0, 'API_ERROR_FAILSAFE'
        
    logger.info(f"Skor Google Trends ({source}) untuk '{final_query}': {score}/100")
    return score, 'OK'

