import os
import logging
import random
from moviepy import VideoFileClip
from moviepy.video.fx import MirrorX, MultiplySpeed, MultiplyColor, Crop, Margin, Resize
from config import VIDEO_OUTPUT_WIDTH, VIDEO_OUTPUT_HEIGHT, RENDER_THREADS

logger = logging.getLogger(__name__)

def process_video_for_reupload(filepath: str) -> str:
    """
    Mengaplikasikan manipulasi anti-copyright dan konversi rasio Vertical (9:16)
    agar dapat menghindari fingerprint match ID Youtube/TikTok/Reels.
    
    CATATAN: Fungsi ini TIDAK menghapus file original.
    Caller bertanggung jawab untuk cleanup file lama jika diperlukan.
    
    Returns:
        Path ke file baru yang sudah diproses. Jika gagal, return filepath asli.
    """
    if not os.path.exists(filepath):
        logger.error(f"Cannot process video. File not found: {filepath}")
        return filepath
        
    logger.info(f"Menerapkan Efek Anti-Copyright Advanced pada: {filepath}")
    
    clip = None
    try:
        clip = VideoFileClip(filepath)
        w, h = clip.size
        
        # 1. Balikkan sisi Horizontal (Mirror X)
        clip = clip.with_effects([MirrorX()])
        
        # 2. Cepatkan durasi secara acak (1.02x - 1.05x) menghindari pencocokan waveform persis
        speed_factor = round(random.uniform(1.02, 1.05), 3)
        clip = clip.with_effects([MultiplySpeed(speed_factor)])
        
        # 3. Slight Color Grading (Membuat kecerahan/saturasi naik 5% secara algoritma RGB)
        # Efek ini merubah bytemark frame warna total tanpa disadari manusia.
        clip = clip.with_effects([MultiplyColor(1.05)])
        
        # 4. Crop & Resize ke Format Vertikal Mobile Resolusi standar (9:16)
        target_ratio = 9 / 16
        current_ratio = w / h
        
        # Mentoleransi sedikit deviasi agar jika rasionya sudah mirip (misal 10:16), dibiarkan
        if abs(current_ratio - target_ratio) > 0.05:
            # Apabila video ini memanjang ke samping (Horizontal 16:9), kita crop area Fokus Tengah:
            if current_ratio > target_ratio: 
                new_w = int(h * target_ratio)
                clip = clip.with_effects([Crop(x_center=w//2, y_center=h//2, width=new_w, height=h)])
            # Apabila sangat memanjang tinggi (sangat mis-proporsi), potong atas-bawah
            else:
                new_h = int(w / target_ratio)
                clip = clip.with_effects([Crop(x_center=w//2, y_center=h//2, width=w, height=new_h)])
        
        # Pastikan dirender dengan ukuran standar platform short agar API Tiktok/IG stabil.
        clip = clip.with_effects([Resize(new_size=(VIDEO_OUTPUT_WIDTH, VIDEO_OUTPUT_HEIGHT))])
            
        # 5. Margin/Border acak (Fake Padding)
        # Menambahkan frame hitam kecil (2-5 pixel) keliling yang akan mengelabui AI pemindai tepian batas
        margin_size = random.randint(2, 5)
        clip = clip.with_effects([Margin(margin_size, color=(0, 0, 0))])
        
        # Siapkan output render
        dir_name, file_name = os.path.split(filepath)
        name, ext = os.path.splitext(file_name)
        new_filepath = os.path.join(dir_name, f"{name}_remix{ext}")
        
        # Render Video menggunakan codec x264 dengan optimalisasi Multi-threading rendering PC
        clip.write_videofile(
            new_filepath,
            codec="libx264",
            audio_codec="aac",
            preset="superfast",         # Mengurangi durasi convert hingga 50%
            threads=RENDER_THREADS,     # Menggunakan CPU threads untuk GUI tidak nge-hang parah
            temp_audiofile=os.path.join(dir_name, f"temp-audio-{name}.m4a"),
            remove_temp=True,
            logger=None
        )
        
        logger.info(f"Berhasil Me-Render Video Anti-Copyright: {new_filepath}")
        
        # Validasi output file benar-benar ada sebelum return
        if os.path.exists(new_filepath):
            return new_filepath
        else:
            logger.error(f"Output file tidak ditemukan setelah render: {new_filepath}")
            return filepath
            
    except Exception as e:
        logger.error(f"Kegagalan Engine Video Editor Lokal pada {filepath}. Log: {e}")
        return filepath
    finally:
        # PENTING: Selalu tutup clip untuk melepaskan file handle (mencegah lock di Windows)
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass