import logging
from config import OPENAI_API_KEY, GEMINI_API_KEY, CAPTION_MAX_TOKENS

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration (API keys, etc.) is missing or invalid."""
    pass


def generate_caption(title: str, platform: str, provider: str = "gemini") -> str:
    """
    Generates a viral caption using the specified LLM provider based on social-content skill formulas.
    
    Raises:
        ConfigurationError: Jika API key tidak dikonfigurasi.
        ValueError: Jika provider tidak didukung.
    """
    if provider == "openai":
        return _generate_with_openai(title, platform)
    elif provider == "gemini":
        return _generate_with_gemini(title, platform)
    else:
        raise ValueError(f"Provider LLM '{provider}' tidak didukung. Gunakan 'openai' atau 'gemini'.")

def _get_prompt(title: str, platform: str) -> str:
    return f"""Kamu adalah ahli Social Media Marketing (setara skill 'social-content').
Tugasmu adalah menulis ulang judul video asli ini: '{title}'
Menjadi sebuah caption viral untuk platform {platform.upper()}.
Gunakan format 'Curiosity Hook' atau 'Value Hook'.
Tambahkan 3-5 hashtag yang sangat relevan.
Jangan terlalu panjang, buat natural dan mengundang komentar!
PENTING: Langsung tuliskan caption-nya sekarang tanpa basa-basi!"""

def _generate_with_openai(title: str, platform: str) -> str:
    if not OPENAI_API_KEY:
        raise ConfigurationError(
            "OPENAI_API_KEY tidak dikonfigurasi di .env. "
            "Isi terlebih dahulu atau gunakan provider lain."
        )
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a viral social media strategist."},
                {"role": "user", "content": _get_prompt(title, platform)}
            ],
            max_tokens=CAPTION_MAX_TOKENS,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        raise

def _generate_with_gemini(title: str, platform: str) -> str:
    if not GEMINI_API_KEY:
        raise ConfigurationError(
            "GEMINI_API_KEY tidak dikonfigurasi di .env. "
            "Isi terlebih dahulu atau gunakan provider lain."
        )
        
    try:
        from google import genai
        # Menggunakan SDK baru `google.genai` karena `google.generativeai` telah deprecated
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=_get_prompt(title, platform),
            config=genai.types.GenerateContentConfig(
                max_output_tokens=CAPTION_MAX_TOKENS,
                temperature=0.7,
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        raise
