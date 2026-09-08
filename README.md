# project
# Face Recognition and QR-Based Attendance System

A complete, production-grade **Attendance Management System using OpenCV LBPH Face Recognition and Dynamic QR Code Validation**, built with Python Flask, MySQL, and modern Vanilla HTML5/CSS3/JavaScript.

The system runs **100% locally** without any paid APIs, third-party cloud services, or external subscriptions.

---

## 🌟 Key Features

* **Admin-Only Management**: Streamlined administration with no student/employee login required.
* **Biometric Face Recognition**:
  * Face detection using Haar Feature-based Cascade Classifiers (`haarcascade_frontalface_default.xml`).
  * Face feature extraction and pattern recognition using OpenCV LBPH (`cv2.face.LBPHFaceRecognizer_create()`).
  * Structured face dataset capture storing 50 grayscale samples named `Name.Serial.PersonID.SampleNumber.jpg` in `TrainingImage/`.
  * One-click model training serialized to `TrainingImageLabel/Trainer.yml`.
* **Dynamic Time-Sensitive QR Validation**:
  * High-entropy cryptographic UUID tokens generated via Python `qrcode`.
  * Automatic 5-minute expiry countdown with real-time progress indicator.
  * Real-time in-browser QR scanning via camera using local `jsQR` (zero external CDN dependence).
* **Robust MySQL Storage**:
  * Tables: `persons`, `qr_sessions`, and `attendance`.
  * Enforces unique daily attendance per person (`UNIQUE(person_id, attendance_date)`).
  * Auto-initialization on startup.
* **Cybernetic Glassmorphic UI**:
  * Deep obsidian theme with neon cyan and emerald glows.
  * Animated laser scanning beam and face positioning reticles.
  * Interactive toasts, modal dialogs, and CSV export.

---

## 🏗️ Architecture & Verification Flow

```
========================================================================
ADMIN WORKFLOW:
1. Register Person (/register)
   └─ Save to MySQL `persons` table
2. Capture Face Samples (/capture-face/<id>)
   ├─ Browser Webcam OR Local OpenCV Window
   └─ Saves 50 images to `TrainingImage/Name.Serial.PersonID.Sample.jpg`
3. Train Model (POST /train-model)
   └─ Trains LBPHFaceRecognizer -> Saves `TrainingImageLabel/Trainer.yml`
4. Generate Dynamic QR (/generate-qr)
   └─ Saves 5-min session to `qr_sessions` & generates `static/qr/<uuid>.png`
========================================================================

========================================================================
ATTENDANCE WORKFLOW:
Open Attendance Terminal (/attendance)
        │
        ▼
[Step 1: Scan QR Code] ────(Invalid/Expired)───► Display Error Alert
        │
     (Valid)
        ▼
[Step 2: Face Recognition] ──(Not Recognized)──► Display Re-align Error
        │
     (Matched)
        ▼
Check Duplicate Today ─────(Already Marked)────► Display "Already Marked"
        │
   (Not Marked)
        ▼
Record Attendance in MySQL ────────────────────► Display Success Card
========================================================================
```

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.10+ / Flask | REST API, session handling, view routing |
| **Biometrics** | OpenCV & OpenCV Contrib | Haar Cascade detection & LBPH face recognition |
| **Database** | MySQL 8.0 & `mysql-connector-python` | Relational storage & connection pooling |
| **QR Code** | `qrcode[pil]` & `jsQR` | Dynamic QR generation & local webcam scanner |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript | Responsive glassmorphism interface |

---

## 📁 Project Directory Structure

