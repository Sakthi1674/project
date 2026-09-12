import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, date, time
import logging
from config import Config
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)

class EmailService:
    """Handles attendance notifications, absentee alerts, student credentials, and cutoff processing."""

    @classmethod
    def is_smtp_configured(cls):
        """Returns True if SMTP credentials are provided in configuration."""
        Config.get_smtp_config()
        return bool(Config.SMTP_EMAIL and Config.SMTP_PASSWORD and Config.SMTP_SERVER)

    @classmethod
    def send_student_qr_email(cls, student_email, student_name, student_code, department, qr_code_rel_path):
        """
        Sends an official registration email to a student with their enrolled details
        and their unique QR code embedded inline as well as attached for mobile/print usage.
        Falls back gracefully with logging if SMTP is not configured.
        """
        if not student_email or not student_email.strip():
            return {
                "success": False,
                "message": "No email address registered for student."
            }

        student_email = student_email.strip()
        dept_name = department.strip() if department else "General"
        date_today = datetime.now().strftime("%Y-%m-%d")
        cutoff = Config.ATTENDANCE_CUTOFF_TIME

        # Resolve image filepath on disk
        full_qr_path = ""
        if qr_code_rel_path:
            full_qr_path = os.path.join(Config.BASE_DIR, qr_code_rel_path.lstrip("/\\"))

        # If SMTP is not configured, simulate and log gracefully
        if not cls.is_smtp_configured():
            logger.info(
                f"[EMAIL NOTICE] SMTP not configured. Student QR credential email for {student_name} "
                f"({student_code}) in {dept_name} to <{student_email}> logged. QR File: {full_qr_path}"
            )
            return {
                "success": True,
                "simulated": True,
                "message": f"SMTP not configured. Registration details and QR logged for {student_email}."
            }

        try:
            subject = f"Your Attendance QR Credential - {student_name} ({student_code})"

            # Modern Light-Themed HTML Template
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #0f172a; }}
                    .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }}
                    .header {{ background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #ffffff; padding: 28px 24px; text-align: center; }}
                    .header h2 {{ margin: 0 0 6px 0; font-size: 22px; font-weight: 800; letter-spacing: -0.02em; }}
                    .header p {{ margin: 0; font-size: 14px; opacity: 0.9; }}
                    .content {{ padding: 28px; line-height: 1.6; font-size: 15px; }}
                    .details-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin: 20px 0; }}
                    .qr-section {{ text-align: center; margin: 24px 0; padding: 20px; background: #f1f5f9; border-radius: 12px; border: 1px dashed #cbd5e1; }}
                    .qr-img {{ width: 220px; height: 220px; border-radius: 8px; border: 2px solid #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.08); background: #ffffff; padding: 6px; }}
                    .tip-box {{ background: #eff6ff; border-left: 4px solid #2563eb; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: #1e40af; margin-top: 20px; }}
                    .footer {{ background: #f8fafc; padding: 18px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="header">
                        <h2>🎓 Welcome to Attendance Management</h2>
                        <p>Your Student Biometric &amp; QR Attendance Credential</p>
                    </div>
                    <div class="content">
                        <p>Dear <strong>{student_name}</strong>,</p>
                        <p>You have been enrolled in the <strong>Attendance Management System</strong>. Below are your official student registration details and your personal Attendance QR code.</p>
                        
                        <div class="details-box">
                            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                                <tr>
                                    <td style="color: #64748b; padding: 6px 0;">Student Name:</td>
                                    <td style="font-weight: 700; text-align: right; color: #0f172a;">{student_name}</td>
                                </tr>
                                <tr>
                                    <td style="color: #64748b; padding: 6px 0;">Registration / Roll No:</td>
                                    <td style="font-weight: 700; text-align: right; font-family: monospace; color: #2563eb;">{student_code}</td>
                                </tr>
                                <tr>
                                    <td style="color: #64748b; padding: 6px 0;">Department:</td>
                                    <td style="font-weight: 700; text-align: right; color: #0f172a;">{dept_name}</td>
                                </tr>
                                <tr>
                                    <td style="color: #64748b; padding: 6px 0;">Registered Email:</td>
                                    <td style="font-weight: 600; text-align: right; color: #475569;">{student_email}</td>
                                </tr>
                                <tr>
                                    <td style="color: #64748b; padding: 6px 0;">Registration Date:</td>
                                    <td style="font-weight: 600; text-align: right; color: #475569;">{date_today}</td>
                                </tr>
                                <tr>
                                    <td style="color: #64748b; padding: 6px 0;">Daily Cutoff Time:</td>
                                    <td style="font-weight: 700; text-align: right; color: #dc2626;">{cutoff}</td>
                                </tr>
                            </table>
                        </div>

                        <div class="qr-section">
                            <div style="font-size: 14px; font-weight: 700; color: #334155; margin-bottom: 12px;">
                                📱 Your Personal Attendance QR Code
                            </div>
                            <img src="cid:student_qr" alt="Student QR Code" class="qr-img">
                            <div style="font-size: 12px; color: #64748b; margin-top: 10px;">
                                Registration No: <strong>{student_code}</strong> | Folder: <code>{dept_name}</code>
                            </div>
                        </div>

                        <div class="tip-box">
                            <strong>📌 Instructions for Daily Attendance:</strong>
                            <ul style="margin: 6px 0 0 0; padding-left: 18px;">
                                <li>Save the attached QR code image to your smartphone or keep a printed copy.</li>
                                <li>Scan this QR code at the attendance terminal in your department.</li>
                                <li>Look into the camera to complete facial biometric verification.</li>
                                <li>Please ensure you mark your attendance before <strong>{cutoff}</strong> each morning to prevent being marked absent.</li>
                            </ul>
                        </div>
                    </div>
                    <div class="footer">
                        Automated notification sent by Attendance Management System. Please do not reply directly to this email.
                    </div>
                </div>
            </body>
            </html>
            """

            msg = MIMEMultipart("related")
            msg["Subject"] = subject
            msg["From"] = Config.SMTP_EMAIL
            msg["To"] = student_email

            # Create the alternative part for the HTML text
            msg_alt = MIMEMultipart("alternative")
            msg.attach(msg_alt)
            msg_alt.attach(MIMEText(html_body, "html"))

            # Attach QR image if file exists
            if full_qr_path and os.path.exists(full_qr_path):
                with open(full_qr_path, "rb") as img_f:
                    img_data = img_f.read()
                
                # Inline Image for CID
                qr_mime = MIMEImage(img_data)
                qr_mime.add_header("Content-ID", "<student_qr>")
                qr_mime.add_header("Content-Disposition", "inline", filename=f"{student_code}.png")
                msg.attach(qr_mime)

                # Downloadable attachment
                qr_attach = MIMEImage(img_data)
                qr_attach.add_header("Content-Disposition", "attachment", filename=f"{student_code}_attendance_qr.png")
                msg.attach(qr_attach)

            server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10)
            if Config.SMTP_USE_TLS:
                server.starttls()
            server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
            server.sendmail(Config.SMTP_EMAIL, [student_email], msg.as_string())
            server.quit()

            logger.info(f"Successfully dispatched QR credential email to {student_email} for {student_name} ({student_code})")
            return {
                "success": True,
                "simulated": False,
                "message": f"QR credential email successfully sent to {student_email}"
            }

        except Exception as e:
            logger.error(f"Error sending QR credential email to {student_email}: {e}")
            return {
                "success": False,
                "message": f"Failed to send QR email: {str(e)}"
            }

    @classmethod
    def send_absentee_email(cls, student_email, student_name, student_code, cutoff_time, date_str):
        """
        Sends an absentee alert email to a registered student.
        Falls back gracefully with logging if SMTP is not configured.
        """
        if not student_email or not student_email.strip():
            return {
                "success": False,
                "message": "No email address registered for student."
            }

        student_email = student_email.strip()

        # If SMTP credentials are not configured, simulate and log gracefully
        if not cls.is_smtp_configured():
            logger.info(
                f"[EMAIL NOTICE] SMTP not configured. Absentee alert for {student_name} "
                f"({student_code}) to <{student_email}> on {date_str} logged."
            )
            return {
                "success": True,
                "simulated": True,
                "message": f"SMTP not configured. Notification recorded for {student_email}."
            }

        try:
            subject = f"Attendance Notice: Marked Absent for {date_str} - {student_name}"
            
            # HTML Body with clean modern styling
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #0f172a; }}
                    .card {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
                    .header {{ background: #dc2626; color: #ffffff; padding: 24px; text-align: center; }}
                    .header h2 {{ margin: 0; font-size: 20px; font-weight: 700; }}
                    .content {{ padding: 28px; line-height: 1.6; font-size: 15px; }}
                    .badge-absent {{ display: inline-block; background: #fee2e2; color: #b91c1c; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }}
                    .details-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 20px 0; }}
                    .footer {{ background: #f1f5f9; padding: 16px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="header">
                        <h2>⚠️ Attendance Status: ABSENT</h2>
                    </div>
                    <div class="content">
                        <p>Dear <strong>{student_name}</strong>,</p>
                        <p>This is an automated notification from the <strong>Attendance Management System</strong>.</p>
                        <p>You did not mark your attendance before today's cutoff time (<strong>{cutoff_time}</strong>) on <strong>{date_str}</strong>. Therefore, your attendance status for today has been recorded as:</p>
                        
                        <div style="text-align: center; margin: 15px 0;">
                            <span class="badge-absent">ABSENT</span>
                        </div>

                        <div class="details-box">
                            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                                <tr>
                                    <td style="color: #64748b; padding: 4px 0;">Student ID:</td>
                                    <td style="font-weight: 700; text-align: right;">{student_code}</td>
                                </tr>
                                <tr>
                                    <td style="color: #64748b; padding: 4px 0;">Date:</td>
                                    <td style="font-weight: 700; text-align: right;">{date_str}</td>
                                </tr>
                                <tr>
                                    <td style="color: #64748b; padding: 4px 0;">Daily Cutoff Time:</td>
                                    <td style="font-weight: 700; text-align: right;">{cutoff_time}</td>
                                </tr>
                            </table>
                        </div>

                        <p style="font-size: 13px; color: #64748b;">If you believe this status is in error or had an approved leave/on-duty clearance, please contact your department administrator immediately.</p>
                    </div>
                    <div class="footer">
                        Automated notification sent by Attendance Management System. Please do not reply directly to this email.
                    </div>
                </div>
            </body>
            </html>
            """

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = Config.SMTP_EMAIL
            msg["To"] = student_email
            msg.attach(MIMEText(html_body, "html"))

            server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10)
            if Config.SMTP_USE_TLS:
                server.starttls()
            server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
            server.sendmail(Config.SMTP_EMAIL, [student_email], msg.as_string())
            server.quit()

            logger.info(f"Successfully dispatched absentee email to {student_email} for {student_name}")
            return {
                "success": True,
                "simulated": False,
                "message": f"Email successfully sent to {student_email}"
            }

        except Exception as e:
            logger.error(f"Error sending absentee email to {student_email}: {e}")
            return {
                "success": False,
                "message": f"Failed to send email: {str(e)}"
            }

    @classmethod
    def parse_cutoff_time(cls, cutoff_str):
        """Parses HH:MM string to datetime.time object."""
        try:
            parts = cutoff_str.strip().split(":")
            return time(int(parts[0]), int(parts[1]))
        except Exception:
            return time(10, 30)

    @classmethod
    def is_past_cutoff(cls, cutoff_str=None):
        """Checks if current system time is past the specified cutoff time."""
        cutoff_str = cutoff_str or Config.ATTENDANCE_CUTOFF_TIME
        cutoff = cls.parse_cutoff_time(cutoff_str)
        now_time = datetime.now().time()
        return now_time >= cutoff

    @classmethod
    def process_absentees_and_notify(cls, cutoff_time_str=None, target_date=None, force=False):
        """
        Evaluates attendance cutoff:
        1. Verifies current time is past cutoff (unless force=True).
        2. Identifies all students with no 'PRESENT' record for the date.
        3. Marks their status as 'ABSENT' in attendance table.
        4. Sends absentee email to students who have an email address.
        """
        cutoff_time_str = cutoff_time_str or Config.ATTENDANCE_CUTOFF_TIME
        if not target_date:
            target_date = date.today().isoformat()

        # Check cutoff time constraint if checking for today and force is not set
        if not force and target_date == date.today().isoformat():
            if not cls.is_past_cutoff(cutoff_time_str):
                current_hhmm = datetime.now().strftime("%H:%M")
                return {
                    "success": False,
                    "is_before_cutoff": True,
                    "message": f"Current time ({current_hhmm}) is before cutoff time ({cutoff_time_str}). Absentee check runs after cutoff.",
                    "cutoff_time": cutoff_time_str,
                    "current_time": current_hhmm
                }

        # Retrieve unmarked or absent students
        unmarked_students = DatabaseService.get_unmarked_or_absent_students_for_date(target_date)
        if not unmarked_students:
            return {
                "success": True,
                "message": "All students have already marked attendance for today.",
                "total_absentees": 0,
                "emails_sent": 0,
                "cutoff_time": cutoff_time_str,
                "date": target_date
            }

        emails_sent = 0
        emails_failed = 0
        marked_count = 0

        for student in unmarked_students:
            # Mark absent in database
            DatabaseService.update_attendance_status(student["id"], target_date, status="ABSENT")
            marked_count += 1

            # Dispatch notification if student has email
            stu_email = student.get("email")
            if stu_email and stu_email.strip():
                res = cls.send_absentee_email(
                    stu_email,
                    student["name"],
                    student["person_code"],
                    cutoff_time_str,
                    target_date
                )
                if res.get("success"):
                    emails_sent += 1
                else:
                    emails_failed += 1

        logger.info(
            f"Processed absentees for {target_date}: {marked_count} marked ABSENT, "
            f"{emails_sent} notifications dispatched."
        )

        return {
            "success": True,
            "message": f"Processed {marked_count} absentee records. Sent {emails_sent} email notifications.",
            "total_absentees": marked_count,
            "emails_sent": emails_sent,
            "emails_failed": emails_failed,
            "cutoff_time": cutoff_time_str,
            "date": target_date,
            "smtp_configured": cls.is_smtp_configured()
        }
