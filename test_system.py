"""
Comprehensive Automated Test Suite for Student QR & Biometric Attendance System.
Tests:
- Database creation, connection pooling, and tables
- Student Registration with department and departmental QR code storage
- Department addition and dropdown listing
- Department grouping and attendance breakdown
- Manual edit blocking by system policy (403)
- Attendance cutoff check and absentee batch processing (AttendanceService)
- Face sample generation and LBPH model training
- Biometric attendance cross-validation and duplicate prevention
- Admin authentication, route protection, and sign out
"""

import os
import cv2
import numpy as np
from datetime import datetime, timedelta, date
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
        cls.created_person_ids = []
        cls.created_depts = []
        cls.created_files = []

    @classmethod
    def tearDownClass(cls):
        """Clean up all test data, departments, QR codes, and face images created during testing."""
        print("\n--- Cleaning up Test Suite Artifacts ---")
        for pid in getattr(cls, "created_person_ids", []):
            try:
                person = DatabaseService.get_person_by_id(pid)
                if person:
                    qr_path = person.get("qr_code_path")
                    if qr_path:
                        QRService.delete_student_qr(qr_path)
                    FaceService.delete_person_face_samples(pid, person.get("person_code", ""))
                DatabaseService.delete_person(pid)
            except Exception as e:
                print(f"Error cleaning test person {pid}: {e}")

        for dept in getattr(cls, "created_depts", []):
            try:
                DatabaseService.execute_query("DELETE FROM departments WHERE name = %s", (dept,), commit=True)
            except Exception as e:
                print(f"Error cleaning test dept {dept}: {e}")

        for fpath in getattr(cls, "created_files", []):
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception as e:
                print(f"Error cleaning file {fpath}: {e}")

        # Re-train model with remaining real images
        remaining_images = [f for f in os.listdir(Config.TRAINING_IMAGE_DIR) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
        if remaining_images:
            FaceService.train_lbph_model()

    def test_01_database_and_student_registration_with_dept_qr(self):
        """Test Student Registration with department and departmental QR code storage (without email requirement)."""
        print("\n[Test 1] Testing Student Registration & Departmental QR Storage...")
        ts = int(datetime.now().timestamp())
        test_code = f"STU_{ts}"
        test_name = "Arun Kumar"
        test_dept = "Computer Science"

        # 1. Insert Student without email
        person_id = DatabaseService.add_person(test_code, test_name, test_dept, email=None)
        self.created_person_ids.append(person_id)
        self.assertIsNotNone(person_id)
        self.assertGreater(person_id, 0)

        person = DatabaseService.get_person_by_id(person_id)
        self.assertEqual(person["department"], test_dept)

        # 2. Generate Student QR into department folder with registration number filename
        qr_info = QRService.generate_student_qr(person_id, test_code, test_name, test_dept)
        self.assertTrue(qr_info["success"])
        self.assertIn("qr_token", qr_info)
        self.assertIn("qr_code_path", qr_info)

        # Verify path matches /static/qr/<department>/<person_code>.png
        expected_rel_path = f"/static/qr/Computer_Science/{test_code}.png"
        self.assertEqual(qr_info["qr_code_path"], expected_rel_path)
        
        full_disk_path = os.path.join(Config.BASE_DIR, expected_rel_path.lstrip("/"))
        self.assertTrue(os.path.exists(full_disk_path), f"QR file should exist at {full_disk_path}")

        # 3. Validate Student QR
        val_res = QRService.validate_student_qr(qr_info["qr_token"])
        self.assertTrue(val_res["success"])
        self.assertEqual(val_res["person"]["id"], person_id)
        self.assertEqual(val_res["person"]["person_code"], test_code)
        print(f"  Passed: Registered student #{person_id} with QR: {qr_info['qr_code_path']}")

    def test_02_department_addition_and_listing(self):
        """Test adding departments dynamically and retrieving the dropdown list."""
        print("\n[Test 2] Testing Department Management & Dropdown APIs...")
        new_dept = f"Aero_{int(datetime.now().timestamp())}"
        self.created_depts.append(new_dept)
        
        # Add department
        success = DatabaseService.add_department(new_dept)
        self.assertTrue(success)

        depts_list = DatabaseService.get_departments_list()
        self.assertIn(new_dept, depts_list)

        # Via API with admin session
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "admin"

        robo_dept = f"Robo_{int(datetime.now().timestamp())}"
        self.created_depts.append(robo_dept)
        api_res = self.client.post("/api/department/add", json={"name": robo_dept})
        self.assertEqual(api_res.status_code, 200)
        self.assertTrue(api_res.get_json()["success"])
        print(f"  Passed: Departments list dynamically maintained (total {len(depts_list)} departments).")

    def test_03_department_wise_attendance_and_edit_toggle(self):
        """Test department-wise attendance breakdown, manual edit disabling (403), and automated attendance."""
        print("\n[Test 3] Testing Department-Wise Attendance & Disabled Manual Edits...")
        today_str = date.today().isoformat()
        test_code = f"DEPT_TEST_{int(datetime.now().timestamp())}"
        dept_name = "Information Technology"
        person_id = DatabaseService.add_person(test_code, "DeptTester", dept_name)
        self.created_person_ids.append(person_id)

        # Initial department attendance breakdown
        dept_data = DatabaseService.get_department_wise_attendance(attendance_date=today_str)
        self.assertIn(dept_name, dept_data)
        self.assertGreaterEqual(dept_data[dept_name]["total_students"], 1)

        # Initially unmarked / absent
        absent_ids = [s["id"] for s in dept_data[dept_name]["absent_students"]]
        self.assertIn(person_id, absent_ids)

        # Manual edit button action MUST be rejected with HTTP 403 Forbidden (authenticated session)
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "admin"

        edit_res = self.client.post("/api/attendance/update-status", json={
            "person_id": person_id,
            "date": today_str,
            "status": "PRESENT"
        })
        self.assertEqual(edit_res.status_code, 403)
        self.assertFalse(edit_res.get_json()["success"])
        self.assertIn("Manual attendance editing is disabled", edit_res.get_json()["message"])

        # Automated Attendance Recording (Kiosk verification) works correctly
        rec_id = DatabaseService.record_attendance(person_id, status="PRESENT")
        self.assertIsNotNone(rec_id)

        # Check department attendance again: student is now PRESENT via automated record
        dept_data_after = DatabaseService.get_department_wise_attendance(attendance_date=today_str)
        pres_ids = [s["id"] for s in dept_data_after[dept_name]["present_students"]]
        self.assertIn(person_id, pres_ids)
        print("  Passed: Department-wise report verified, manual edit blocked (403), and automated attendance confirmed.")

    def test_04_cutoff_absentee_processing(self):
        """Test absentee processing after cutoff time without email service."""
        print("\n[Test 4] Testing Cutoff Absentee Processing (AttendanceService)...")
        today_str = date.today().isoformat()
        test_code = f"ABS_TEST_{int(datetime.now().timestamp())}"
        person_id = DatabaseService.add_person(test_code, "AbsenteeStudent", "Mechanical")
        self.created_person_ids.append(person_id)

        # Run absentee check with force=True
        result = AttendanceService.process_cutoff_absentees(
            cutoff_time_str=Config.ATTENDANCE_CUTOFF_TIME,
            target_date=today_str,
            force=True
        )
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["total_absentees"], 1)

        # Verify student is now marked ABSENT in attendance table
        today_rec = DatabaseService.check_today_attendance(person_id)
        self.assertIsNotNone(today_rec)
        self.assertEqual(today_rec["status"], "ABSENT")
        print(f"  Passed: Processed {result['total_absentees']} absentees with cutoff {Config.ATTENDANCE_CUTOFF_TIME}.")

    def test_05_face_sample_capture_and_training(self):
        """Test face image storage, naming format, and LBPH model training."""
        print("\n[Test 5] Testing Face Sample Capture & LBPH Training...")
        unique_code = f"EMP_TRAIN_{int(datetime.now().timestamp())}"
        person_id = DatabaseService.add_person(unique_code, "ModelTester", "Robotics")
        self.created_person_ids.append(person_id)

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
            self.created_files.append(filepath)

        sample_count = FaceService.get_captured_count(person_id, unique_code)
        self.assertEqual(sample_count, 10)

        # Train model
        train_result = FaceService.train_lbph_model()
        self.assertTrue(train_result["success"])
        self.assertTrue(os.path.exists(Config.TRAINER_FILE))
        print(f"  Passed: LBPH Face Model trained successfully and written to {Config.TRAINER_FILE}.")

    def test_06_biometric_cross_validation_and_duplicate_prevention(self):
        """Test attendance biometric cross-validation and duplicate prevention."""
        print("\n[Test 6] Testing Biometric Cross-Validation & Duplicate Prevention...")
        ts = int(datetime.now().timestamp())
        test_code = f"BIO_TEST_{ts}"
        person_id = DatabaseService.add_person(test_code, "Biometric Tester", "AI & Data Science")
        self.created_person_ids.append(person_id)

        # Mark first attendance
        res1 = AttendanceService.process_attendance(person_id)
        self.assertTrue(res1["success"])
        self.assertEqual(res1["status"], "PRESENT")

        # Attempt duplicate attendance on same day
        res2 = AttendanceService.process_attendance(person_id)
        self.assertFalse(res2["success"])
        self.assertTrue(res2["is_duplicate"])
        print("  Passed: First attendance recorded, duplicate attendance blocked.")

    def test_07_admin_authentication_and_session(self):
        """Test Admin Login, Session Protection, and Sign Out."""
        print("\n[Test 7] Testing Admin Login, Protected Routes & Sign Out...")
        # Clear any leftover session to test unauthenticated access
        with self.client.session_transaction() as sess:
            sess.clear()

        # 1. Accessing dashboard without login redirects to login
        res_unauth = self.client.get("/dashboard")
        self.assertEqual(res_unauth.status_code, 302)
        self.assertIn("/login", res_unauth.headers.get("Location", ""))

        # 2. Login with invalid credentials fails
        res_fail = self.client.post("/login", data={"username": "wrong", "password": "bad"})
        self.assertEqual(res_fail.status_code, 200)

        # 3. Login with valid credentials succeeds and sets session
        res_ok = self.client.post(
            "/login", 
            data={"username": Config.ADMIN_USERNAME, "password": Config.ADMIN_PASSWORD}, 
            follow_redirects=False
        )
        self.assertEqual(res_ok.status_code, 302)
        self.assertIn("/dashboard", res_ok.headers.get("Location", ""))

        # 4. Now accessing dashboard with active session succeeds
        res_dash = self.client.get("/dashboard")
        self.assertEqual(res_dash.status_code, 200)

        # 5. Sign out clears session and redirects to home
        res_logout = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(res_logout.status_code, 302)
        self.assertIn("/home", res_logout.headers.get("Location", ""))

        # 6. Accessing dashboard after logout redirects to login again
        res_after = self.client.get("/dashboard")
        self.assertEqual(res_after.status_code, 302)
        self.assertIn("/login", res_after.headers.get("Location", ""))
        print("  Passed: Admin authentication, route protection, and sign out fully verified.")

    def test_08_face_already_registered_detection(self):
        """Test detection when a student already has face biometrics or when a face matches another student."""
        print("\n[Test 8] Testing Face Already Registered Detection...")
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        dup_res = FaceService.check_face_already_registered(dummy_frame, current_person_id=99999)
        self.assertFalse(dup_res["is_duplicate"])

        save_res = FaceService.save_face_sample_from_frame(dummy_frame, person_id=999999)
        self.assertFalse(save_res["success"])
        print("  Passed: Face already registered checking mechanism validated.")

if __name__ == "__main__":
    unittest.main()
