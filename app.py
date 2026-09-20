import os
from functools import wraps
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from config import Config
from services.database_service import DatabaseService
from services.face_service import FaceService
from services.qr_service import QRService
from services.attendance_service import AttendanceService
import logging

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("attendance_app")

app = Flask(__name__)
app.config.from_object(Config)

# Ensure required directories exist
os.makedirs(Config.TRAINING_IMAGE_DIR, exist_ok=True)
os.makedirs(Config.TRAINING_LABEL_DIR, exist_ok=True)
os.makedirs(Config.QR_FOLDER, exist_ok=True)
os.makedirs(os.path.join(Config.QR_FOLDER, "students"), exist_ok=True)

# Initialize database schema and ensure student QRs on startup
with app.app_context():
    try:
        DatabaseService.init_db()
        QRService.ensure_all_students_have_qr()
        logger.info("Application database and student credentials initialized successfully.")
    except Exception as e:
        logger.error(f"Startup database initialization error: {e}")

def login_required(f):
    """Decorator to require administrator login for protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please sign in to access the administrator portal.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Context processor to inject common metrics/variables into templates
@app.context_processor
def inject_globals():
    try:
        metrics = DatabaseService.get_dashboard_metrics()
    except Exception:
        metrics = {"total_persons": 0, "present_today": 0, "total_departments": 0}
    
    cutoff_val = Config.get_cutoff_time()
    is_past = AttendanceService.is_past_cutoff(cutoff_val)
    return {
        "metrics": metrics,
        "cutoff_time": cutoff_val,
        "is_past_cutoff": is_past,
        "current_date_today": date.today().isoformat(),
        "logged_in": session.get("logged_in", False),
        "current_username": session.get("username", "Admin")
    }

# -------------------------------------------------------------------
# 1. Welcome Homepage & Authentication
# -------------------------------------------------------------------
@app.route("/")
@app.route("/home")
def home():
    """Welcome Homepage with system details, architecture overview, and login action."""
    try:
        metrics = DatabaseService.get_dashboard_metrics()
        departments = DatabaseService.get_all_departments()
        cutoff_val = Config.get_cutoff_time()
        return render_template(
            "home.html",
            metrics=metrics,
            departments=departments,
            cutoff_time=cutoff_val
        )
    except Exception as e:
        logger.error(f"Home page load error: {e}")
        return render_template("home.html", metrics={}, departments=[], cutoff_time=Config.get_cutoff_time())

@app.route("/login", methods=["GET", "POST"])
def login():
    """Administrator Login page with session authentication."""
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    next_page = request.args.get("next") or url_for("dashboard")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            flash(f"Welcome back, {username}! Signed in successfully.", "success")
            return redirect(next_page)
        else:
            flash("Invalid administrator credentials. Please check your username and password.", "danger")

    return render_template("login.html", next_page=next_page)

@app.route("/logout")
def logout():
    """Signs out of the administrator portal."""
    session.pop("logged_in", None)
    session.pop("username", None)
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("home"))

@app.route("/dashboard", endpoint="dashboard")
@app.route("/index", endpoint="index")
@login_required
def dashboard():
    """Admin Dashboard showing today's attendance performance, live activity, and biometric status."""
    try:
        model_exists = os.path.exists(Config.TRAINER_FILE)
        students = DatabaseService.get_all_students_with_today_status()
        recent_attendance = DatabaseService.get_recent_today_attendance(limit=8)

        total_students = len(students)
        present_today = 0
        absent_today = 0
        face_enrolled_count = 0

        # Enhance each student with sample counts and QR paths
        for s in students:
            s["sample_count"] = FaceService.get_captured_count(s["id"], s["person_code"])
            if s["sample_count"] >= 50:
                face_enrolled_count += 1

            if s["today_status"] == "PRESENT":
                present_today += 1
            else:
                absent_today += 1

            if not s.get("qr_code_path"):
                qr_info = QRService.generate_student_qr(s["id"], s["person_code"], s["name"], s.get("department"))
                s["qr_code_path"] = qr_info["qr_code_path"]

        attendance_rate = round((present_today / total_students * 100), 1) if total_students > 0 else 0.0
        face_coverage_rate = round((face_enrolled_count / total_students * 100), 1) if total_students > 0 else 0.0

        metrics = {
            "total_students": total_students,
            "total_persons": total_students,
            "present_today": present_today,
            "absent_today": absent_today,
            "attendance_rate": attendance_rate,
            "face_enrolled_count": face_enrolled_count,
            "face_pending_count": total_students - face_enrolled_count,
            "face_coverage_rate": face_coverage_rate
        }

        return render_template(
            "index.html",
            metrics=metrics,
            students=students,
            recent_attendance=recent_attendance,
            model_exists=model_exists
        )
    except Exception as e:
        logger.error(f"Dashboard load error: {e}")
        flash(f"Error loading dashboard: {str(e)}", "danger")
        return render_template(
            "index.html",
            metrics={"total_students": 0, "total_persons": 0, "present_today": 0, "absent_today": 0, "attendance_rate": 0, "face_enrolled_count": 0, "face_pending_count": 0, "face_coverage_rate": 0},
            students=[],
            recent_attendance=[],
            model_exists=False
        )

