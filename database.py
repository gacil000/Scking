from sqlalchemy import create_engine, Column, Integer, String, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError
from contextlib import contextmanager
from config import DATABASE_URL
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

class Video(Base):
    __tablename__ = 'videos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    platform = Column(String, nullable=False, index=True) # 'youtube', 'instagram', 'facebook', 'tiktok'
    status = Column(String, default='MUNCUL', index=True) # 'MUNCUL', 'DIUNDUH', 'DIUNGGAH'
    filepath = Column(String, nullable=True) # path ke file lokal setelah didownload
    
    # Fitur Baru
    generated_caption = Column(String, nullable=True)
    scheduled_time = Column(String, nullable=True) # Iso format string
    llm_provider = Column(String, nullable=True)

# Konfigurasi Database (SQLite) - Thread-Safe
# connect_args check_same_thread=False WAJIB agar SQLite bisa diakses dari thread berbeda.
# pool_pre_ping memastikan koneksi masih hidup sebelum dipakai.
engine = create_engine(
    DATABASE_URL, 
    echo=False,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def get_db():
    """Context Manager untuk mendapatkan sesi DB yang aman per-scope.
    
    PENTING: Caller bertanggung jawab untuk memanggil db.commit() secara eksplisit.
    Context manager ini hanya melakukan rollback jika terjadi exception,
    dan selalu menutup session saat selesai.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(engine)
    
    # Simple migration for existing DB — hanya catch OperationalError
    # agar error serius (disk full, corruption) tidak tertelan
    migration_columns = [
        "ALTER TABLE videos ADD COLUMN generated_caption VARCHAR",
        "ALTER TABLE videos ADD COLUMN scheduled_time VARCHAR",
        "ALTER TABLE videos ADD COLUMN llm_provider VARCHAR",
    ]
    with engine.connect() as conn:
        for sql in migration_columns:
            try:
                conn.execute(text(sql))
            except OperationalError:
                pass  # Kolom sudah ada, abaikan
            except Exception as e:
                logger.warning(f"Migration warning: {e}")
        conn.commit()

if __name__ == "__main__":
    import logging
    init_db()
    logging.info("Database dan tabel berhasil diinisialisasi.")

