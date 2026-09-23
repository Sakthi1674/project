import os

def load_env_file(filepath=".env"):
    """Reads key-value pairs from .env into os.environ without requiring external packages."""
    if not os.path.isabs(filepath):
        base_dir = os.path.abspath(os.path.dirname(__file__))
        filepath = os.path.join(base_dir, filepath)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        os.environ[k] = v
        except Exception:
            pass

# Pre-load .env into environment
load_env_file()

class Config:
    """Application Configuration Settings"""
    # Base directories
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Secret Key for Flask session and flash messages
    SECRET_KEY = os.environ.get("SECRET_KEY", "face_attendance_secret_key_2026_super_secure")
    
    # MySQL Database Configuration
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "root")
    DB_NAME = os.environ.get("DB_NAME", "attendance_system")
    
    # Storage Directories
    TRAINING_IMAGE_DIR = os.path.join(BASE_DIR, "TrainingImage")
    TRAINING_LABEL_DIR = os.path.join(BASE_DIR, "TrainingImageLabel")
    TRAINER_FILE = os.path.join(TRAINING_LABEL_DIR, "Trainer.yml")
    QR_FOLDER = os.path.join(BASE_DIR, "static", "qr")
    
    # Face Detection & Recognition Parameters
    # LBPH distance: lower is better match. Confidence < 70 is strong match.
    CONFIDENCE_THRESHOLD = 75.0
    REQUIRED_SAMPLES = 50
    
    # Administrator Credentials
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Attendance Cutoff Time (HH:MM format, e.g. '10:30')
    # After this time, unmarked students are marked ABSENT
    ATTENDANCE_CUTOFF_TIME = os.environ.get("ATTENDANCE_CUTOFF_TIME", "10:30")

    @classmethod
    def get_cutoff_time(cls):
        """Dynamically re-reads ATTENDANCE_CUTOFF_TIME from .env or environment, normalizing format."""
        load_env_file()
        cutoff = os.environ.get("ATTENDANCE_CUTOFF_TIME", cls.ATTENDANCE_CUTOFF_TIME)
        clean = cutoff.strip() if cutoff else "10:30"
        # Support user entering '10.30' with a dot
        if "." in clean and ":" not in clean:
            clean = clean.replace(".", ":")
        cls.ATTENDANCE_CUTOFF_TIME = clean
        return clean

    @classmethod
    def get_smtp_config(cls):
        """Dynamically re-reads SMTP settings from .env or environment."""
        load_env_file()
        cls.SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "").strip()
        cls.SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
        cls.SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com").strip()
        try:
            cls.SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
        except (ValueError, TypeError):
            cls.SMTP_PORT = 587
        cls.SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "True").lower() in ("true", "1", "yes")
        return {
            "email": cls.SMTP_EMAIL,
            "password": cls.SMTP_PASSWORD,
            "server": cls.SMTP_SERVER,
            "port": cls.SMTP_PORT,
            "use_tls": cls.SMTP_USE_TLS
        }

    # Haar Cascade Model
    HAAR_CASCADE_FILE = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
