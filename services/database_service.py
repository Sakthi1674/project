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

            # Migration: ensure qr_token and qr_code_path columns exist on persons table
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
                logger.warning(f"Migration check notice: {mig_err}")

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
    def add_person(cls, person_code, name, department, qr_token=None, qr_code_path=None):
        """Inserts a new person/student record. Returns the new person's integer primary key ID."""
        dept = department.strip() if department else "General"
        query = """
            INSERT INTO persons (person_code, name, department, qr_token, qr_code_path)
            VALUES (%s, %s, %s, %s, %s)
        """
        return cls.execute_query(
            query,
            (person_code.strip(), name.strip(), dept, qr_token, qr_code_path),
            commit=True,
            last_id=True
        )

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
    def record_attendance(cls, person_id, qr_session_id=None, status="PRESENT"):
        """Records attendance for person if not already marked for today."""
        now = datetime.now()
        current_date = now.date()
        current_time = now.time().strftime("%H:%M:%S")

        query = """
            INSERT INTO attendance (person_id, qr_session_id, attendance_date, attendance_time, status)
            VALUES (%s, %s, %s, %s, %s)
        """
        return cls.execute_query(query, (person_id, qr_session_id, current_date, current_time, status), commit=True, last_id=True)

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