# Backward-compatibility alias for url_for('index')
index = dashboard

# -------------------------------------------------------------------
# 2. Student Registration Flow (Email Service Removed)
# -------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    """Registers a student with department, generates unique student QR, and moves to face capture."""
    departments_list = DatabaseService.get_departments_list()

    if request.method == "POST":
        person_code = request.form.get("person_id", "").strip()
        name = request.form.get("name", "").strip()
        department = request.form.get("department", "").strip() or "General"

        # Validation
        if not person_code or not name:
            flash("Student ID / Roll No. and Full Name are required.", "danger")
            return render_template("register.html", person_code=person_code, name=name, department=department, departments_list=departments_list)

        # Check cross-department uniqueness for person_code
        dup_check = DatabaseService.check_duplicate_student(person_code)
        if dup_check.get("is_duplicate"):
            flash(dup_check["message"], "danger")
            return render_template("register.html", person_code=person_code, name=name, department=department, departments_list=departments_list)

        try:
            # 1. Save student to MySQL (without email)
            new_id = DatabaseService.add_person(person_code, name, department, email=None)
            
            # 2. Automatically generate unique student attendance QR code in department folder
            QRService.generate_student_qr(new_id, person_code, name, department)

            flash(f"Student '{name}' registered successfully and unique QR credential created! Now collect face samples.", "success")
            
            # Redirect to Student QR confirmation card before face capture
            return redirect(url_for("student_qr_page", person_id=new_id))

        except Exception as e:
            logger.error(f"Registration error: {e}")
            flash(f"Failed to register student: {str(e)}", "danger")
            return render_template("register.html", person_code=person_code, name=name, department=department, departments_list=departments_list)

    return render_template("register.html", departments_list=departments_list)

@app.route("/api/department/add", methods=["POST"])
@login_required
def api_add_department():
    """Dynamically adds a new department and returns the updated list for dropdowns."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "message": "Department name cannot be empty."}), 400

    success = DatabaseService.add_department(name)
    departments = DatabaseService.get_departments_list()
    return jsonify({
        "success": success,
        "message": f"Department '{name}' added successfully.",
        "department": name,
        "departments": departments
    })

@app.route("/student-qr/<int:person_id>", methods=["GET"])
@login_required
def student_qr_page(person_id):
    """Displays newly registered student's QR credential with button to face capture."""
    student = DatabaseService.get_person_by_id(person_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("register"))

    if not student.get("qr_code_path"):
        QRService.generate_student_qr(student["id"], student["person_code"], student["name"], student.get("department"))
        student = DatabaseService.get_person_by_id(person_id)

    return render_template("student_qr.html", person=student)