```text
Face_recognition_based_attendance_system/
│
├── app.py                     # Main Flask application and REST routes
├── config.py                  # MySQL credentials and configuration settings
├── requirements.txt           # Python dependencies
├── haarcascade_frontalface_default.xml # Bundled Haar Cascade classifier
├── test_system.py             # Automated end-to-end unit test suite
│
├── database/
│   └── database.sql           # MySQL DDL schema
│
├── services/
│   ├── __init__.py
│   ├── database_service.py    # MySQL connection pool and CRUD queries
│   ├── face_service.py        # Face detection, capture, and LBPH recognition
│   ├── qr_service.py          # Dynamic QR generation and validation
│   └── attendance_service.py  # Attendance marking, duplicate check, and logs
│
├── static/
│   ├── css/
│   │   └── style.css          # Modern glassmorphism UI theme
│   ├── js/
│   │   ├── jsqr.js            # Offline local QR decoder engine
│   │   ├── qr-scanner.js      # Webcam QR scanner controller
│   │   └── app.js             # General UI helpers, toasts, camera manager
│   ├── images/                # Static image assets
│   └── qr/                    # Generated dynamic QR code PNGs
│
├── templates/
│   ├── base.html              # Layout skeleton and navigation
│   ├── index.html             # Admin Dashboard
│   ├── register.html          # Person registration form
│   ├── capture_face.html      # 50-sample face capture interface
│   ├── generate_qr.html       # Dynamic QR display with 5-minute timer
│   ├── attendance.html        # 2-step verification terminal
│   └── report.html            # Attendance records table with date filter
│
├── TrainingImage/             # Stored face images: Name.Serial.PersonID.Sample.jpg
└── TrainingImageLabel/
    └── Trainer.yml            # Trained LBPH model file
```

---

## ⚙️ Installation & Setup Guide

### 1. Prerequisites
* **Python 3.10+** (Tested with Python 3.13)
* **MySQL Server 8.0+** running locally on port `3306`
* A computer webcam (integrated or USB)

### 2. Configure MySQL Database
Edit `config.py` if your local MySQL root password is not `root`:

```python
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "your_mysql_password"
DB_NAME = "attendance_system"
```

*Note: The application automatically creates the `attendance_system` database and all tables on startup.*

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Automated Tests
Verify your environment and database connection:
```bash
python test_system.py
```

### 5. Launch the Application
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 📋 Step-by-Step Usage Guide

### 1. Register a Person
1. Click **"Register"** in the top navigation or Dashboard.
2. Enter the unique **Person ID** (e.g. `EMP001`), **Full Name**, and **Department**.
3. Click **"Save Person & Proceed to Face Capture"**.

### 2. Capture Face Samples
1. On the Capture Face page, click **"Start Camera"** and allow webcam access.
2. Align the person's face inside the green oval guide.
3. Click **"Start Capture (50 Samples)"**. The system will capture 50 face images, displaying real-time progress.
4. *(Optional)* Click **"Local OpenCV Window"** if you prefer native OpenCV camera capture.

### 3. Train the Model
1. Click **"Train Face Model"** on the Dashboard or on the Capture page.
2. The system processes all images in `TrainingImage/` and saves `TrainingImageLabel/Trainer.yml`.

### 4. Generate Attendance QR Code
1. Click **"Generate QR"** from the navigation bar.
2. The dynamic QR code will be generated with a live **5-minute countdown**.
3. Keep this screen visible on the attendance kiosk or monitor.

### 5. Mark Attendance (Person Workflow)
1. Open **"Mark Attendance"** (`/attendance`) on the person terminal.
2. **Step 1**: Point the device camera at the generated QR code.
3. Once validated, the terminal transitions to **Step 2: Face Recognition**.
4. Look directly into the camera reticle and click **"Verify Face & Mark Attendance"**.
5. The system verifies the face, checks for duplicates, and records the attendance in MySQL.
6. A confirmation card is displayed with the person's name, department, and timestamp.

### 6. View Attendance Reports
1. Click **"Reports"** (`/report`) to view historical logs.
2. Filter by date, search by name or department, and click **"Export CSV"** to download the records.

---

## 🔒 Error Handling & Edge Cases

* **Expired QR Code**: Rejects scan and prompts user to scan a fresh QR code.
* **Duplicate Attendance**: Prevents marking attendance more than once on the same date for the same person.
* **Unknown Face**: Checks confidence distance against threshold (`CONFIDENCE_THRESHOLD = 75.0`). Rejects unrecognized faces.
* **No Face / Multiple Faces**: Alerts user to align a single face clearly in the camera viewfinder.
* **Missing Model**: Displays warning on the dashboard when `Trainer.yml` needs to be trained.
