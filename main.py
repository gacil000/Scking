from config import (setup_logging, ensure_directories, COOKIES_FILE, DOWNLOAD_DIR,
                    OPENAI_API_KEY, GEMINI_API_KEY, MAX_WORKERS, TITLE_TRUNCATE_LEN, SEARCH_OVERFETCH)
from content_generator import generate_caption
import customtkinter as ctk
import threading
import concurrent.futures
import logging
import time
import os
import random
import atexit
from datetime import datetime
import tkinter.messagebox as messagebox
from database import get_db, Video, init_db
from scraper import search_videos, download_video
from uploader import (upload_to_youtube, upload_to_instagram, upload_to_tiktok,
                      upload_to_facebook, shutdown_ngrok)
from video_editor import process_video_for_reupload

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ═══════════════════════════════════════════════════════════════
# PRESET DATA — Dropdown options
# ═══════════════════════════════════════════════════════════════

NICHE_OPTIONS = [
    "Gaming",
    "Kucing / Hewan",
    "Masak / Resep",
    "Fitness / Gym",
    "Comedy / Lucu",
    "Edukasi",
    "Musik",
    "Otomotif",
    "Travel",
    "Fashion / OOTD",
    "Teknologi",
    "Horror / Misteri",
    "Motivasi",
    "Life Hack",
    "Custom...",
]

CONTENT_TYPES = [
    "Kompilasi",
    "Remix",
    "Funny Moments",
    "Best Moments",
    "Highlights",
    "Meme",
    "Tips & Tricks",
    "Random (Acak)",
]

LIMIT_OPTIONS = ["5", "10", "15", "20", "30", "50"]

# Warna tema per platform
PLATFORM_COLORS = {
    "youtube":   {"accent": "#FF0000", "hover": "#CC0000", "badge": "#FF4444"},
    "instagram": {"accent": "#E1306C", "hover": "#C13584", "badge": "#F77737"},
    "facebook":  {"accent": "#1877F2", "hover": "#145DBF", "badge": "#42B72A"},
    "tiktok":    {"accent": "#00F2FE", "hover": "#00D2D3", "badge": "#EE1D52"},
}

PLATFORM_ICONS = {
    "youtube":   "▶  YouTube",
    "instagram": "📷  Instagram",
    "facebook":  "📘  Facebook",
    "tiktok":    "🎵  TikTok",
}


# ═══════════════════════════════════════════════════════════════
# PlatformTab — Widget reusable per platform
# ═══════════════════════════════════════════════════════════════

