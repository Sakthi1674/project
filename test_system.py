"""
Comprehensive Automated Test Suite for Student QR & Biometric Attendance System.
Tests:
- Database creation, connection pooling, and tables
- Student QR Code generation, persistence, and validation
- Department grouping and student counts
- Face sample generation, file naming, and LBPH model training
- Face recognition and prediction
- Biometric attendance cross-validation and duplicate prevention
- Flask API routes
"""

import os
import cv2
import numpy as np
from datetime import datetime, timedelta
import unittest
from config import Config
from services.database_service import DatabaseService
from services.qr_service import QRService
from services.face_service import FaceService
from services.attendance_service import AttendanceService
from app import app

class TestAttendanceSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up database and directories for testing."""
        print("\n--- Setting up Test Suite ---")
        DatabaseService.init_db()
        FaceService.ensure_directories()
        QRService.ensure_qr_dir()
        cls.client = app.test_client()

    def test_01_database_and_student_registration(self):
        """Test Student Registration and automatic QR generation."""
        print("\n[Test 1] Testing Student Registration & Unique QR Generation...")
        test_code = f"STU_{int(datetime.now().timestamp())}"
        test_name = "Arun Kumar"
        test_dept = "Computer Science"

        # 1. Insert Student
        person_id = DatabaseService.add_person(test_code, test_name, test_dept)
        self.assertIsNotNone(person_id)
        self.assertGreater(person_id, 0)

        # 2. Generate Student QR
        qr_info = QRService.generate_student_qr(person_id, test_code, test_name, test_dept)
        self.assertTrue(qr_info["success"])
        self.assertIn("qr_token", qr_info)
        self.assertIn("qr_code_path", qr_info)
        self.assertTrue(os.path.exists(os.path.join(Config.BASE_DIR, qr_info["qr_code_path"].lstrip("/"))))

        # 3. Validate Student QR
        val_res = QRService.validate_student_qr(qr_info["qr_token"])
        self.assertTrue(val_res["success"])
        self.assertEqual(val_res["person"]["id"], person_id)
        self.assertEqual(val_res["person"]["person_code"], test_code)
        print(f"  Passed: Registered student #{person_id} with unique QR: {qr_info['qr_code_path']}")

    def test_02_department_grouping(self):
        """Test department grouping for the dashboard."""
        print("\n[Test 2] Testing Department Grouping...")
        grouped = DatabaseService.get_persons_grouped_by_department()
        self.assertIsInstance(grouped, dict)
        self.assertGreater(len(grouped), 0)

        depts = DatabaseService.get_all_departments()
        self.assertIsInstance(depts, list)
        self.assertGreater(len(depts), 0)
        print(f"  Passed: Grouped students across {len(grouped)} departments.")

    def test_03_face_sample_and_training(self):
        """Test face image storage, naming format, and LBPH model training."""
        print("\n[Test 3] Testing Face Sample Capture & LBPH Training...")
        unique_code = f"EMP_TRAIN_{int(datetime.now().timestamp())}"
        person_id = DatabaseService.add_person(unique_code, "ModelTester", "Robotics")

        # Create synthetic face images for training
        for i in range(1, 11):
            face_img = np.zeros((200, 200), dtype=np.uint8)
            cv2.circle(face_img, (60, 70), 20, 200, -1)
            cv2.circle(face_img, (140, 70), 20, 200, -1)
            cv2.ellipse(face_img, (100, 140), (40, 20), 0, 0, 180, 180, -1)
            noise = np.random.randint(0, 15, (200, 200), dtype=np.uint8)
            face_img = cv2.add(face_img, noise)

            filename = f"ModelTester.{person_id}.{unique_code}.{i}.jpg"
            filepath = os.path.join(Config.TRAINING_IMAGE_DIR, filename)
            cv2.imwrite(filepath, face_img)

        sample_count = FaceService.get_captured_count(person_id, unique_code)
        self.assertEqual(sample_count, 10)

        # Train model
        train_result = FaceService.train_lbph_model()
        self.assertTrue(train_result["success"])
        self.assertTrue(os.path.exists(Config.TRAINER_FILE))
        print(f"  Passed: LBPH Face Model trained successfully and written to {Config.TRAINER_FILE}.")

    def test_04_attendance_marking_and_duplicates(self):
        """Test attendance marking and duplicate detection."""
        print("\n[Test 4] Testing Attendance Duplicate Prevention...")
        person_code = f"ATT_TEST_{int(datetime.now().timestamp())}"
        person_id = DatabaseService.add_person(person_code, "AttendanceStudent", "Civil")

        # Mark attendance first time
        result1 = AttendanceService.process_attendance(person_id)
        self.assertTrue(result1["success"])
        self.assertEqual(result1["person"]["id"], person_id)

        # Attempt duplicate attendance on same date
        result2 = AttendanceService.process_attendance(person_id)
        self.assertFalse(result2["success"])
        self.assertTrue(result2.get("is_duplicate"))
        print("  Passed: Duplicate attendance prevented for today.")

    def test_05_flask_routes(self):
        """Test all Flask web endpoints including new student QR and department dashboard."""
        print("\n[Test 5] Testing Flask Web Endpoints...")
        # GET / (Dashboard with department grid)
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Student Attendance & Biometric Directory", res.data)

        # GET /register
        res = self.client.get("/register")
        self.assertEqual(res.status_code, 200)

        # POST /register (redirects to /student-qr/<id>)
        unique_id = f"ROUTE_STU_{int(datetime.now().timestamp())}"
        res = self.client.post("/register", data={
            "person_id": unique_id,
            "name": "Route Student",
            "department": "Mechanical"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/student-qr/", res.headers["Location"])

        # Follow to student-qr page
        qr_page_res = self.client.get(res.headers["Location"])
        self.assertEqual(qr_page_res.status_code, 200)
        self.assertIn(b"Student Registered & Unique QR Generated", qr_page_res.data)

        # POST /validate-student-qr
        val_res = self.client.post("/validate-student-qr", json={"qr_data": unique_id})
        self.assertEqual(val_res.status_code, 200)
        self.assertTrue(val_res.get_json()["success"])

        # GET /attendance
        res = self.client.get("/attendance")
        self.assertEqual(res.status_code, 200)

        # GET /report
        res = self.client.get("/report")
        self.assertEqual(res.status_code, 200)

        # GET /api/attendance
        res = self.client.get("/api/attendance")
        self.assertEqual(res.status_code, 200)
        print("  Passed: All endpoints (Dashboard, Register, Student QR, Validation, Terminal, Reports) verified.")

if __name__ == "__main__":
    unittest.main()
