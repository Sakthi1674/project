"""
Direct System Camera Face Capture & Training Utility
Attendance System - High Speed Biometric Face Dataset Collector

Usage:
    python capture_camera.py                  # Lists registered students to choose from
    python capture_camera.py <student_id>     # Captures for specific student by ID or Person Code
    python capture_camera.py STU001           # Captures for student by person code
"""

import sys
import os
import time

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from config import Config
from services.database_service import DatabaseService
from services.face_service import FaceService

def main():
    print("=" * 65)
    print(" [*] FAST DIRECT SYSTEM CAMERA FACE CAPTURE & DATASET COLLECTOR")
    print("=" * 65)

    # Initialize DB and directories
    DatabaseService.init_db()
    FaceService.ensure_directories()

    target_person = None

    if len(sys.argv) > 1:
        identifier = sys.argv[1].strip()
        # Try finding by numeric ID
        if identifier.isdigit():
            target_person = DatabaseService.get_person_by_id(int(identifier))
        
        # If not found by ID, try by person_code
        if not target_person:
            target_person = DatabaseService.get_person_by_code(identifier)

        if not target_person:
            print(f"[!] Error: Student with ID or code '{identifier}' not found in database.")
            sys.exit(1)
    else:
        # Interactive selection
        persons = DatabaseService.get_all_persons()
        if not persons:
            print("[!] No registered students found in database. Please register a student first.")
            sys.exit(1)

        print("\nRegistered Students:")
        for idx, p in enumerate(persons, 1):
            count = FaceService.get_captured_count(p["id"], p["person_code"])
            print(f" [{idx}] ID: {p['id']} | Code: {p['person_code']:<12} | Name: {p['name']:<20} | Dept: {p.get('department','General'):<15} | Samples: {count}/50")

        choice = input("\nSelect student number to capture face for (or press Enter for #1): ").strip()
        if not choice:
            target_person = persons[0]
        else:
            try:
                selected_idx = int(choice) - 1
                if 0 <= selected_idx < len(persons):
                    target_person = persons[selected_idx]
                else:
                    print("[!] Invalid selection.")
                    sys.exit(1)
            except ValueError:
                print("[!] Invalid input number.")
                sys.exit(1)

    print("\n" + "-" * 65)
    print(f"Target Student: {target_person['name']} (Code: {target_person['person_code']}, DB Serial: {target_person['id']})")
    current_count = FaceService.get_captured_count(target_person["id"], target_person["person_code"])
    print(f"Existing Samples: {current_count} / {Config.REQUIRED_SAMPLES}")
    print("[+] Directly accessing system camera via OpenCV DirectShow...")
    print("[+] Capturing 50 samples rapidly at native camera framerate (~2 seconds)...")
    print("[*] Please look straight at the camera and slightly tilt/rotate your head.")
    print("-" * 65 + "\n")

    t_start = time.time()
    result = FaceService.capture_faces_opencv_native(
        person_id=target_person["id"],
        max_samples=Config.REQUIRED_SAMPLES,
        auto_train=True
    )
    t_elapsed = time.time() - t_start

    print("\n" + "=" * 65)
    if result.get("success"):
        print(f"[SUCCESS] {result.get('message')}")
        print(f"Total Capture Time: {t_elapsed:.2f} seconds")
        print(f"Stored in: {Config.TRAINING_IMAGE_DIR}")
        print(f"Biometric Model Status: {'Trained & Ready' if result.get('model_trained') else 'Manual train required'}")
    else:
        print(f"[FAILED] {result.get('message')}")
    print("=" * 65)

if __name__ == "__main__":
    main()
