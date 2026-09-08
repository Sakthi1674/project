"""
Script to wipe all student data, attendance logs, face datasets, QR codes, and trained models.
Usage:
    python clear_all_data.py
"""

import os
import sys

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from config import Config
from services.database_service import DatabaseService
from services.face_service import FaceService
from services.qr_service import QRService

def purge_all_data():
    print("=" * 65)
    print(" [*] PURGING ALL STUDENT DATA, ATTENDANCE & BIOMETRIC ASSETS")
    print("=" * 65)

    # 1. Purge MySQL Database
    DatabaseService.init_db()
    print("[1/4] Purging MySQL records (attendance, persons, qr_sessions)...")
    DatabaseService.clear_all_student_data()
    print("  -> Database tables cleared & AUTO_INCREMENT reset to 1.")

    # 2. Delete all training images
    print("[2/4] Purging TrainingImage/ face datasets...")
    deleted_images = 0
    if os.path.exists(Config.TRAINING_IMAGE_DIR):
        for f in os.listdir(Config.TRAINING_IMAGE_DIR):
            fpath = os.path.join(Config.TRAINING_IMAGE_DIR, f)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    deleted_images += 1
                except Exception as e:
                    print(f"  [!] Could not delete {f}: {e}")
    print(f"  -> Deleted {deleted_images} face training sample images.")

    # 3. Delete Trainer.yml
    print("[3/4] Removing trained LBPH model...")
    if os.path.exists(Config.TRAINER_FILE):
        try:
            os.remove(Config.TRAINER_FILE)
            print("  -> Removed Trainer.yml.")
        except Exception as e:
            print(f"  [!] Error removing Trainer.yml: {e}")
    else:
        print("  -> No Trainer.yml model found.")

    # 4. Delete Student QR Codes
    print("[4/4] Purging student QR codes from static/qr/...")
    deleted_qrs = 0
    student_qr_dir = os.path.join(Config.QR_FOLDER, "students")
    if os.path.exists(student_qr_dir):
        for f in os.listdir(student_qr_dir):
            fpath = os.path.join(student_qr_dir, f)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    deleted_qrs += 1
                except Exception as e:
                    print(f"  [!] Could not delete {f}: {e}")

    # Remove any extra PNGs in static/qr directly
    if os.path.exists(Config.QR_FOLDER):
        for f in os.listdir(Config.QR_FOLDER):
            fpath = os.path.join(Config.QR_FOLDER, f)
            if os.path.isfile(fpath) and f.lower().endswith(".png"):
                try:
                    os.remove(fpath)
                    deleted_qrs += 1
                except Exception:
                    pass
    print(f"  -> Deleted {deleted_qrs} generated QR code images.")

    # Re-ensure directory structures exist
    FaceService.ensure_directories()
    QRService.ensure_qr_dir()

    print("\n" + "=" * 65)
    print(" [SUCCESS] All student data, attendance logs, and biometric assets")
    print(" have been completely removed. System is clean and ready.")
    print("=" * 65)

if __name__ == "__main__":
    purge_all_data()
