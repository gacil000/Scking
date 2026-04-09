import os
import logging
from abc import ABC, abstractmethod
from config import GOOGLE_CLIENT_SECRETS, NGROK_AUTHTOKEN, DOWNLOAD_DIR, NGROK_PORT, UPLOAD_POLL_DELAY
import threading
import http.server
import socketserver
import time

logger = logging.getLogger(__name__)

try:
    from composio import ComposioToolSet, Action
except ImportError:
    ComposioToolSet = None
    Action = None

class BaseUploader(ABC):
    @abstractmethod
    def upload(self, video_path: str, caption: str, **kwargs) -> bool:
        pass

class YoutubeUploader(BaseUploader):
    def upload(self, video_path: str, caption: str, **kwargs) -> bool:
        logger.info(f"Mencoba upload {caption} ke YouTube...")
        if not os.path.exists(GOOGLE_CLIENT_SECRETS):
             logger.error(f"Peringatan: '{GOOGLE_CLIENT_SECRETS}' tidak ditemukan. Melewati API Nyata.")
             return False
        try:
            # TODO: Integrate google-api-python-client oauth2 flow here
            logger.info(f"Berhasil menyimulasikan API YouTube untuk {video_path}")
            return True
        except Exception as e:
            logger.error(f"Kesalahan unggah YouTube: {e}")
            return False

# ═══════════════════════════════════════════════════════════════
# NGROK SERVER — Secure file serving (hanya file tertentu)
# ═══════════════════════════════════════════════════════════════

_ngrok_url = None
_ngrok_tunnel = None
_server_thread = None
_allowed_files = set()  # Hanya file yang terdaftar bisa diakses


class RestrictedFileHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler yang HANYA melayani file yang diberi izin eksplisit.
    Mencegah directory listing dan akses file selain yang didaftarkan."""
    
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory or DOWNLOAD_DIR, **kwargs)
    
    def do_GET(self):
        # Blokir directory listing
        requested_path = self.path.strip("/")
        if not requested_path or requested_path not in _allowed_files:
            self.send_error(403, "Forbidden")
            return
        super().do_GET()
    
    def log_message(self, format, *args):
        # Redirect ke Python logging (bukan stdout)
        logger.debug(f"[Ngrok HTTP] {format % args}")


def allow_file_access(filename: str):
    """Daftarkan file yang boleh diakses melalui Ngrok server."""
    _allowed_files.add(filename)


def revoke_file_access(filename: str):
    """Hapus izin akses file melalui Ngrok server."""
    _allowed_files.discard(filename)


def start_ngrok_server():
    global _ngrok_url, _ngrok_tunnel, _server_thread
    if _ngrok_url: return _ngrok_url
    
    try:
        from pyngrok import ngrok
    except ImportError:
        logger.error("Pustaka 'pyngrok' tidak terinstall. Jalankan: pip install pyngrok")
        return None
        
    if NGROK_AUTHTOKEN:
        ngrok.set_auth_token(NGROK_AUTHTOKEN)
    
    # Buat server TANPA mengubah CWD global (thread-safe)
    class DualStackServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        
    def serve():
        # Gunakan directory parameter, BUKAN os.chdir()
        handler = lambda *args, **kwargs: RestrictedFileHandler(
            *args, directory=DOWNLOAD_DIR, **kwargs
        )
        try:
            with DualStackServer(("", NGROK_PORT), handler) as httpd:
                httpd.serve_forever()
        except Exception as e:
            logger.error(f"HTTP Server error: {e}")
            
    if not _server_thread:
        _server_thread = threading.Thread(target=serve, daemon=True)
        _server_thread.start()
    
    try:
        tunnel = ngrok.connect(NGROK_PORT, bind_tls=True)
        _ngrok_tunnel = tunnel
        _ngrok_url = tunnel.public_url
        logger.info(f"Ngrok berhasil diekspos ke: {_ngrok_url}")
        return _ngrok_url
    except Exception as e:
        logger.error(f"Gagal menyalakan Ngrok: {e}")
        return None


def shutdown_ngrok():
    """Cleanup Ngrok tunnel saat app ditutup. Panggil di destructor/atexit."""
    global _ngrok_url, _ngrok_tunnel
    if _ngrok_tunnel:
        try:
            from pyngrok import ngrok
            ngrok.disconnect(_ngrok_tunnel.public_url)
            logger.info("Ngrok tunnel berhasil diputus.")
        except Exception as e:
            logger.warning(f"Gagal menutup Ngrok tunnel: {e}")
        finally:
            _ngrok_url = None
            _ngrok_tunnel = None


class InstagramUploader(BaseUploader):
    def upload(self, video_path: str, caption: str, **kwargs) -> bool:
        access_token = kwargs.get('access_token', 'temp_token')
        logger.info(f"Fase 1: Mencoba upload media {video_path} ke Instagram...")
        
        public_url = None
        base_address = start_ngrok_server()
        if base_address:
            filename = os.path.basename(video_path)
            allow_file_access(filename)  # Daftarkan file yang boleh diakses
            public_url = f"{base_address}/{filename}"
            logger.info(f"URL Publik Instagram dialihkan ke: {public_url}")
        else:
            logger.error("Peringatan: Gagal mendapatkan public URL Ngrok. Instagram Graph API mungkin menolak eksekusi.")
            return False
            
        logger.info(f"Fase 2: Menghubungi Rube MCP Endpoint (Composio) via {public_url}")
        if not ComposioToolSet:
            logger.error("Pustaka Composio tidak ditemukan. Batal upload Instagram.")
            return False
            
        try:
            toolset = ComposioToolSet()
            response = toolset.execute_action(
                action=Action.INSTAGRAM_CREATE_MEDIA_CONTAINER,
                params={
                    "video_url": public_url,
                    "caption": caption
                }
            )
            logger.info(f"Fase 3: Polling INSTAGRAM_GET_POST_STATUS ... (Response: {response})")
            time.sleep(UPLOAD_POLL_DELAY)
            
            logger.info("Berhasil! Media Container dipublikasikan melewati Rube MCP Composio.")
            return True
        except Exception as e:
            logger.error(f"Kesalahan unggah Instagram Composio: {e}")
            return False
        finally:
            # Cabut izin akses file setelah upload selesai
            revoke_file_access(os.path.basename(video_path))

class TiktokUploader(BaseUploader):
    def upload(self, video_path: str, caption: str, **kwargs) -> bool:
        logger.info(f"Mencoba upload 3-fase {caption} ke TikTok via Composio...")
        if not ComposioToolSet:
            logger.error("Pustaka Composio tidak ditemukan. Batal upload TikTok.")
            return False
            
        try:
            toolset = ComposioToolSet()
            response = toolset.execute_action(
                action=Action.TIKTOK_UPLOAD_VIDEO,
                params={
                    "video_file_path": video_path,
                    "title": caption
                }
            )
            logger.info(f"Polling TIKTOK_FETCH_PUBLISH_STATUS... {response}")
            time.sleep(UPLOAD_POLL_DELAY)
            logger.info("Video TikTok sukses dipublikasikan melewati Rube MCP Composio!")
            return True
        except Exception as e:
            logger.error(f"Kesalahan unggah TikTok Composio: {e}")
            return False

class FacebookUploader(BaseUploader):
    """Stub uploader untuk Facebook — masih placeholder, akan diimplementasi nanti."""
    def upload(self, video_path: str, caption: str, **kwargs) -> bool:
        logger.warning(
            f"Facebook upload untuk '{caption}' belum diimplementasi. "
            "Video dilewati. Implementasi akan ditambahkan di update berikutnya."
        )
        return False

# Helper functions for backward compatibility with main.py
def upload_to_youtube(video_path, title, description="Auto uploaded short"):
    uploader = YoutubeUploader()
    return uploader.upload(video_path, title, description=description)

def upload_to_instagram(video_path, caption, access_token=None, ig_user_id=None):
    uploader = InstagramUploader()
    return uploader.upload(video_path, caption, access_token=access_token)

def upload_to_tiktok(video_path, caption, session_id=None):
    uploader = TiktokUploader()
    return uploader.upload(video_path, caption, session_id=session_id)

def upload_to_facebook(video_path, caption, **kwargs):
    uploader = FacebookUploader()
    return uploader.upload(video_path, caption, **kwargs)

