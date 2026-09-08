import os

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
    
    # QR Code Parameters
    QR_EXPIRY_MINUTES = 5
    
    # Haar Cascade Model
    HAAR_CASCADE_FILE = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
