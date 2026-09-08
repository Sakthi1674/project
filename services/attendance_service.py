from datetime import datetime, date
from services.database_service import DatabaseService
from services.face_service import FaceService
from services.qr_service import QRService
import logging

logger = logging.getLogger(__name__)

class AttendanceService:
    """Manages attendance verification, duplicate prevention, and logging."""

    @classmethod
    def process_student_biometric_attendance(cls, student_id, frame_bgr):
        """
        Validates student attendance using biometric cross-validation:
        1. Confirms student exists.
        2. Detects face in webcam frame.
        3. Recognizes face using LBPH model.
        4. Verifies that the face in front of the camera matches the student ID from the scanned QR!
        5. Checks for duplicate attendance today.
        6. Saves attendance in MySQL and returns confirmation details.
        """
        # 1. Fetch expected student from DB
        student = DatabaseService.get_person_by_id(student_id)
        if not student:
            return {
                "success": False,
                "message": f"Student record #{student_id} not found in database."
            }

        # 2. Check if face model is trained
        rec_result = FaceService.recognize_face_from_frame(frame_bgr)
        if not rec_result["success"]:
            return {
                "success": False,
                "message": rec_result["message"]
            }

        recognized_person = rec_result["person"]
        confidence = rec_result.get("confidence_score", 0)

        # 3. Biometric Cross-Validation: does recognized person match the scanned student?
        if int(recognized_person["id"]) != int(student["id"]):
            logger.warning(
                f"Biometric mismatch! Scanned QR: {student['name']} ({student['person_code']}), "
                f"Face matched: {recognized_person['name']} ({recognized_person['person_code']})"
            )
            return {
                "success": False,
                "is_mismatch": True,
                "message": (
                    f"Biometric Mismatch! The camera detected {recognized_person['name']} "
                    f"({recognized_person['person_code']}), but the scanned QR code belongs to "
                    f"{student['name']} ({student['person_code']}). Proxy attendance rejected."
                )
            }

        # 4. Check for duplicate attendance today
        today_record = DatabaseService.check_today_attendance(student["id"])
        if today_record:
            time_str = str(today_record["attendance_time"])
            return {
                "success": False,
                "is_duplicate": True,
                "message": f"Attendance already marked for {student['name']} today at {time_str}.",
                "person": student,
                "marked_time": time_str
            }

        # 5. Record Attendance
        try:
            attendance_id = DatabaseService.record_attendance(
                person_id=student["id"],
                qr_session_id=None,
                status="PRESENT"
            )
            now = datetime.now()
            time_formatted = now.strftime("%I:%M:%S %p")
            date_formatted = now.strftime("%Y-%m-%d")

            logger.info(f"Attendance verified & recorded #{attendance_id} for {student['name']} ({student['person_code']})")

            return {
                "success": True,
                "is_duplicate": False,
                "message": f"Identity verified! Attendance marked successfully for {student['name']}.",
                "attendance_id": attendance_id,
                "person": student,
                "date": date_formatted,
                "time": time_formatted,
                "status": "PRESENT",
                "confidence_score": confidence
            }
        except Exception as e:
            logger.error(f"Failed to record attendance: {e}")
            return {
                "success": False,
                "message": f"Database error while recording attendance: {str(e)}"
            }

    @classmethod
    def process_attendance(cls, person_id, qr_token=None):
        """Standard attendance marking with duplicate check."""
        person = DatabaseService.get_person_by_id(person_id)
        if not person:
            return {
                "success": False,
                "message": f"Person ID #{person_id} does not exist in the system."
            }

        # Check for Duplicate Attendance Today
        today_record = DatabaseService.check_today_attendance(person_id)
        if today_record:
            time_str = str(today_record["attendance_time"])
            return {
                "success": False,
                "is_duplicate": True,
                "message": f"Attendance already marked for {person['name']} today at {time_str}.",
                "person": person,
                "marked_time": time_str
            }

        try:
            attendance_id = DatabaseService.record_attendance(
                person_id=person_id,
                qr_session_id=None,
                status="PRESENT"
            )
            now = datetime.now()
            time_formatted = now.strftime("%I:%M:%S %p")
            date_formatted = now.strftime("%Y-%m-%d")

            return {
                "success": True,
                "is_duplicate": False,
                "message": f"Attendance successfully marked for {person['name']}!",
                "attendance_id": attendance_id,
                "person": person,
                "date": date_formatted,
                "time": time_formatted,
                "status": "PRESENT"
            }
        except Exception as e:
            logger.error(f"Failed to record attendance: {e}")
            return {
                "success": False,
                "message": f"Database error while recording attendance: {str(e)}"
            }

    @classmethod
    def get_report(cls, date_filter=None, search=None):
        """Retrieves attendance log entries for reporting."""
        records = DatabaseService.get_attendance_logs(date_filter=date_filter, search=search)
        formatted = []
        for r in records:
            time_obj = r["attendance_time"]
            time_display = str(time_obj)
            formatted.append({
                "id": r["attendance_id"],
                "person_code": r["person_code"],
                "name": r["name"],
                "department": r["department"] or "General",
                "date": str(r["attendance_date"]),
                "time": time_display,
                "status": r["status"]
            })
        return formatted