class PlatformTab:
    """
    Kelas independen untuk setiap tab platform.
    Setiap instance memiliki kontrol, tabel, status, dan thread sendiri.
    Mendukung multitasking penuh antar tab.
    """
    
    def __init__(self, parent_frame, platform_name, app_ref):
        self.parent = parent_frame
        self.platform = platform_name  # 'youtube', 'instagram', 'facebook'
        self.app = app_ref
        self.colors = PLATFORM_COLORS[platform_name]
        
        # State per-tab (terisolasi)
        self.table_widgets = {}
        self.status_labels_map = {}
        self.current_row = 1
        self.is_busy = False  # Flag untuk mencegah double-click
        
        self._build_ui()
        self._load_existing_data()
    
    def _build_ui(self):
        """Membangun seluruh UI untuk satu tab platform"""
        # ── Container utama ──
        self.parent.grid_columnconfigure(0, weight=1)
        self.parent.grid_rowconfigure(1, weight=1)
        
        # ══════════════════════════════════════════
        # CONTROL PANEL (Baris atas)
        # ══════════════════════════════════════════
        ctrl_frame = ctk.CTkFrame(self.parent, fg_color=("gray92", "gray17"), corner_radius=12)
        ctrl_frame.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        ctrl_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # ── Row 0: Dropdowns ──
        # Niche
        niche_container = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        niche_container.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        ctk.CTkLabel(niche_container, text="📂 Niche", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w")
        self.niche_var = ctk.StringVar(value="Gaming")
        self.niche_dropdown = ctk.CTkOptionMenu(
            niche_container, variable=self.niche_var, values=NICHE_OPTIONS,
            width=160, dynamic_resizing=False,
            fg_color=self.colors["accent"], button_color=self.colors["hover"],
            command=self._on_niche_changed
        )
        self.niche_dropdown.pack(fill="x", pady=(2, 0))
        
        # Custom keyword entry (hidden by default)
        self.custom_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        self.custom_frame.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        self.custom_label = ctk.CTkLabel(self.custom_frame, text="✏️ Keyword Custom", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray")
        self.custom_entry = ctk.CTkEntry(self.custom_frame, placeholder_text="Ketik keyword...", width=160)
        # Hidden awalnya
        self.custom_visible = False
        
        # Tipe Konten
        type_container = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        type_container.grid(row=0, column=2, padx=10, pady=8, sticky="ew")
        ctk.CTkLabel(type_container, text="🎬 Tipe Konten", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w")
        self.content_type_var = ctk.StringVar(value="Kompilasi")
        self.content_type_dropdown = ctk.CTkOptionMenu(
            type_container, variable=self.content_type_var, values=CONTENT_TYPES,
            width=140, dynamic_resizing=False,
            fg_color="gray30", button_color="gray40",
        )
        self.content_type_dropdown.pack(fill="x", pady=(2, 0))
        
        # Limit
        limit_container = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        limit_container.grid(row=0, column=3, padx=10, pady=8, sticky="ew")
        ctk.CTkLabel(limit_container, text="🔢 Jumlah", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w")
        self.limit_var = ctk.StringVar(value="10")
        self.limit_dropdown = ctk.CTkOptionMenu(
            limit_container, variable=self.limit_var, values=LIMIT_OPTIONS,
            width=80, dynamic_resizing=False,
            fg_color="gray30", button_color="gray40",
        )
        self.limit_dropdown.pack(fill="x", pady=(2, 0))
        
        # ── Row 1: AI & Scheduling ──
        self.ai_sched_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        self.ai_sched_frame.grid(row=1, column=0, columnspan=4, padx=10, pady=(10, 0), sticky="ew")
        
        ctk.CTkLabel(self.ai_sched_frame, text="✨ AI Caption:", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(side="left", padx=(0, 5))
        self.ai_options = ["None"]
        if GEMINI_API_KEY: self.ai_options.append("Gemini")
        if OPENAI_API_KEY: self.ai_options.append("OpenAI")
        
        self.ai_combo = ctk.CTkComboBox(self.ai_sched_frame, values=self.ai_options, width=120)
        self.ai_combo.set("None")
        self.ai_combo.pack(side="left", padx=(0, 15))
        
        if len(self.ai_options) == 1:
            self.ai_combo.configure(state="disabled")
            # Bind wrapper to inform user when clicked disabled
            self.ai_combo._canvas.bind("<Button-1>", lambda e: messagebox.showwarning("API Key Kosong", "Isi GEMINI_API_KEY atau OPENAI_API_KEY di .env!"))
            
        ctk.CTkLabel(self.ai_sched_frame, text="⏱ Delay Upload (menit):", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(side="left", padx=(0, 5))
        self.delay_entry = ctk.CTkEntry(self.ai_sched_frame, width=60)
        self.delay_entry.insert(0, "0")
        self.delay_entry.pack(side="left")
        
        # Checkbox Anti-Copyright
        self.moviepy_var = ctk.BooleanVar(value=False)
        self.moviepy_checkbox = ctk.CTkCheckBox(
            self.ai_sched_frame, text="🛡 Filter Anti-Copyright", 
            variable=self.moviepy_var, font=ctk.CTkFont(size=11, weight="bold")
        )
        self.moviepy_checkbox.pack(side="left", padx=(15, 0))
        
        # Checkbox Auto-Cleanup Disk
        self.cleanup_var = ctk.BooleanVar(value=False)
        self.cleanup_checkbox = ctk.CTkCheckBox(
            self.ai_sched_frame, text="🧹 Auto-Cleanup", 
            variable=self.cleanup_var, font=ctk.CTkFont(size=11, weight="bold")
        )
        self.cleanup_checkbox.pack(side="left", padx=(10, 0))
        
        # ── Row 2: Action Buttons ──
        btn_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=4, padx=10, pady=(8, 10), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        self.search_btn = ctk.CTkButton(
            btn_frame, text="🔍  Cari Video", 
            command=self.on_search, height=36,
            fg_color=self.colors["accent"], hover_color=self.colors["hover"],
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.search_btn.grid(row=0, column=0, padx=4, sticky="ew")
        
        self.download_btn = ctk.CTkButton(
            btn_frame, text="⬇  Download", 
            command=self.on_download, height=36,
            fg_color="#2ECC71", hover_color="#27AE60",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.download_btn.grid(row=0, column=1, padx=4, sticky="ew")
        
        self.upload_btn = ctk.CTkButton(
            btn_frame, text="⬆  Upload", 
            command=self.on_upload, height=36,
            fg_color="#F39C12", hover_color="#E67E22",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.upload_btn.grid(row=0, column=2, padx=4, sticky="ew")
        
        self.clear_btn = ctk.CTkButton(
            btn_frame, text="🗑  Hapus", 
            command=self.on_clear, height=36,
            fg_color="#E74C3C", hover_color="#C0392B",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.clear_btn.grid(row=0, column=3, padx=4, sticky="ew")
        
        # ══════════════════════════════════════════
        # VIDEO TABLE (Area tengah - scrollable)
        # ══════════════════════════════════════════
        self.table_frame = ctk.CTkScrollableFrame(
            self.parent, fg_color=("gray95", "gray14"), corner_radius=12,
            label_text=f"📋 Daftar Video — {self.platform.upper()}", 
            label_font=ctk.CTkFont(size=12, weight="bold"),
            label_fg_color=self.colors["accent"],
        )
        self.table_frame.grid(row=1, column=0, padx=12, pady=6, sticky="nsew")
        self.table_frame.grid_columnconfigure(1, weight=1)
        
        # Header row
        headers = [("No", 40), ("Judul", 420), ("Status", 110)]
        for col, (text, width) in enumerate(headers):
            lbl = ctk.CTkLabel(
                self.table_frame, text=text, width=width,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.colors["badge"],
            )
            lbl.grid(row=0, column=col, padx=6, pady=6, sticky="w" if col == 1 else "")
        
        # Separator
        sep = ctk.CTkFrame(self.table_frame, height=2, fg_color=self.colors["accent"])
        sep.grid(row=0, column=0, columnspan=3, padx=4, pady=(28, 0), sticky="ew")
        
        # ══════════════════════════════════════════
        # STATUS BAR (Baris bawah)
        # ══════════════════════════════════════════
        status_frame = ctk.CTkFrame(self.parent, fg_color=("gray92", "gray17"), corner_radius=12, height=40)
        status_frame.grid(row=2, column=0, padx=12, pady=(6, 12), sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(
            status_frame, text="⏸ Status: Menunggu perintah...", 
            font=ctk.CTkFont(size=12), text_color="cyan",
            anchor="w"
        )
        self.status_label.grid(row=0, column=0, padx=14, pady=8, sticky="w")
        
        # Busy indicator
        self.busy_indicator = ctk.CTkLabel(
            status_frame, text="", font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.busy_indicator.grid(row=0, column=1, padx=14, pady=8, sticky="e")
        
        # Progress bar (hidden by default)
        self.progress_bar = ctk.CTkProgressBar(
            status_frame, width=200, height=12,
            progress_color=self.colors["accent"],
            fg_color="gray25",
        )
        self.progress_bar.grid(row=0, column=2, padx=(0, 14), pady=8, sticky="e")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()  # Hidden awalnya
        
        # Progress label (e.g. "3/10")
        self.progress_label = ctk.CTkLabel(
            status_frame, text="", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.colors["badge"]
        )
        self.progress_label.grid(row=0, column=3, padx=(0, 14), pady=8, sticky="e")
        self.progress_label.grid_remove()
    
    # ─────────────── UI Helpers ───────────────
    
    def _on_niche_changed(self, value):
        """Show/hide custom keyword entry based on dropdown selection"""
        if value == "Custom...":
            if not self.custom_visible:
                self.custom_label.pack(anchor="w")
                self.custom_entry.pack(fill="x", pady=(2, 0))
                self.custom_visible = True
        else:
            if self.custom_visible:
                self.custom_label.pack_forget()
                self.custom_entry.pack_forget()
                self.custom_visible = False
    
    def _get_keyword(self):
        """Mendapatkan keyword dari dropdown atau custom entry"""
        niche = self.niche_var.get()
        if niche == "Custom...":
            keyword = self.custom_entry.get().strip()
            if not keyword:
                self.set_status("❌ Error: Keyword custom kosong!", True)
                return None
            if len(keyword) > 100:
                self.set_status("❌ Error: Keyword terlalu panjang (max 100 karakter)!", True)
                return None
            return keyword
        else:
            return niche.lower().replace(" / ", " ").replace(" / ", " ")
    
    def set_status(self, text, is_error=False):
        ts = datetime.now().strftime("%H:%M:%S")
        display = f"[{ts}] {text}"
        color = "#FF6B6B" if is_error else "#00D2FF"
        try:
            self.status_label.configure(text=display, text_color=color)
            if is_error:
                logging.error(f"[{self.platform}] {text}")
            else:
                logging.info(f"[{self.platform}] {text}")
        except Exception as e:
            logging.debug(f"[{self.platform}] UI update skipped: {e}")
    
    def _set_busy(self, busy, action_text=""):
        """Toggle busy state — disable/enable buttons with visual feedback"""
        self.is_busy = busy
        state = "disabled" if busy else "normal"
        try:
            self.search_btn.configure(state=state, text="⏳ Memproses..." if busy else "🔍  Cari Video")
            self.download_btn.configure(state=state, text="⏳ Memproses..." if busy else "⬇  Download")
            self.upload_btn.configure(state=state, text="⏳ Memproses..." if busy else "⬆  Upload")
            self.clear_btn.configure(state=state)
            self.busy_indicator.configure(text=f"⏳ {action_text}" if busy else "")
            
            # Show/hide progress bar
            if busy:
                self.progress_bar.set(0)
                self.progress_bar.grid()
                self.progress_label.grid()
            else:
                self.progress_bar.grid_remove()
                self.progress_label.grid_remove()
        except Exception as e:
            logging.debug(f"[{self.platform}] Busy toggle skipped: {e}")
    
    def _update_progress(self, current, total):
        """Update progress bar dan label"""
        try:
            progress = current / total if total > 0 else 0
            self.progress_bar.set(progress)
            self.progress_label.configure(text=f"{current}/{total}")
        except Exception:
            pass
    
    def render_row(self, vid):
        """Membuat baris UI tunggal"""
        row = self.current_row
        
        id_lbl = ctk.CTkLabel(self.table_frame, text=str(vid.id), width=40, font=ctk.CTkFont(size=11))
        id_lbl.grid(row=row, column=0, padx=6, pady=4)
        
        title_text = (vid.title or "Untitled")[:TITLE_TRUNCATE_LEN]
        if len(vid.title or "") > TITLE_TRUNCATE_LEN:
            title_text += "..."
        title_lbl = ctk.CTkLabel(
            self.table_frame, text=title_text, width=420, anchor="w",
            font=ctk.CTkFont(size=11), wraplength=400,
        )
        title_lbl.grid(row=row, column=1, padx=6, pady=4, sticky="w")
        
        status_color, status_icon = self._status_style(vid.status)
        status_lbl = ctk.CTkLabel(
            self.table_frame, text=f"{status_icon} {vid.status}", width=110,
            text_color=status_color, font=ctk.CTkFont(size=11, weight="bold"),
        )
        status_lbl.grid(row=row, column=2, padx=6, pady=4)
        
        self.table_widgets[vid.id] = [id_lbl, title_lbl, status_lbl]
        self.status_labels_map[vid.id] = status_lbl
        self.current_row += 1
    
    @staticmethod
    def _status_style(status):
        if status == 'MUNCUL':
            return "#FF6B6B", "🔴"
        elif status == 'DIUNDUH':
            return "#FFD93D", "🟡"
        elif status == 'DIUNGGAH':
            return "#6BCB77", "🟢"
        return "gray", "⚪"
    
    def refresh_table(self):
        """In-Place Update per platform"""
        with get_db() as db:
            videos = db.query(Video).filter_by(platform=self.platform).all()
            for vid in videos:
                if vid.id in self.status_labels_map:
                    lbl = self.status_labels_map[vid.id]
                    current_text = lbl.cget("text")
                    expected_status = vid.status
                    if expected_status not in current_text:
                        color, icon = self._status_style(expected_status)
                        lbl.configure(text=f"{icon} {expected_status}", text_color=color)
                else:
                    self.render_row(vid)
    
    def clear_ui_table(self):
        for vid_id, widgets in self.table_widgets.items():
            for w in widgets:
                w.destroy()
        self.table_widgets.clear()
        self.status_labels_map.clear()
        self.current_row = 1
    
    def _load_existing_data(self):
        """Load video yang sudah ada di DB untuk platform ini"""
        self.refresh_table()
    
    # ─────────────── Actions ───────────────
    
    def on_search(self):
        if self.is_busy:
            return
        keyword = self._get_keyword()
        if not keyword:
            return
        
        try:
            limit = int(self.limit_var.get())
        except (ValueError, TypeError):
            limit = 10
            self.set_status("⚠ Limit tidak valid, menggunakan default 10.")
        content_type = self.content_type_var.get()
        
        # Cek histori
        with get_db() as db:
            existing_count = db.query(Video).filter_by(platform=self.platform).count()
            if existing_count > 0:
                choice = messagebox.askyesnocancel(
                    f"Video {self.platform.upper()} Sudah Ada",
                    f"Terdapat {existing_count} video {self.platform} lokal.\n\n"
                    "YES: Hapus dan mulai dari nol.\n"
                    "NO: Gabungkan dengan yang ada.\n"
                    "CANCEL: Batalkan."
                )
                if choice is None:
                    return
                elif choice is True:
                    db.query(Video).filter_by(platform=self.platform).delete()
                    self.clear_ui_table()
        
        self._set_busy(True, "Mencari...")
        self.set_status(f"🔍 Mencari '{keyword}' ({content_type})...")
        threading.Thread(
            target=self._search_task, 
            args=(keyword, limit, content_type), 
            daemon=True
        ).start()
    
    def _search_task(self, keyword, limit, content_type):
        try:
            fetch_limit = limit + SEARCH_OVERFETCH
            results = search_videos(
                keyword, platform=self.platform, 
                limit=fetch_limit, content_type=content_type
            )
            
            if not results:
                self.app.after(0, lambda: self.set_status("❌ Tiada hasil ditemukan.", True))
                self.app.after(0, lambda: self._set_busy(False))
                return
            
            # Validasi edge case
            valid_results = [r for r in results if r.get('url') and r.get('title') and r['url'] != 'None']
            if not valid_results:
                self.app.after(0, lambda: self.set_status("❌ Semua hasil invalid.", True))
                self.app.after(0, lambda: self._set_busy(False))
                return
            
            random.shuffle(valid_results)
            
            new_videos = []
            with get_db() as db:
                for info in valid_results:
                    if len(new_videos) >= limit:
                        break
                    existing = db.query(Video).filter_by(url=info['url']).first()
                    if not existing:
                        new_videos.append(Video(
                            title=info['title'],
                            url=info['url'],
                            platform=self.platform,
                        ))
                
                if new_videos:
                    db.add_all(new_videos)
                    db.commit()
                added = len(new_videos)
            
            self.app.after(0, self.refresh_table)
            self.app.after(0, lambda: self.set_status(f"✅ {added} Video berhasil terdata!"))
        except Exception as e:
            logging.error(f"[{self.platform}] Search Error: {e}")
            self.app.after(0, lambda e_s=str(e): self.set_status(f"❌ Error: {e_s[:50]}", True))
        finally:
            self.app.after(0, lambda: self._set_busy(False))
    
    def on_download(self):
        if self.is_busy:
            return
        with get_db() as db:
            count = db.query(Video).filter_by(platform=self.platform, status='MUNCUL').count()
        if count == 0:
            self.set_status("⚠ Tidak ada video untuk didownload.", True)
            return
        
        self._set_busy(True, f"Download {count}...")
        self.set_status(f"⬇ Mengunduh {count} video...")
        threading.Thread(target=self._download_task, daemon=True).start()
    
    def _download_task(self):
        try:
            with get_db() as db:
                videos = db.query(Video).filter_by(platform=self.platform, status='MUNCUL').all()
                vid_data = [(v.id, v.url) for v in videos]
                
            ok, fail = 0, 0
            
            def worker(vid_id, url):
                self.app.after(0, lambda v=vid_id: self.set_status(f"⬇ Mengunduh ID {v}..."))
                try:
                    filepath = download_video(url)
                    return vid_id, filepath
                except Exception as e:
                    logging.error(f"Download crash ID {vid_id}: {e}")
                    return vid_id, None

            # Download paralel dengan progress counter
            total = len(vid_data)
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(worker, v_id, v_url): v_id for v_id, v_url in vid_data}
                
                for future in concurrent.futures.as_completed(futures):
                    try:
                        v_id, filepath = future.result()
                    except Exception as e:
                        logging.error(f"Future download error: {e}")
                        fail += 1
                        continue
                    with get_db() as db:
                        vid = db.get(Video, v_id)
                        if vid and filepath and os.path.exists(filepath):
                            vid.status = 'DIUNDUH'
                            vid.filepath = filepath
                            ok += 1
                        else:
                            fail += 1
                        db.commit()
                    self.app.after(0, self.refresh_table)
                    self.app.after(0, lambda o=ok, f=fail, t=total: self._update_progress(o+f, t))
            
            msg = f"✅ Download selesai! ({ok} OK" + (f", {fail} gagal)" if fail else ")")
            self.app.after(0, lambda: self.set_status(msg, is_error=(fail > 0)))
        except Exception as e:
            logging.error(f"[{self.platform}] Download Error: {e}")
            self.app.after(0, lambda: self.set_status(f"❌ Error download: {str(e)[:50]}", True))
        finally:
            self.app.after(0, lambda: self._set_busy(False))
    
    def on_upload(self):
        if self.is_busy:
            return
        with get_db() as db:
            count = db.query(Video).filter_by(platform=self.platform, status='DIUNDUH').count()
        if count == 0:
            self.set_status("⚠ Belum ada video berstatus DIUNDUH.", True)
            return
        
        # Confirmation dialog
        ai_mode = self.ai_combo.get()
        use_filter = "🛡 Anti-Copyright ON" if self.moviepy_var.get() else "❌ Anti-Copyright OFF"
        cleanup = "🧹 Auto-cleanup ON" if self.cleanup_var.get() else ""
        
        summary = (
            f"Upload {count} video ke {self.platform.upper()}\n\n"
            f"• AI Caption: {ai_mode}\n"
            f"• {use_filter}\n"
            + (f"• {cleanup}\n" if cleanup else "")
            + f"\nLanjutkan?"
        )
        if not messagebox.askyesno(f"Konfirmasi Upload {self.platform.upper()}", summary):
            return
        
        self._set_busy(True, f"Upload {count}...")
        self.set_status(f"⬆ Mengupload {count} video...")
        threading.Thread(target=self._upload_task, daemon=True).start()
    
    def _upload_task(self):
        try:
            with get_db() as db:
                videos = db.query(Video).filter_by(platform=self.platform, status='DIUNDUH').all()
                vid_data = [(v.id, v.filepath, v.title) for v in videos]
                
            ok, fail = 0, 0
            selected_ai = self.ai_combo.get()
            use_moviepy = self.moviepy_var.get()
            auto_cleanup = self.cleanup_var.get()
            
            try:
                delay_mins = int(self.delay_entry.get())
                if delay_mins < 0:
                    delay_mins = 0
            except (ValueError, TypeError):
                delay_mins = 0
            
            def worker(vid_id, filepath, original_title):
                if delay_mins > 0:
                    self.app.after(0, lambda v=vid_id: self.set_status(f"🕰 Delay ID {v} ({delay_mins}m)..."))
                    time.sleep(delay_mins * 60)
                
                # --- Video Editor Anti-Copyright ---
                final_filepath = filepath
                if use_moviepy:
                    self.app.after(0, lambda v=vid_id: self.set_status(f"🛡 Proses Filter ID {v}..."))
                    try:
                        final_filepath = process_video_for_reupload(filepath)
                    except Exception as e:
                        logging.error(f"Video Editor Error ID {vid_id}: {e}")
                        
                self.app.after(0, lambda v=vid_id: self.set_status(f"⬆ Upload ID {v}..."))
                
                # Gunakan AI Generator jika dipilih
                final_caption = original_title
                llm_used = None
                if selected_ai != "None":
                    try:
                        self.app.after(0, lambda v=vid_id: self.set_status(f"🤖 AI Generating ID {v}..."))
                        final_caption = generate_caption(original_title, self.platform, selected_ai.lower())
                        llm_used = selected_ai.lower()
                    except Exception as e:
                        logging.error(f"AI Generator Error ID {vid_id}: {e}")
                        
                try:
                    if self.platform == 'youtube':
                        success = upload_to_youtube(final_filepath, final_caption)
                    elif self.platform == 'instagram':
                        success = upload_to_instagram(final_filepath, final_caption)
                    elif self.platform == 'tiktok':
                        success = upload_to_tiktok(final_filepath, final_caption)
                    elif self.platform == 'facebook':
                        success = upload_to_facebook(final_filepath, final_caption)
                    else:
                        logging.warning(f"Platform '{self.platform}' tidak dikenali, skip upload.")
                        success = False
                        
                    return vid_id, success, final_caption, llm_used, final_filepath
                except Exception as e:
                    logging.error(f"Upload crash ID {vid_id}: {e}")
                    return vid_id, False, final_caption, llm_used, final_filepath

            # Upload paralel dengan progress counter
            total = len(vid_data)
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(worker, v_id, v_filepath, v_title): v_id for v_id, v_filepath, v_title in vid_data}
                
                for future in concurrent.futures.as_completed(futures):
                    try:
                        v_id, success, caption, llm_prov, final_path = future.result()
                    except Exception as e:
                        logging.error(f"Future upload error: {e}")
                        fail += 1
                        continue
                    with get_db() as db:
                        vid = db.get(Video, v_id)
                        if vid and success:
                            vid.status = 'DIUNGGAH'
                            vid.generated_caption = caption
                            vid.llm_provider = llm_prov
                            ok += 1
                            
                            # Auto-cleanup: hapus file setelah upload berhasil
                            if auto_cleanup and vid.filepath:
                                for fpath in set([vid.filepath, final_path]):
                                    if fpath and os.path.exists(fpath):
                                        try:
                                            os.remove(fpath)
                                            logging.info(f"Cleanup: {fpath} dihapus.")
                                        except OSError as e:
                                            logging.warning(f"Cleanup gagal: {e}")
                        else:
                            fail += 1
                        db.commit()
                    self.app.after(0, self.refresh_table)
                    self.app.after(0, lambda o=ok, f=fail, t=total: self._update_progress(o+f, t))
            
            msg = f"✅ Upload selesai! ({ok} OK" + (f", {fail} gagal)" if fail else ")")
            self.app.after(0, lambda: self.set_status(msg, is_error=(fail > 0)))
        except Exception as e:
            logging.error(f"[{self.platform}] Upload Error: {e}")
            self.app.after(0, lambda: self.set_status(f"❌ Error upload: {str(e)[:50]}", True))
        finally:
            self.app.after(0, lambda: self._set_busy(False))
    
    def on_clear(self):
        if self.is_busy:
            return
        with get_db() as db:
            count = db.query(Video).filter_by(platform=self.platform).count()
        if count == 0:
            self.set_status("ℹ Tabel sudah kosong.")
            return
        
        choice = messagebox.askyesno(
            f"Hapus Data {self.platform.upper()}",
            f"Yakin hapus {count} video {self.platform}?\nAksi ini tidak bisa dibatalkan."
        )
        if choice:
            with get_db() as db:
                db.query(Video).filter_by(platform=self.platform).delete()
                db.commit()
            self.clear_ui_table()
            self.set_status("🧹 Data berhasil dihapus.")


# ═══════════════════════════════════════════════════════════════
# App — Main Window
# ═══════════════════════════════════════════════════════════════

class App(ctk.CTk):
    def __init__(self):
        # Inisialisasi konfigurasi global dan logging permanen
        setup_logging()
        ensure_directories()
        
        super().__init__()
        self.title("Konten Niche Pro — Auto-Upload Medsos")
        self.geometry("1050x720")
        self.minsize(900, 600)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        init_db()
        
        self._build_header()
        self._build_tabs()
    
    def _build_header(self):
        """Header branding bar"""
        header = ctk.CTkFrame(self, fg_color=("gray90", "gray12"), corner_radius=0, height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        
        title = ctk.CTkLabel(
            header, text="🎬  Konten Niche Pro",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#00D2FF",
        )
        title.grid(row=0, column=0, padx=20, pady=12)
        
        subtitle = ctk.CTkLabel(
            header, text="Auto-Discovery & Upload — YouTube • Instagram • Facebook",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        subtitle.grid(row=0, column=1, padx=10, pady=12, sticky="w")
        
        # Cookie info
        cookie_lbl = ctk.CTkLabel(
            header, text=f"🍪 {os.path.basename(COOKIES_FILE)}",
            font=ctk.CTkFont(size=11),
            text_color="#6BCB77" if os.path.exists(COOKIES_FILE) else "#FF6B6B",
        )
        cookie_lbl.grid(row=0, column=2, padx=20, pady=12)
    
    def _build_tabs(self):
        """Membuat TabView dengan 3 tab platform"""
        self.tabview = ctk.CTkTabview(
            self, corner_radius=12,
            segmented_button_fg_color="gray20",
            segmented_button_selected_color="#00D2FF",
            segmented_button_selected_hover_color="#00B4D8",
            segmented_button_unselected_color="gray30",
            segmented_button_unselected_hover_color="gray40",
        )
        self.tabview.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        
        # Buat 3 tab
        self.tabs = {}
        for platform_key, tab_title in PLATFORM_ICONS.items():
            tab_frame = self.tabview.add(tab_title)
            tab_frame.grid_columnconfigure(0, weight=1)
            tab_frame.grid_rowconfigure(1, weight=1)
            self.tabs[platform_key] = PlatformTab(tab_frame, platform_key, self)
        
        # Set default tab
        self.tabview.set(PLATFORM_ICONS["youtube"])



if __name__ == "__main__":
    app = App()
    atexit.register(shutdown_ngrok)  # Cleanup Ngrok tunnel saat app ditutup
    app.mainloop()
