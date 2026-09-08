import os
import re
import json
import uuid
import qrcode
from datetime import datetime, timedelta
from config import Config
from services.database_service import DatabaseService
import logging

logger = logging.getLogger(__name__)

class QRService:
    """Manages student unique QR code generation, storage, and validation."""

    @classmethod
    def ensure_qr_dir(cls):
        """Ensures the static/qr and static/qr/students directories exist."""
        os.makedirs(Config.QR_FOLDER, exist_ok=True)
        os.makedirs(os.path.join(Config.QR_FOLDER, "students"), exist_ok=True)

    @classmethod
    def generate_student_qr(cls, person_id, person_code, name, department):
        """
        Generates and stores a permanent unique QR code for a registered student.
        Encodes student details into QR, saves image in static/qr/students/{person_code}.png,
        and updates the student's record in MySQL.
        """
        cls.ensure_qr_dir()
        student_qr_dir = os.path.join(Config.QR_FOLDER, "students")

        # 1. Generate unique student token
        unique_token = f"STU_{uuid.uuid4().hex[:12].upper()}"

        # 2. Prepare structured QR payload
        qr_payload = json.dumps({
            "type": "STUDENT_ATTENDANCE_QR",
            "token": unique_token,
            "person_code": person_code,
            "name": name,
            "department": department or "General"
        })

        # 3. Render high-resolution QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=3,
        )
        qr.add_data(qr_payload)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")

        clean_code = re.sub(r'[^a-zA-Z0-9_-]', '_', person_code)
        filename = f"{clean_code}.png"
        filepath = os.path.join(student_qr_dir, filename)
        qr_img.save(filepath)

        rel_path = f"/static/qr/students/{filename}"

        # 4. Save to Database
        DatabaseService.update_person_qr(person_id, unique_token, rel_path)

        logger.info(f"Generated unique student QR for {name} ({person_code}) -> {rel_path}")

        return {
            "success": True,
            "qr_token": unique_token,
            "qr_code_path": rel_path,
            "person_id": person_id,
            "person_code": person_code,
            "name": name,
            "department": department
        }

    @classmethod
    def delete_student_qr(cls, qr_code_path):
        """Deletes student's QR image from filesystem."""
        if not qr_code_path:
            return False
        try:
            full_path = os.path.join(Config.BASE_DIR, qr_code_path.lstrip("/\\"))
            if os.path.exists(full_path):
                os.remove(full_path)
                logger.info(f"Deleted QR image file: {full_path}")
                return True
        except Exception as e:
            logger.warning(f"Could not delete QR file {qr_code_path}: {e}")
        return False

    @classmethod
    def validate_student_qr(cls, raw_input):
        """
        Validates scanned QR data from the attendance terminal.
        Accepts JSON payload, unique token, or student ID.
        Returns the registered student profile.
        """
        if not raw_input or not isinstance(raw_input, str):
            return {"success": False, "message": "Empty or invalid QR code data."}

        raw_input = raw_input.strip()
        token = raw_input
        person_code = raw_input

        # Parse JSON if applicable
        try:
            parsed = json.loads(raw_input)
            if isinstance(parsed, dict):
                token = parsed.get("token") or token
                person_code = parsed.get("person_code") or person_code
        except Exception:
            pass

        # Lookup in MySQL
        person = DatabaseService.get_person_by_qr_token(token)
        if not person and person_code != token:
            person = DatabaseService.get_person_by_code(person_code)

        if not person:
            return {
                "success": False,
                "message": "Student not recognized. This QR code does not belong to any enrolled student."
            }

        return {
            "success": True,
            "message": f"Student verified: {person['name']}",
            "person": person
        }

    @classmethod
    def ensure_all_students_have_qr(cls):
        """Ensures every existing student in database has a unique QR code generated."""
        students = DatabaseService.get_all_persons()
        for s in students:
            qr_file = s.get("qr_code_path")
            full_path = os.path.join(Config.BASE_DIR, qr_file.lstrip("/")) if qr_file else None
            if not qr_file or not full_path or not os.path.exists(full_path):
                cls.generate_student_qr(s["id"], s["person_code"], s["name"], s["department"])

    # --- Legacy dynamic QR session generation for backwards compatibility ---
    @classmethod
    def generate_attendance_qr(cls):
        """Generates dynamic attendance QR code valid for 5 minutes."""
        cls.ensure_qr_dir()
        token = str(uuid.uuid4())
        created_at = datetime.now()
        expires_at = created_at + timedelta(minutes=Config.QR_EXPIRY_MINUTES)
        session_id = DatabaseService.create_qr_session(token, expires_at)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=3,
        )
        qr.add_data(token)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")

        filename = f"{token}.png"
        filepath = os.path.join(Config.QR_FOLDER, filename)
        qr_img.save(filepath)

        return {
            "session_id": session_id,
            "token": token,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            "image_url": f"/static/qr/{filename}",
            "valid_seconds": Config.QR_EXPIRY_MINUTES * 60
        }

    @classmethod
    def validate_qr_token(cls, token):
        """Validates dynamic session token."""
        if not token or not isinstance(token, str):
            return {"success": False, "message": "Invalid QR code: missing token."}
        token = token.strip()
        session = DatabaseService.get_qr_session(token)
        if not session:
            return {"success": False, "message": "Invalid QR code: token not recognized."}

        now = datetime.now()
        expires_at = session["expires_at"]
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        if session["status"] != "ACTIVE" or (expires_at and expires_at < now):
            DatabaseService.expire_qr_session(token)
            return {"success": False, "message": "QR code has expired."}

        return {"success": True, "message": "QR code is valid.", "session_id": session["id"], "token": token}