# -------------------------------------------------------------------
# Department Directory & Dedicated Department Pages
# -------------------------------------------------------------------
@app.route("/department/<path:dept_name>", methods=["GET"])
@login_required
def department_detail_page(dept_name):
    """Dedicated separate page for a single department: displays enrolled students, stats, and QR cards."""
    dept_name = dept_name.strip()
    students = DatabaseService.get_students_by_department(dept_name)
    
    # Enhance student data with sample counts and QR paths
    face_enrolled_count = 0
    for s in students:
        s["sample_count"] = FaceService.get_captured_count(s["id"], s["person_code"])
        if s["sample_count"] >= 50:
            face_enrolled_count += 1
        if not s.get("qr_code_path"):
            qr_info = QRService.generate_student_qr(s["id"], s["person_code"], s["name"], s.get("department"))
            s["qr_code_path"] = qr_info["qr_code_path"]
    
    total_students = len(students)
    all_departments = DatabaseService.get_all_departments()
    
    return render_template(
        "department_detail.html",
        dept_name=dept_name,
        students=students,
        total_students=total_students,
        face_enrolled_count=face_enrolled_count,
        all_departments=all_departments
    )

@app.route("/departments", methods=["GET"])
@login_required
def departments_page():
    """Departments view: tap department to view its students & QR credentials."""
    try:
        metrics = DatabaseService.get_dashboard_metrics()
        grouped = DatabaseService.get_persons_grouped_by_department()
        departments = DatabaseService.get_all_departments()

        for dept_name, student_list in grouped.items():
            for s in student_list:
                s["sample_count"] = FaceService.get_captured_count(s["id"], s["person_code"])
                if not s.get("qr_code_path"):
                    qr_info = QRService.generate_student_qr(s["id"], s["person_code"], s["name"], s.get("department"))
                    s["qr_code_path"] = qr_info["qr_code_path"]

        return render_template(
            "departments.html",
            grouped_students=grouped,
            departments=departments,
            metrics=metrics
        )
    except Exception as e:
        logger.error(f"Departments page error: {e}")
        flash(f"Error loading departments: {str(e)}", "danger")
        return render_template("departments.html", grouped_students={}, departments=[], metrics={})

@app.route("/api/department/<dept_name>", methods=["GET"])
@login_required
def api_department_students(dept_name):
    """API endpoint returning students for a specific department."""
    students = DatabaseService.get_students_by_department(dept_name)
    for s in students:
        s["sample_count"] = FaceService.get_captured_count(s["id"], s["person_code"])
    return jsonify({"success": True, "department": dept_name, "count": len(students), "students": students})

@app.route("/api/student-details/<int:person_id>", methods=["GET"])
@login_required
def api_student_complete_details(person_id):
    """Returns complete profile and all previous attendance data for a student."""
    details = DatabaseService.get_student_complete_details(person_id)
    if not details:
        return jsonify({"success": False, "message": "Student not found."}), 404
    return jsonify({"success": True, "student": details})

