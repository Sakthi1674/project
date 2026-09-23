import mysql.connector
from mysql.connector import pooling, Error
import os
import logging
from datetime import datetime, date
from config import Config

logger = logging.getLogger(__name__)

class DatabaseService:
    """Handles all MySQL database connections, migrations, and CRUD operations."""
    
    _pool = None

    @classmethod
    def init_db(cls):
        """Initializes database, creates tables, and applies migrations if needed."""
        try:
            # 1. Connect without database selected to ensure database exists
            initial_conn = mysql.connector.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD
            )
            cursor = initial_conn.cursor()
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
            initial_conn.commit()
            cursor.close()
            initial_conn.close()
            logger.info(f"Database '{Config.DB_NAME}' verified/created.")

            # 2. Connect to the specific database and create tables
            conn = mysql.connector.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                database=Config.DB_NAME
            )
            cursor = conn.cursor()

            # Execute SQL script if file exists
            sql_file_path = os.path.join(Config.BASE_DIR, "database", "database.sql")
            if os.path.exists(sql_file_path):
                with open(sql_file_path, "r", encoding="utf-8") as f:
                    sql_commands = f.read().split(";")
                    for command in sql_commands:
                        cmd = command.strip()
                        if cmd:
                            cursor.execute(cmd)
                conn.commit()
                logger.info("Database tables initialized successfully from database.sql.")

            # Migration 1: ensure qr_token and qr_code_path columns exist on persons table
            try:
                cursor.execute("""
                    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'persons' AND COLUMN_NAME = 'qr_token'
                """, (Config.DB_NAME,))
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE persons ADD COLUMN qr_token VARCHAR(255) UNIQUE AFTER department;")
                    cursor.execute("ALTER TABLE persons ADD COLUMN qr_code_path VARCHAR(255) AFTER qr_token;")
                    conn.commit()
                    logger.info("Migrated persons table: added qr_token and qr_code_path columns.")
            except Error as mig_err:
                logger.warning(f"Migration check notice (qr columns): {mig_err}")

            # Migration 2: ensure email column exists on persons table
            try:
                cursor.execute("""
                    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'persons' AND COLUMN_NAME = 'email'
                """, (Config.DB_NAME,))
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE persons ADD COLUMN email VARCHAR(150) AFTER name;")
                    conn.commit()
                    logger.info("Migrated persons table: added email column.")
            except Error as mig_err:
                logger.warning(f"Migration check notice (email column): {mig_err}")

            # Migration 3: ensure departments table exists and seed defaults
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS departments (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB;
                """)
                standard_depts = [
                    "Computer Science",
                    "Information Technology",
                    "AI & Data Science",
                    "Electronics & Communication",
                    "Mechanical Engineering",
                    "Electrical & Electronics",
                    "Civil Engineering"
                ]
                for dept_name in standard_depts:
                    cursor.execute("INSERT IGNORE INTO departments (name) VALUES (%s)", (dept_name,))
                conn.commit()
                logger.info("Departments table verified and standard departments seeded.")
            except Error as mig_err:
                logger.warning(f"Migration check notice (departments): {mig_err}")

            cursor.close()
            conn.close()

            # 3. Setup Connection Pool
            cls._pool = pooling.MySQLConnectionPool(
                pool_name="attendance_pool",
                pool_size=5,
                pool_reset_session=True,
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                database=Config.DB_NAME
            )
            logger.info("MySQL Connection Pool initialized successfully.")
            return True

        except Error as e:
            logger.error(f"Error initializing MySQL Database: {e}")
            raise e

    @classmethod
    def get_connection(cls):
        """Returns a connection from pool or creates a standalone connection."""
        if cls._pool is None:
            cls.init_db()
        try:
            return cls._pool.get_connection()
        except Error:
            # Fallback to direct connection if pool is exhausted or unavailable
            return mysql.connector.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                database=Config.DB_NAME
            )

    @classmethod
    def execute_query(cls, query, params=None, commit=False, fetch_one=False, fetch_all=False, last_id=False):
        """Generic helper to execute parameterized queries safely."""
        conn = None
        cursor = None
        try:
            conn = cls.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            
            if commit:
                conn.commit()
                if last_id:
                    return cursor.lastrowid
                return True
                
            if fetch_one:
                return cursor.fetchone()
                
            if fetch_all:
                return cursor.fetchall()
                
            return None
        except Error as e:
            logger.error(f"Database query error: {e} | Query: {query} | Params: {params}")
            if conn and commit:
                conn.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # --- Person / Student Management ---
    @classmethod
    def add_person(cls, person_code, name, department, email=None, qr_token=None, qr_code_path=None):
        """Inserts a new person/student record with email. Returns the new person's integer primary key ID."""
        dept = department.strip() if department else "General"
        clean_email = email.strip() if email else None
        
        # Ensure department exists in departments table
        if dept and dept != "General":
            cls.add_department(dept)

        query = """
            INSERT INTO persons (person_code, name, email, department, qr_token, qr_code_path)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        return cls.execute_query(
            query,
            (person_code.strip(), name.strip(), clean_email, dept, qr_token, qr_code_path),
            commit=True,
            last_id=True
        )

    # --- Department Management ---
    @classmethod
    def get_departments_list(cls):
        """Returns sorted list of unique department names from departments table and persons table."""
        query = """
            SELECT DISTINCT name FROM (
                SELECT name FROM departments
                UNION
                SELECT COALESCE(NULLIF(department, ''), 'General') AS name FROM persons
            ) AS combined_depts
            WHERE name IS NOT NULL AND name != ''
            ORDER BY name ASC
        """
        rows = cls.execute_query(query, fetch_all=True) or []
        depts = [r["name"] for r in rows if r.get("name")]
        if not depts:
            depts = ["Computer Science", "Information Technology", "AI & Data Science", "Electronics & Communication", "Mechanical Engineering"]
        return depts

    @classmethod
    def add_department(cls, name):
        """Inserts a new department name into the departments table."""
        if not name or not name.strip():
            return False
        dept_name = name.strip()
        try:
            query = "INSERT IGNORE INTO departments (name) VALUES (%s)"
            cls.execute_query(query, (dept_name,), commit=True)
            logger.info(f"Department added/verified: '{dept_name}'")
            return True
        except Exception as e:
            logger.error(f"Error adding department '{dept_name}': {e}")
            return False

    @classmethod
    def update_person_qr(cls, person_id, qr_token, qr_code_path):
        """Updates a student's unique QR code token and image path."""
        query = """
            UPDATE persons
            SET qr_token = %s, qr_code_path = %s
            WHERE id = %s
        """
        return cls.execute_query(query, (qr_token, qr_code_path, person_id), commit=True)

    @classmethod
    def get_person_by_id(cls, person_id):
        """Fetches person by integer id."""
        query = "SELECT * FROM persons WHERE id = %s"
        return cls.execute_query(query, (person_id,), fetch_one=True)

    @classmethod
    def get_person_by_code(cls, person_code):
        """Fetches person by unique person_code."""
        query = "SELECT * FROM persons WHERE person_code = %s"
        return cls.execute_query(query, (person_code.strip(),), fetch_one=True)

    @classmethod
    def get_person_by_email(cls, email):
        """Fetches person by email address."""
        if not email or not email.strip():
            return None
        query = "SELECT * FROM persons WHERE LOWER(TRIM(email)) = LOWER(%s)"
        return cls.execute_query(query, (email.strip(),), fetch_one=True)

    @classmethod
    def check_duplicate_student(cls, person_code, email=None, exclude_person_id=None):
        """
        Checks if person_code or email already exists in any department.
        Returns a dict indicating whether a duplicate exists with the conflicting department.
        """
        if person_code and person_code.strip():
            code_clean = person_code.strip()
            query = "SELECT * FROM persons WHERE LOWER(TRIM(person_code)) = LOWER(%s)"
            params = [code_clean]
            if exclude_person_id:
                query += " AND id != %s"
                params.append(exclude_person_id)
            existing_code = cls.execute_query(query, params, fetch_one=True)
            if existing_code:
                dept = existing_code.get("department") or "General"
                name = existing_code.get("name") or "Unknown"
                return {
                    "is_duplicate": True,
                    "field": "person_code",
                    "message": (
                        f"Student ID / Roll No. '{code_clean}' is already registered in '{dept}' department "
                        f"under student '{name}'. Duplicate student registration across departments is not allowed."
                    ),
                    "existing_person": existing_code
                }

        if email and email.strip():
            email_clean = email.strip()
            query = "SELECT * FROM persons WHERE LOWER(TRIM(email)) = LOWER(%s)"
            params = [email_clean]
            if exclude_person_id:
                query += " AND id != %s"
                params.append(exclude_person_id)
            existing_email = cls.execute_query(query, params, fetch_one=True)
            if existing_email:
                dept = existing_email.get("department") or "General"
                name = existing_email.get("name") or "Unknown"
                code = existing_email.get("person_code") or "N/A"
                return {
                    "is_duplicate": True,
                    "field": "email",
                    "message": (
                        f"Email '{email_clean}' is already registered to student '{name}' ({code}) "
                        f"in department '{dept}'. A student cannot be registered multiple times across departments."
                    ),
                    "existing_person": existing_email
                }

        return {"is_duplicate": False, "field": None, "message": None, "existing_person": None}

    @classmethod
    def get_person_by_qr_token(cls, qr_token):
        """Fetches student by their unique QR token or person_code."""
        query = "SELECT * FROM persons WHERE qr_token = %s OR person_code = %s"
        return cls.execute_query(query, (qr_token.strip(), qr_token.strip()), fetch_one=True)

    @classmethod
    def delete_person(cls, person_id):
        """Deletes a student record and returns the deleted record info."""
        person = cls.get_person_by_id(person_id)
        if not person:
            return None
        cls.execute_query("DELETE FROM persons WHERE id = %s", (person_id,), commit=True)
        return person

    @classmethod
    def clear_all_student_data(cls):
        """Completely purges all student records, attendance logs, and sessions from MySQL."""
        cls.execute_query("DELETE FROM attendance", commit=True)
        cls.execute_query("DELETE FROM persons", commit=True)
        cls.execute_query("DELETE FROM qr_sessions", commit=True)
        try:
            cls.execute_query("ALTER TABLE attendance AUTO_INCREMENT = 1", commit=True)
            cls.execute_query("ALTER TABLE persons AUTO_INCREMENT = 1", commit=True)
            cls.execute_query("ALTER TABLE qr_sessions AUTO_INCREMENT = 1", commit=True)
        except Exception as e:
            logger.warning(f"Could not reset auto_increment: {e}")
        return True

    @classmethod
    def get_students_by_department(cls, department_name):
        """Fetches all students belonging to a specific department."""
        query = """
            SELECT * FROM persons 
            WHERE COALESCE(NULLIF(department, ''), 'General') = %s 
            ORDER BY name ASC
        """
        return cls.execute_query(query, (department_name.strip(),), fetch_all=True)

    @classmethod
    def get_all_persons(cls):
        """Returns list of all registered persons sorted alphabetically."""
        query = "SELECT * FROM persons ORDER BY name ASC"
        return cls.execute_query(query, fetch_all=True)

    @classmethod
    def get_all_departments(cls):
        """Returns distinct department names with student count."""
        query = """
            SELECT 
                COALESCE(NULLIF(department, ''), 'General') AS department_name, 
                COUNT(*) as student_count
            FROM persons 
            GROUP BY COALESCE(NULLIF(department, ''), 'General')
            ORDER BY department_name ASC
        """
        return cls.execute_query(query, fetch_all=True) or []

    @classmethod
    def get_persons_grouped_by_department(cls):
        """
        Returns all students grouped by department as a dictionary:
        { 'Department Name': [ { student1 }, { student2 } ] }
        """
        query = """
            SELECT 
                id, 
                person_code, 
                name, 
                COALESCE(NULLIF(department, ''), 'General') AS department,
                qr_token,
                qr_code_path,
                created_at
            FROM persons 
            ORDER BY department ASC, name ASC
        """
        rows = cls.execute_query(query, fetch_all=True) or []
        grouped = {}
        for row in rows:
            dept = row["department"]
            if dept not in grouped:
                grouped[dept] = []
            grouped[dept].append(row)
        return grouped

    @classmethod
    def get_all_students_with_today_status(cls):
        """
        Returns all registered students with today's attendance status and check-in time.
        """
        query = """
            SELECT 
                p.id, 
                p.person_code, 
                p.name, 
                COALESCE(NULLIF(p.department, ''), 'General') AS department, 
                p.qr_code_path,
                a.id AS attendance_id,
                a.attendance_time,
                COALESCE(a.status, 'UNMARKED') AS today_status
            FROM persons p
            LEFT JOIN attendance a ON p.id = a.person_id AND a.attendance_date = CURDATE()
            ORDER BY p.name ASC
        """
        return cls.execute_query(query, fetch_all=True) or []

    # --- QR Session Management ---
    @classmethod
    def create_qr_session(cls, qr_token, expires_at):
        """Creates an active QR session record with expiration timestamp."""
        query = """
            INSERT INTO qr_sessions (qr_token, expires_at, status)
            VALUES (%s, %s, 'ACTIVE')
        """
        return cls.execute_query(query, (qr_token, expires_at), commit=True, last_id=True)

    @classmethod
    def get_qr_session(cls, qr_token):
        """Retrieves QR session details by token."""
        query = "SELECT * FROM qr_sessions WHERE qr_token = %s"
        return cls.execute_query(query, (qr_token.strip(),), fetch_one=True)

    @classmethod
    def expire_qr_session(cls, qr_token):
        """Marks a QR session as EXPIRED."""
        query = "UPDATE qr_sessions SET status = 'EXPIRED' WHERE qr_token = %s"
        return cls.execute_query(query, (qr_token.strip(),), commit=True)

    @classmethod
    def expire_old_sessions(cls):
        """Marks all past-expiry sessions as EXPIRED."""
        query = "UPDATE qr_sessions SET status = 'EXPIRED' WHERE expires_at < NOW() AND status = 'ACTIVE'"
        return cls.execute_query(query, commit=True)

    # --- Attendance Management ---
    @classmethod
    def check_today_attendance(cls, person_id):
        """Checks if person already marked attendance for today."""
        query = """
            SELECT a.*, p.name, p.person_code, p.department
            FROM attendance a
            JOIN persons p ON a.person_id = p.id
            WHERE a.person_id = %s AND a.attendance_date = CURDATE()
        """
        return cls.execute_query(query, (person_id,), fetch_one=True)

    @classmethod
    def get_recent_today_attendance(cls, limit=6):
        """Returns recent attendance records logged today with student details."""
        query = """
            SELECT 
                a.id, 
                a.attendance_time, 
                a.status, 
                p.name, 
                p.person_code, 
                COALESCE(NULLIF(p.department, ''), 'General') AS department
            FROM attendance a
            JOIN persons p ON a.person_id = p.id
            WHERE a.attendance_date = CURDATE() AND a.status = 'PRESENT'
            ORDER BY a.attendance_time DESC, a.id DESC
            LIMIT %s
        """
        return cls.execute_query(query, (limit,), fetch_all=True) or []

    @classmethod
    def record_attendance(cls, person_id, qr_session_id=None, status="PRESENT"):
        """Records attendance for person if not already marked for today."""
        now = datetime.now()
        current_date = now.date()
        current_time = now.time().strftime("%H:%M:%S")

        query = """
            INSERT INTO attendance (person_id, qr_session_id, attendance_date, attendance_time, status)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                attendance_time = VALUES(attendance_time),
                status = VALUES(status),
                qr_session_id = COALESCE(VALUES(qr_session_id), qr_session_id)
        """
        return cls.execute_query(query, (person_id, qr_session_id, current_date, current_time, status), commit=True, last_id=True)

    @classmethod
    def update_attendance_status(cls, person_id, attendance_date=None, status="PRESENT"):
        """
        Updates or inserts an attendance record for a student on a specific date.
        Allows toggling between PRESENT and ABSENT.
        """
        if not attendance_date:
            attendance_date = date.today().isoformat()
        
        status_clean = status.upper().strip()
        now = datetime.now()
        current_time = now.time().strftime("%H:%M:%S")

        # Check existing record
        query_check = "SELECT id, status FROM attendance WHERE person_id = %s AND attendance_date = %s"
        existing = cls.execute_query(query_check, (person_id, attendance_date), fetch_one=True)

        if existing:
            query_update = """
                UPDATE attendance 
                SET status = %s, attendance_time = %s 
                WHERE id = %s
            """
            cls.execute_query(query_update, (status_clean, current_time, existing["id"]), commit=True)
            return {"success": True, "action": "updated", "id": existing["id"], "status": status_clean}
        else:
            query_insert = """
                INSERT INTO attendance (person_id, attendance_date, attendance_time, status)
                VALUES (%s, %s, %s, %s)
            """
            new_id = cls.execute_query(query_insert, (person_id, attendance_date, current_time, status_clean), commit=True, last_id=True)
            return {"success": True, "action": "created", "id": new_id, "status": status_clean}

    @classmethod
    def get_department_wise_attendance(cls, attendance_date=None):
        """
        Returns complete department-wise attendance breakdown for a given date:
        Totals, Present, Absent, and student rosters with individual status.
        """
        if not attendance_date:
            attendance_date = date.today().isoformat()

        query = """
            SELECT 
                p.id AS person_id,
                p.person_code,
                p.name,
                p.email,
                COALESCE(NULLIF(p.department, ''), 'General') AS department,
                p.qr_code_path,
                a.id AS attendance_id,
                a.attendance_date,
                a.attendance_time,
                COALESCE(a.status, 'UNMARKED') AS status
            FROM persons p
            LEFT JOIN attendance a 
                ON p.id = a.person_id AND a.attendance_date = %s
            ORDER BY department ASC, p.name ASC
        """
        rows = cls.execute_query(query, (attendance_date,), fetch_all=True) or []

        dept_summary = {}
        for r in rows:
            dept = r["department"]
            if dept not in dept_summary:
                dept_summary[dept] = {
                    "department_name": dept,
                    "total_students": 0,
                    "present_count": 0,
                    "absent_count": 0,
                    "attendance_rate": 0.0,
                    "present_students": [],
                    "absent_students": []
                }

            dept_summary[dept]["total_students"] += 1
            student_info = {
                "id": r["person_id"],
                "person_code": r["person_code"],
                "name": r["name"],
                "email": r.get("email") or "",
                "department": dept,
                "qr_code_path": r.get("qr_code_path") or "",
                "attendance_id": r["attendance_id"],
                "date": attendance_date,
                "time": str(r["attendance_time"]) if r.get("attendance_time") else "",
                "status": r["status"]
            }

            if r["status"] == "PRESENT":
                dept_summary[dept]["present_count"] += 1
                dept_summary[dept]["present_students"].append(student_info)
            else:
                dept_summary[dept]["absent_count"] += 1
                if student_info["status"] == "UNMARKED":
                    student_info["status"] = "ABSENT"
                dept_summary[dept]["absent_students"].append(student_info)

        # Compute attendance rate
        for dept, data in dept_summary.items():
            tot = data["total_students"]
            pres = data["present_count"]
            data["attendance_rate"] = round((pres / tot * 100), 1) if tot > 0 else 0.0

        return dept_summary

    @classmethod
    def get_unmarked_or_absent_students_for_date(cls, attendance_date=None):
        """
        Returns all registered students who have not marked PRESENT for a specific date.
        Used for cutoff absentee notifications.
        """
        if not attendance_date:
            attendance_date = date.today().isoformat()

        query = """
            SELECT 
                p.id,
                p.person_code,
                p.name,
                p.email,
                COALESCE(NULLIF(p.department, ''), 'General') AS department,
                a.id AS attendance_id,
                a.status
            FROM persons p
            LEFT JOIN attendance a 
                ON p.id = a.person_id AND a.attendance_date = %s
            WHERE a.status IS NULL OR a.status != 'PRESENT'
            ORDER BY department ASC, p.name ASC
        """
        return cls.execute_query(query, (attendance_date,), fetch_all=True) or []

    @classmethod
    def get_unmarked_students_for_date(cls, attendance_date=None):
        """
        Returns all registered students who have NO attendance record (neither PRESENT nor ABSENT)
        for a specific date. Used to idempotently process and mark absentees upon cutoff.
        """
        if not attendance_date:
            attendance_date = date.today().isoformat()

        query = """
            SELECT 
                p.id,
                p.person_code,
                p.name,
                p.email,
                COALESCE(NULLIF(p.department, ''), 'General') AS department
            FROM persons p
            LEFT JOIN attendance a 
                ON p.id = a.person_id AND a.attendance_date = %s
            WHERE a.id IS NULL
            ORDER BY department ASC, p.name ASC
        """
        return cls.execute_query(query, (attendance_date,), fetch_all=True) or []

    @classmethod
    def get_attendance_logs(cls, date_filter=None, search=None):
        """Fetches attendance records with person details, optional date and name filters."""
        query = """
            SELECT 
                a.id AS attendance_id,
                a.person_id,
                p.person_code,
                p.name,
                p.department,
                a.attendance_date,
                a.attendance_time,
                a.status,
                a.qr_session_id,
                qs.qr_token
            FROM attendance a
            JOIN persons p ON a.person_id = p.id
            LEFT JOIN qr_sessions qs ON a.qr_session_id = qs.id
            WHERE 1=1
        """
        params = []
        if date_filter:
            query += " AND a.attendance_date = %s"
            params.append(date_filter)
            
        if search:
            query += " AND (p.name LIKE %s OR p.person_code LIKE %s OR p.department LIKE %s)"
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])
            
        query += " ORDER BY a.attendance_date DESC, a.attendance_time DESC"
        return cls.execute_query(query, params, fetch_all=True)

    @classmethod
    def get_dashboard_metrics(cls):
        """Returns statistics for dashboard cards."""
        # 1. Total registered persons
        p_res = cls.execute_query("SELECT COUNT(*) AS total FROM persons", fetch_one=True)
        total_persons = p_res["total"] if p_res else 0

        # 2. Total present today
        a_res = cls.execute_query("SELECT COUNT(*) AS total FROM attendance WHERE attendance_date = CURDATE()", fetch_one=True)
        present_today = a_res["total"] if a_res else 0

        # 3. Total departments
        d_res = cls.execute_query("SELECT COUNT(DISTINCT department) AS total FROM persons WHERE department IS NOT NULL AND department != ''", fetch_one=True)
        total_depts = d_res["total"] if d_res else 0

        return {
            "total_persons": total_persons,
            "present_today": present_today,
            "total_departments": total_depts
        }

    @classmethod
    def get_student_complete_details(cls, person_id):
        """
        Returns full profile information and all previous attendance history for a student.
        """
        person = cls.get_person_by_id(person_id)
        if not person:
            return None

        # 1. Face sample count
        from services.face_service import FaceService
        sample_count = FaceService.get_captured_count(person["id"], person.get("person_code", ""))

        # 2. Complete Attendance History (All Previous Data)
        query = """
            SELECT 
                id AS attendance_id,
                attendance_date,
                attendance_time,
                status
            FROM attendance
            WHERE person_id = %s
            ORDER BY attendance_date DESC, attendance_time DESC
        """
        history_rows = cls.execute_query(query, (person_id,), fetch_all=True) or []

        total_sessions = len(history_rows)
        present_count = sum(1 for h in history_rows if h.get("status") == "PRESENT")
        absent_count = sum(1 for h in history_rows if h.get("status") == "ABSENT")
        rate = round((present_count / total_sessions * 100), 1) if total_sessions > 0 else 0.0

        history = []
        for h in history_rows:
            history.append({
                "id": h["attendance_id"],
                "date": str(h["attendance_date"]),
                "time": str(h["attendance_time"]) if h.get("attendance_time") else "Recorded",
                "status": h["status"]
            })

        return {
            "id": person["id"],
            "person_code": person["person_code"],
            "name": person["name"],
            "email": person.get("email") or "Not provided",
            "department": person.get("department") or "General",
            "qr_code_path": person.get("qr_code_path") or "",
            "created_at": str(person.get("created_at") or ""),
            "sample_count": sample_count,
            "face_enrolled": sample_count >= 50,
            "total_sessions": total_sessions,
            "present_count": present_count,
            "absent_count": absent_count,
            "attendance_rate": rate,
            "history": history
        }
