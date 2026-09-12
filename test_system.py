"""
Comprehensive Automated Test Suite for Student QR & Biometric Attendance System.
Tests:
- Database creation, connection pooling, and tables
- Student Registration with email and department
- Department addition and dropdown listing
- Department-based QR code folder storage with registration number filename
- Department grouping and attendance breakdown
- Attendance status update (edit button to Present/Absent)
- Attendance cutoff check and absentee notification processing
- Face sample generation, collision avoidance, and LBPH model training
- Biometric attendance cross-validation and duplicate prevention
- Flask API routes
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
from services.email_service import EmailService
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

    def test_01_database_and_student_registration_with_email_and_dept_qr(self):
        """Test Student Registration with email, department, and departmental QR code storage."""
        print("\n[Test 1] Testing Student Registration with Email & Departmental QR Storage...")
        ts = int(datetime.now().timestamp())
        test_code = f"STU_{ts}"
        test_name = "Arun Kumar"
        test_email = f"arun_{ts}@university.edu"
        test_dept = "Computer Science"

        # 1. Insert Student with email
        person_id = DatabaseService.add_person(test_code, test_name, test_dept, email=test_email)
        self.assertIsNotNone(person_id)
        self.assertGreater(person_id, 0)

        person = DatabaseService.get_person_by_id(person_id)
        self.assertEqual(person["email"], test_email)
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
        print(f"  Passed: Registered student #{person_id} with email {test_email} and QR: {qr_info['qr_code_path']}")

    def test_02_department_addition_and_listing(self):
        """Test adding departments dynamically and retrieving the dropdown list."""
        print("\n[Test 2] Testing Department Management & Dropdown APIs...")
        new_dept = f"Aero_{int(datetime.now().timestamp())}"
        
        # Add department
        success = DatabaseService.add_department(new_dept)
        self.assertTrue(success)

        depts_list = DatabaseService.get_departments_list()
        self.assertIn(new_dept, depts_list)

        # Via API
        api_res = self.client.post("/api/department/add", json={"name": f"Robo_{int(datetime.now().timestamp())}"})
        self.assertEqual(api_res.status_code, 200)
        self.assertTrue(api_res.get_json()["success"])
        print(f"  Passed: Departments list dynamically maintained (total {len(depts_list)} departments).")

    def test_03_department_wise_attendance_and_edit_toggle(self):
        """Test department-wise attendance breakdown, manual edit disabling (403), and automated attendance."""
        print("\n[Test 3] Testing Department-Wise Attendance & Disabled Manual Edits...")
        today_str = date.today().isoformat()
        test_code = f"DEPT_TEST_{int(datetime.now().timestamp())}"
        dept_name = "Information Technology"
        person_id = DatabaseService.add_person(test_code, "DeptTester", dept_name, email="dept@test.com")

        # Initial department attendance breakdown
        dept_data = DatabaseService.get_department_wise_attendance(attendance_date=today_str)
        self.assertIn(dept_name, dept_data)
        self.assertGreaterEqual(dept_data[dept_name]["total_students"], 1)

        # Initially unmarked / absent
        absent_ids = [s["id"] for s in dept_data[dept_name]["absent_students"]]
        self.assertIn(person_id, absent_ids)

        # Manual edit button action MUST be rejected with HTTP 403 Forbidden
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

    def test_04_cutoff_absentee_processing_and_email(self):
        """Test absentee processing after cutoff time with notification dispatch."""
        print("\n[Test 4] Testing Cutoff Absentee Processing & Email Notifications...")
        today_str = date.today().isoformat()
        test_code = f"ABS_TEST_{int(datetime.now().timestamp())}"
        person_id = DatabaseService.add_person(test_code, "AbsenteeStudent", "Mechanical", email="absentee@test.com")

        # Run absentee check with force=True
        result = EmailService.process_absentees_and_notify(
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
        person_id = DatabaseService.add_person(unique_code, "ModelTester", "Robotics", email="tester@test.com")

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

    def test_06_flask_web_endpoints(self):
        """Test all Flask web endpoints with light theme and new flows."""
        print("\n[Test 6] Testing Flask Web Endpoints & Light Theme...")
        # 1. Welcome Homepage
        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 200)
        self.assertIn(b"Welcome", res_home.data)
        self.assertIn(b"GET STARTED", res_home.data)
        self.assertIn(b"Dashboard", res_home.data)

        # 2. Admin Dashboard
        res_dash = self.client.get("/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"QR Code Based Attendance Management system", res_dash.data)

        # 3. Registration with email and department
        unique_id = f"ROUTE_STU_{int(datetime.now().timestamp())}"
        unique_email = f"route_{int(datetime.now().timestamp())}@test.com"
        res = self.client.post("/register", data={
            "person_id": unique_id,
            "name": "Route Student",
            "email": unique_email,
            "department": "Civil Engineering"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/student-qr/", res.headers["Location"])

        # 4. Reports (verify manual edit buttons are absent)
        res_rep = self.client.get("/report")
        self.assertEqual(res_rep.status_code, 200)
        self.assertIn(b"Department-Wise Attendance Reports", res_rep.data)
        self.assertNotIn(b"Mark Present", res_rep.data)
        self.assertNotIn(b"toggleStudentStatus", res_rep.data)

        # 5. Dedicated Department Detail Page
        res_dept = self.client.get("/department/Computer%20Science")
        self.assertEqual(res_dept.status_code, 200)
        self.assertIn(b"Computer Science", res_dept.data)
        self.assertIn(b"Academic Department", res_dept.data)

        # 6. Dynamic Cutoff Verification
        cutoff_val = Config.get_cutoff_time()
        self.assertTrue(len(cutoff_val) >= 4)
        print("  Passed: All web endpoints verified, including homepage, dashboard, and report.")

    def test_07_duplicate_student_across_departments(self):
        """Test duplicate student prevention across departments for ID and Email with informative errors."""
        print("\n[Test 7] Testing Cross-Department Duplicate Detection (ID & Email)...")
        ts = int(datetime.now().timestamp())
        dup_code = f"DUP_ID_{ts}"
        dup_email = f"student_{ts}@dept1.edu"
        
        # 1. Register student in Computer Science
        res1 = self.client.post("/register", data={
            "person_id": dup_code,
            "name": "Original Student",
            "email": dup_email,
            "department": "Computer Science"
        }, follow_redirects=False)
        self.assertEqual(res1.status_code, 302)

        # 2. Try registering the SAME person_code in a DIFFERENT department (e.g. Mechanical Engineering)
        res_dup_id = self.client.post("/register", data={
            "person_id": dup_code,
            "name": "Imposter Student",
            "email": f"different_{ts}@dept2.edu",
            "department": "Mechanical Engineering"
        }, follow_redirects=True)
        # Should stay on register page with error message
        self.assertEqual(res_dup_id.status_code, 200)
        self.assertIn(b"already registered in &#39;Computer Science&#39; department", res_dup_id.data)
        self.assertIn(b"Duplicate student registration across departments is not allowed", res_dup_id.data)

        # 3. Try registering a DIFFERENT person_code but the SAME email in another department (e.g. Information Technology)
        res_dup_email = self.client.post("/register", data={
            "person_id": f"NEW_ID_{ts}",
            "name": "Another Student",
            "email": dup_email,
            "department": "Information Technology"
        }, follow_redirects=True)
        self.assertEqual(res_dup_email.status_code, 200)
        self.assertIn(b"already registered to student &#39;Original Student&#39;", res_dup_email.data)
        self.assertIn(b"A student cannot be registered multiple times across departments", res_dup_email.data)

        # 4. Verify check_duplicate_student directly
        dup_res = DatabaseService.check_duplicate_student(dup_code, email="random@test.com")
        self.assertTrue(dup_res["is_duplicate"])
        self.assertEqual(dup_res["field"], "person_code")
        self.assertIn("Computer Science", dup_res["message"])

        dup_email_res = DatabaseService.check_duplicate_student("UNIQUE_ID_999", email=dup_email)
        self.assertTrue(dup_email_res["is_duplicate"])
        self.assertEqual(dup_email_res["field"], "email")
        self.assertIn("Original Student", dup_email_res["message"])
        print("  Passed: Cross-department duplicate student ID and Email correctly blocked with department details.")

    def test_08_qr_email_dispatch_and_resend(self):
        """Test sending student registration details and QR code via email and resend API."""
        print("\n[Test 8] Testing QR Credential Email Generation & Resend Endpoint...")
        ts = int(datetime.now().timestamp())
        test_code = f"QR_MAIL_{ts}"
        test_email = f"qr_student_{ts}@university.edu"
        dept_name = "AI & Data Science"

        person_id = DatabaseService.add_person(test_code, "QR Recipient", dept_name, email=test_email)
        qr_info = QRService.generate_student_qr(person_id, test_code, "QR Recipient", dept_name)
        
        # Test direct EmailService dispatch
        email_result = EmailService.send_student_qr_email(
            student_email=test_email,
            student_name="QR Recipient",
            student_code=test_code,
            department=dept_name,
            qr_code_rel_path=qr_info["qr_code_path"]
        )
        self.assertTrue(email_result["success"])

        # Test Resend API endpoint
        resend_res = self.client.post(f"/api/student/resend-qr-email/{person_id}")
        self.assertEqual(resend_res.status_code, 200)
        res_data = resend_res.get_json()
        self.assertTrue(res_data["success"])
        print(f"  Passed: QR credential email and resend API verified for student #{person_id}.")

    def test_09_face_already_registered_detection(self):
        """Test detection when a student already has face biometrics or when a face matches another student."""
        print("\n[Test 9] Testing Face Already Registered Detection...")
        # Check direct method with synthetic frame
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Should gracefully return is_duplicate=False for blank image
        dup_res = FaceService.check_face_already_registered(dummy_frame, current_person_id=99999)
        self.assertFalse(dup_res["is_duplicate"])

        # Test saving sample for non-existent person returns friendly error
        save_res = FaceService.save_face_sample_from_frame(dummy_frame, person_id=999999)
        self.assertFalse(save_res["success"])
        print("  Passed: Face already registered checking mechanism validated.")

if __name__ == "__main__":
    unittest.main()