@app.route("/delete-student/<int:person_id>", methods=["POST"])
@login_required
def delete_student(person_id):
    """Deletes a student, removes their QR code and face training samples."""
    try:
        student = DatabaseService.get_person_by_id(person_id)
        if not student:
            return jsonify({"success": False, "message": "Student not found."}), 404

        name = student["name"]
        code = student["person_code"]
        qr_path = student.get("qr_code_path")

        # 1. Delete student record from MySQL
        DatabaseService.delete_person(person_id)

        # 2. Delete QR code image file
        if qr_path:
            QRService.delete_student_qr(qr_path)

        # 3. Delete face training images
        FaceService.delete_person_face_samples(person_id, code)

        # 4. If training images remain, re-train LBPH model; otherwise clean Trainer.yml
        remaining_images = [f for f in os.listdir(Config.TRAINING_IMAGE_DIR) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
        if len(remaining_images) > 0:
            FaceService.train_lbph_model()
        elif os.path.exists(Config.TRAINER_FILE):
            try:
                os.remove(Config.TRAINER_FILE)
            except Exception:
                pass

        logger.info(f"Deleted student #{person_id} ({name}, {code}) and cleaned assets.")
        return jsonify({
            "success": True,
            "message": f"Student '{name}' ({code}) has been deleted successfully."
        })

    except Exception as e:
        logger.error(f"Error deleting student #{person_id}: {e}")
        return jsonify({"success": False, "message": f"Failed to delete student: {str(e)}"}), 500

@app.route("/clear-all-data", methods=["POST"])
@login_required
def clear_all_data_endpoint():
    """Purges all student records, attendance logs, face datasets, and QR codes with admin password verification."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "").strip()

    if not password:
        return jsonify({"success": False, "message": "Administrator password is required to clear all data."}), 400

    if password != Config.ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Incorrect administrator password. Deletion cancelled."}), 403

    try:
        # 1. Purge database
        DatabaseService.clear_all_student_data()

        # 2. Purge face images
        if os.path.exists(Config.TRAINING_IMAGE_DIR):
            for f in os.listdir(Config.TRAINING_IMAGE_DIR):
                fpath = os.path.join(Config.TRAINING_IMAGE_DIR, f)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

        # 3. Purge trainer model
        if os.path.exists(Config.TRAINER_FILE):
            try:
                os.remove(Config.TRAINER_FILE)
            except Exception:
                pass

        # 4. Purge QR codes
        student_qr_dir = os.path.join(Config.QR_FOLDER, "students")
        if os.path.exists(student_qr_dir):
            for f in os.listdir(student_qr_dir):
                fpath = os.path.join(student_qr_dir, f)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

        # Ensure directories
        FaceService.ensure_directories()
        QRService.ensure_qr_dir()

        logger.info("Purged all student data, attendance logs, and biometric assets via API.")
        return jsonify({"success": True, "message": "All student data, attendance logs, and biometric assets have been completely removed."})
    except Exception as e:
        logger.error(f"Error purging all data: {e}")
        return jsonify({"success": False, "message": f"Failed to clear all data: {str(e)}"}), 500

# -------------------------------------------------------------------
# 3. Face Capture Module
# -------------------------------------------------------------------
@app.route("/capture-face/<int:person_id>", methods=["GET"])
@login_required
def capture_face_page(person_id):
    """Face Capture Page for a registered person."""
    person = DatabaseService.get_person_by_id(person_id)
    if not person:
        flash("Person not found.", "danger")
        return redirect(url_for("register"))

    captured_count = FaceService.get_captured_count(person["id"], person["person_code"])
    return render_template(
        "capture_face.html",
        person=person,
        captured_count=captured_count,
        required_samples=Config.REQUIRED_SAMPLES
    )

@app.route("/capture-face", methods=["POST"])
@login_required
def capture_face():
    """Receives camera snapshot frames from browser to save face sample."""
    data = request.get_json(silent=True) or {}
    person_id = data.get("person_id")
    image_base64 = data.get("image")

    if not person_id or not image_base64:
        return jsonify({"success": False, "message": "Missing person_id or image data"}), 400

    frame_bgr = FaceService.decode_base64_image(image_base64)
    if frame_bgr is None:
        return jsonify({"success": False, "message": "Invalid image data format"}), 400

    result = FaceService.save_face_sample_from_frame(frame_bgr, int(person_id))
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@app.route("/capture-face-opencv", methods=["POST"])
@login_required
def capture_face_opencv():
    """Triggers high-speed native system camera capture for 50 samples with auto-training."""
    data = request.get_json(silent=True) or {}
    person_id = data.get("person_id")
    if not person_id:
        return jsonify({"success": False, "message": "Person ID required."}), 400

    auto_train = data.get("auto_train", True)
    result = FaceService.capture_faces_opencv_native(
        int(person_id), 
        max_samples=Config.REQUIRED_SAMPLES, 
        auto_train=auto_train
    )
    return jsonify(result)

@app.route("/api/captured-count/<int:person_id>", methods=["GET"])
@login_required
def api_captured_count(person_id):
    """Returns live sample count and capture progress for frontend polling."""
    person = DatabaseService.get_person_by_id(person_id)
    if not person or not isinstance(person, dict):
        return jsonify({"success": False, "message": "Person not found", "count": 0}), 404

    count = FaceService.get_captured_count(person["id"], person["person_code"])
    live_status = FaceService.get_capture_status(person["id"])
    return jsonify({
        "success": True,
        "person_id": person_id,
        "count": count,
        "required": Config.REQUIRED_SAMPLES,
        "is_complete": count >= Config.REQUIRED_SAMPLES,
        "percent": min(100, int((count / Config.REQUIRED_SAMPLES) * 100)) if Config.REQUIRED_SAMPLES > 0 else 100,
        "live": live_status
    })

# -------------------------------------------------------------------
# 4. Face Model Training Module
# -------------------------------------------------------------------
@app.route("/train-model", methods=["POST"])
@login_required
def train_model():
    """Trains OpenCV LBPH Face Recognizer and writes to Trainer.yml."""
    result = FaceService.train_lbph_model()
    return jsonify(result)

# -------------------------------------------------------------------
# 5. Student QR Validation & Biometric Cross-Validation Flow
# -------------------------------------------------------------------
@app.route("/attendance", methods=["GET"])
@login_required
def attendance_page():
    """Attendance Terminal: Scan Student QR -> Validate Face -> Mark Attendance."""
    try:
        recent_logs = DatabaseService.get_recent_today_attendance(limit=6)
    except Exception:
        recent_logs = []
    model_exists = os.path.exists(Config.TRAINER_FILE)
    return render_template("attendance.html", recent_logs=recent_logs, model_exists=model_exists)

@app.route("/validate-student-qr", methods=["POST"])
def validate_student_qr():
    """Validates scanned student QR code and returns student profile."""
    data = request.get_json(silent=True) or {}
    qr_data = data.get("qr_data") or data.get("qr_token") or data.get("token")
    if not qr_data:
        return jsonify({"success": False, "message": "No QR data received."}), 400

    result = QRService.validate_student_qr(qr_data)
    status_code = 200 if result["success"] else 404
    return jsonify(result), status_code

@app.route("/verify-student-attendance", methods=["POST"])
def verify_student_attendance():
    """
    Biometric Cross-Validation:
    Checks that the face in front of the camera matches the scanned student,
    checks for duplicate attendance today, and records attendance.
    """
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id") or data.get("person_id")
    image_base64 = data.get("image")

    if not student_id or not image_base64:
        return jsonify({"success": False, "message": "Student ID and camera image are required."}), 400

    frame_bgr = FaceService.decode_base64_image(image_base64)
    if frame_bgr is None:
        return jsonify({"success": False, "message": "Invalid camera frame data."}), 400

    result = AttendanceService.process_student_biometric_attendance(int(student_id), frame_bgr)
    status_code = 200 if result["success"] else 400
    return jsonify(result), status_code

# --- Legacy Dynamic QR endpoints (kept for backwards compatibility) ---
@app.route("/generate-qr", methods=["GET", "POST"])
def generate_qr():
    if request.method == "POST":
        try:
            qr_data = QRService.generate_attendance_qr()
            return jsonify({"success": True, **qr_data})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    return render_template("generate_qr.html")

@app.route("/validate-qr", methods=["POST"])
def validate_qr():
    data = request.get_json(silent=True) or {}
    token = data.get("qr_token") or data.get("token")
    if not token:
        return jsonify({"success": False, "message": "Missing QR token."}), 400
    return jsonify(QRService.validate_qr_token(token))

@app.route("/recognize-face", methods=["POST"])
def recognize_face():
    data = request.get_json(silent=True) or {}
    image_base64 = data.get("image")
    if not image_base64:
        return jsonify({"success": False, "message": "No frame provided."}), 400
    frame_bgr = FaceService.decode_base64_image(image_base64)
    if frame_bgr is None:
        return jsonify({"success": False, "message": "Invalid image data."}), 400
    return jsonify(FaceService.recognize_face_from_frame(frame_bgr))

@app.route("/mark-attendance", methods=["POST"])
def mark_attendance():
    data = request.get_json(silent=True) or {}
    qr_token = data.get("qr_token")
    image_base64 = data.get("image")
    person_id = data.get("person_id")

    if not person_id:
        if not image_base64:
            return jsonify({"success": False, "message": "Camera frame is required."}), 400
        frame_bgr = FaceService.decode_base64_image(image_base64)
        if frame_bgr is None:
            return jsonify({"success": False, "message": "Invalid frame."}), 400
        rec_result = FaceService.recognize_face_from_frame(frame_bgr)
        if not rec_result["success"]:
            return jsonify(rec_result), 400
        person_id = rec_result["person"]["id"]

    result = AttendanceService.process_attendance(int(person_id), qr_token=qr_token)
    status_code = 200 if result["success"] else 400
    return jsonify(result), status_code

# -------------------------------------------------------------------
# 6. Attendance Report & API Module
# -------------------------------------------------------------------
@app.route("/report", methods=["GET"])
@login_required
def report():
    """Attendance Report View with Department-Wise breakdown, present/absent rosters, and status editing."""
    date_filter = request.args.get("date", "").strip() or date.today().isoformat()
    search_query = request.args.get("search", "").strip() or None

    # 1. Department-wise structured attendance breakdown
    dept_attendance = DatabaseService.get_department_wise_attendance(attendance_date=date_filter)

    # If search query provided, filter students in dept_attendance
    if search_query:
        sq_lower = search_query.lower()
        filtered_dept = {}
        for dept_name, data in dept_attendance.items():
            pres_match = [s for s in data["present_students"] if sq_lower in s["name"].lower() or sq_lower in s["person_code"].lower() or sq_lower in dept_name.lower()]
            abs_match = [s for s in data["absent_students"] if sq_lower in s["name"].lower() or sq_lower in s["person_code"].lower() or sq_lower in dept_name.lower()]
            if pres_match or abs_match:
                filtered_dept[dept_name] = {
                    **data,
                    "present_students": pres_match,
                    "absent_students": abs_match,
                    "present_count": len(pres_match),
                    "absent_count": len(abs_match),
                    "total_students": len(pres_match) + len(abs_match)
                }
        dept_attendance = filtered_dept

    # 2. Compute aggregate totals
    overall_total = sum(d["total_students"] for d in dept_attendance.values())
    overall_present = sum(d["present_count"] for d in dept_attendance.values())
    overall_absent = sum(d["absent_count"] for d in dept_attendance.values())
    overall_rate = round((overall_present / overall_total * 100), 1) if overall_total > 0 else 0.0

    # 3. Flat attendance logs for table
    records = AttendanceService.get_report(date_filter=date_filter, search=search_query)

    is_past_cutoff = AttendanceService.is_past_cutoff(Config.ATTENDANCE_CUTOFF_TIME)

    return render_template(
        "report.html",
        dept_attendance=dept_attendance,
        records=records,
        current_date=date_filter,
        search_query=search_query or "",
        overall_total=overall_total,
        overall_present=overall_present,
        overall_absent=overall_absent,
        overall_rate=overall_rate,
        cutoff_time=Config.ATTENDANCE_CUTOFF_TIME,
        is_past_cutoff=is_past_cutoff,
        is_today=(date_filter == date.today().isoformat())
    )

@app.route("/api/attendance/update-status", methods=["POST"])
@login_required
def api_update_attendance_status():
    """
    API endpoint to edit attendance status for a student.
    Disabled by administrator policy: manual Present/Absent editing is prohibited.
    Attendance must be authenticated via QR + Face recognition terminal or cutoff processing.
    """
    return jsonify({
        "success": False,
        "message": "Manual attendance editing is disabled by system policy. Attendance must be verified automatically via the QR + Biometric face terminal or automated cutoff processing."
    }), 403

@app.route("/api/process-absentees", methods=["POST"])
@login_required
def api_process_absentees():
    """
    API endpoint to check attendance cutoff time and mark unmarked students as ABSENT.
    (Email dispatches removed as requested).
    """
    data = request.get_json(silent=True) or {}
    target_date = data.get("date") or date.today().isoformat()
    force = bool(data.get("force", False))

    result = AttendanceService.process_cutoff_absentees(
        cutoff_time_str=Config.ATTENDANCE_CUTOFF_TIME,
        target_date=target_date,
        force=force
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@app.route("/api/attendance", methods=["GET"])
@login_required
def api_attendance():
    """JSON API for attendance logs."""
    date_filter = request.args.get("date", "").strip() or None
    search_query = request.args.get("search", "").strip() or None
    records = AttendanceService.get_report(date_filter=date_filter, search=search_query)
    return jsonify({"success": True, "count": len(records), "data": records})

# -------------------------------------------------------------------
# Error Handlers
# -------------------------------------------------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("index.html", error="404 Page Not Found"), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {e}")
    return render_template("index.html", error="500 Internal Server Error"), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
