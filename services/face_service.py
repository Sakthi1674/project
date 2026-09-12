import os
import re
import base64
import numpy as np
import cv2
# pyrefly: ignore [missing-import]
from PIL import Image
from config import Config
from services.database_service import DatabaseService
import logging

logger = logging.getLogger(__name__)

class FaceService:
    """Handles face detection, sample collection, LBPH model training, and recognition."""

    _cascade = None
    _active_capture_status = {}

    @classmethod
    def get_capture_status(cls, person_id):
        """Returns live status of ongoing system camera capture for a person."""
        return cls._active_capture_status.get(person_id, None)

    @classmethod
    def get_cascade(cls):
        """Loads and caches the Haar Cascade Classifier."""
        if cls._cascade is None or cls._cascade.empty():
            cascade_path = Config.HAAR_CASCADE_FILE
            if not os.path.exists(cascade_path):
                # Fallback to cv2 data directory if available
                cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            
            cls._cascade = cv2.CascadeClassifier(cascade_path)
            if cls._cascade.empty():
                raise RuntimeError(f"Failed to load Haar Cascade from {cascade_path}")
        return cls._cascade

    @classmethod
    def ensure_directories(cls):
        """Creates TrainingImage and TrainingImageLabel directories if missing."""
        os.makedirs(Config.TRAINING_IMAGE_DIR, exist_ok=True)
        os.makedirs(Config.TRAINING_LABEL_DIR, exist_ok=True)

    @classmethod
    def decode_base64_image(cls, base64_str):
        """Decodes base64 image data string into OpenCV BGR numpy array."""
        try:
            if "," in base64_str:
                base64_str = base64_str.split(",")[1]
            image_bytes = base64.b64decode(base64_str)
            np_arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            logger.error(f"Error decoding base64 image: {e}")
            return None

    @classmethod
    def detect_face(cls, image_bgr):
        """
        Detects faces in BGR image.
        Returns: (gray_image, faces_list, error_message)
        faces_list is a list of (x, y, w, h)
        """
        if image_bgr is None:
            return None, [], "No image data provided"

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        cascade = cls.get_cascade()
        
        # Optimized for webcams with varied lighting and distance
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=4,
            minSize=(60, 60)
        )
        
        return gray, faces, None

    @classmethod
    def get_captured_count(cls, serial_id, person_code):
        """Returns the number of already captured samples for a person in TrainingImage/."""
        cls.ensure_directories()
        count = 0
        pattern = re.compile(rf"^.+\.{serial_id}\.{re.escape(str(person_code))}\.(\d+)\.jpg$", re.IGNORECASE)
        for filename in os.listdir(Config.TRAINING_IMAGE_DIR):
            if pattern.match(filename):
                count += 1
        return count

    @classmethod
    def delete_person_face_samples(cls, serial_id, person_code):
        """Deletes all training face images belonging to a person from TrainingImage/."""
        cls.ensure_directories()
        deleted = 0
        pattern = re.compile(rf"^.+\.{serial_id}\.{re.escape(str(person_code))}\.(\d+)\.jpg$", re.IGNORECASE)
        for filename in os.listdir(Config.TRAINING_IMAGE_DIR):
            if pattern.match(filename):
                try:
                    os.remove(os.path.join(Config.TRAINING_IMAGE_DIR, filename))
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Could not delete face sample {filename}: {e}")
        logger.info(f"Deleted {deleted} face samples for student ID #{serial_id} ({person_code})")
        return deleted

    @classmethod
    def save_face_sample_from_frame(cls, frame_bgr, person_id):
        """
        Processes a single camera frame for a registered person:
        1. Detects face.
        2. Crops face ROI in grayscale.
        3. Saves image using format: Name.Serial.PersonID.SampleNumber.jpg
        4. Returns status, current count, thumbnail preview, and total target.
        """
        cls.ensure_directories()
        
        # Verify person exists in DB
        person = DatabaseService.get_person_by_id(person_id)
        if not person or not isinstance(person, dict):
            return {"success": False, "message": f"Person with ID {person_id} not found."}

        # Detect face
        gray, faces, err = cls.detect_face(frame_bgr)
        if err or gray is None:
            return {"success": False, "message": err or "Failed to detect face from image."}

        if len(faces) == 0:
            return {"success": False, "message": "No face detected. Please face the camera directly."}
        elif len(faces) > 1:
            return {"success": False, "message": "Multiple faces detected. Ensure only one person is in frame."}

        # Biometric Duplicate Verification: Verify face does not belong to another registered student
        dup_check = cls.check_face_already_registered(frame_bgr, person_id)
        if dup_check.get("is_duplicate"):
            return {
                "success": False,
                "already_registered": True,
                "message": dup_check["message"],
                "matched_person": dup_check.get("matched_person")
            }

        x, y, w, h = faces[0]
        # Add margin around face for LBPH context
        margin_x = int(w * 0.08)
        margin_y = int(h * 0.08)
        x1 = max(0, x - margin_x)
        y1 = max(0, y - margin_y)
        x2 = min(gray.shape[1], x + w + margin_x)
        y2 = min(gray.shape[0], y + h + margin_y)
        
        face_roi = gray[y1:y2, x1:x2]
        # Standardize face size for LBPH
        face_roi = cv2.resize(face_roi, (200, 200))

        # Determine next sample number avoiding collisions
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', str(person.get('name', ''))) or "Person"
        serial = person["id"]
        code = person["person_code"]

        max_sample = 0
        pattern = re.compile(rf"^.+\.{serial}\.{re.escape(str(code))}\.(\d+)\.jpg$", re.IGNORECASE)
        for fname in os.listdir(Config.TRAINING_IMAGE_DIR):
            m = pattern.match(fname)
            if m:
                try:
                    num = int(m.group(1))
                    if num > max_sample:
                        max_sample = num
                except ValueError:
                    pass

        sample_num = max_sample + 1
        filename = f"{clean_name}.{serial}.{code}.{sample_num}.jpg"
        filepath = os.path.join(Config.TRAINING_IMAGE_DIR, filename)

        success = cv2.imwrite(filepath, face_roi)
        if not success or not os.path.exists(filepath):
            return {"success": False, "message": "Failed to write image to disk. Check permissions."}

        # Count total samples currently saved
        total_count = cls.get_captured_count(serial, code)

        # Generate base64 thumbnail for live UI preview
        thumb_b64 = None
        try:
            _, thumb_buf = cv2.imencode(".jpg", face_roi, [cv2.IMWRITE_JPEG_QUALITY, 80])
            thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(thumb_buf).decode("utf-8")
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Sample #{sample_num} captured successfully.",
            "current_count": total_count,
            "sample_num": sample_num,
            "required_samples": Config.REQUIRED_SAMPLES,
            "is_complete": total_count >= Config.REQUIRED_SAMPLES,
            "filename": filename,
            "thumb": thumb_b64,
            "face_box": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        }

    @classmethod
    def capture_faces_opencv_native(cls, person_id, max_samples=Config.REQUIRED_SAMPLES, auto_train=True):
        """
        Directly uses the system camera (OpenCV) to rapidly capture face samples and save them.
        - Uses DirectShow on Windows for instant camera initialization (<0.5s).
        - Captures at native camera speed with 1ms wait loop (~2 seconds for 50 samples).
        - Crops face with boundary margin and normalizes to 200x200 grayscale for LBPH.
        - Displays live visual HUD, bounding box, progress bar, and sample counter on screen.
        - Automatically trains the LBPH model upon capturing all required samples.
        - Closes window automatically when target is reached or when 'q' is pressed.
        """
        cls.ensure_directories()
        person = DatabaseService.get_person_by_id(person_id)
        if not person or not isinstance(person, dict):
            return {"success": False, "message": f"Person with ID {person_id} not found."}

        # Open system camera directly (prefer DirectShow on Windows for instant initialization)
        cap = None
        if os.name == 'nt':
            try:
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap.release()
                    cap = None
            except Exception:
                cap = None

        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            return {"success": False, "message": "Could not access system camera. Please verify camera connection."}

        # Configure fast capture settings
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        cascade = cls.get_cascade()
        person_name = str(person.get("name") or "Person")
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', person_name) or "Person"
        serial = person["id"]
        code = person["person_code"]
        
        captured = cls.get_captured_count(serial, code)
        target = captured + max_samples
        saved_in_session = 0

        logger.info(f"Starting fast direct system camera capture for {person_name} (ID: {serial}), target: {target}")

        try:
            cls._active_capture_status[serial] = {
                "captured": captured,
                "target": target,
                "saved": 0,
                "percent": int(captured / target * 100) if target > 0 else 0,
                "status": "capturing",
                "person_name": person_name
            }

            frame = None
            h_f, w_f = 480, 640

            while captured < target:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(70, 70))

                for (x, y, w, h) in faces:
                    # Check biometric duplicate on first sample before proceeding
                    if saved_in_session == 0:
                        dup_check = cls.check_face_already_registered(frame, serial)
                        if dup_check.get("is_duplicate"):
                            return {
                                "success": False,
                                "already_registered": True,
                                "message": dup_check["message"],
                                "matched_person": dup_check.get("matched_person")
                            }

                    captured += 1
                    saved_in_session += 1

                    # Add margin around face for better LBPH context
                    margin_x = int(w * 0.06)
                    margin_y = int(h * 0.06)
                    x1 = max(0, x - margin_x)
                    y1 = max(0, y - margin_y)
                    x2 = min(gray.shape[1], x + w + margin_x)
                    y2 = min(gray.shape[0], y + h + margin_y)

                    face_roi = gray[y1:y2, x1:x2]
                    face_roi = cv2.resize(face_roi, (200, 200))
                    
                    filename = f"{clean_name}.{serial}.{code}.{captured}.jpg"
                    filepath = os.path.join(Config.TRAINING_IMAGE_DIR, filename)
                    cv2.imwrite(filepath, face_roi)

                    # Update live status for frontend polling
                    cls._active_capture_status[serial] = {
                        "captured": captured,
                        "target": target,
                        "saved": saved_in_session,
                        "percent": int(captured / target * 100) if target > 0 else 0,
                        "status": "capturing",
                        "person_name": person_name
                    }

                    # Draw vibrant emerald bounding box on face
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 128), 2)
                    cv2.putText(
                        frame,
                        f"Sample {captured}/{target}",
                        (x, max(25, y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 255, 128),
                        2
                    )
                    break  # 1 face per frame

                # Draw top HUD header
                h_f, w_f = frame.shape[:2]
                cv2.rectangle(frame, (0, 0), (w_f, 42), (15, 23, 42), -1)
                cv2.putText(
                    frame,
                    f"System Camera: {person_name} ({code})",
                    (15, 27),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2
                )
                pct_str = f"{captured}/{target} ({int(saved_in_session / max_samples * 100)}%)" if max_samples > 0 else f"{captured}"
                cv2.putText(
                    frame,
                    pct_str,
                    (w_f - 180, 27),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (34, 211, 238),
                    2
                )

                # Draw bottom HUD progress bar
                cv2.rectangle(frame, (15, h_f - 24), (w_f - 15, h_f - 10), (30, 41, 59), -1)
                pct_done = min(1.0, saved_in_session / max_samples) if max_samples > 0 else 1.0
                fill_w = int((w_f - 30) * pct_done)
                if fill_w > 0:
                    cv2.rectangle(frame, (15, h_f - 24), (15 + fill_w, h_f - 10), (0, 255, 128), -1)

                cv2.imshow("Fast Face Capture - System Camera", frame)

                # High-speed loop: 1ms wait allows 30-60 FPS capture
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    logger.info("Face capture stopped by user.")
                    break

            # Brief success splash if target reached
            if captured >= target and frame is not None:
                cv2.rectangle(frame, (40, h_f // 2 - 35), (w_f - 40, h_f // 2 + 35), (16, 185, 129), -1)
                cv2.putText(
                    frame,
                    f"Success! {max_samples} Samples Captured",
                    (60, h_f // 2 + 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (255, 255, 255),
                    2
                )
                cv2.imshow("Fast Face Capture - System Camera", frame)
                cv2.waitKey(400)

            # Auto-train LBPH model immediately upon completing capture
            train_msg = ""
            model_trained = False
            if auto_train and captured >= target:
                logger.info("Auto-training LBPH face recognizer with newly captured samples...")
                train_res = cls.train_lbph_model()
                if train_res.get("success"):
                    model_trained = True
                    train_msg = " LBPH face model automatically trained & updated."
                else:
                    train_msg = f" Note: {train_res.get('message')}"

            return {
                "success": True,
                "message": f"Successfully captured and stored {saved_in_session} samples for {person_name}.{train_msg}",
                "total_captured": captured,
                "target": target,
                "saved_in_session": saved_in_session,
                "model_trained": model_trained
            }
        finally:
            cls._active_capture_status[serial] = {
                "captured": captured,
                "target": target,
                "saved": saved_in_session,
                "percent": 100 if captured >= target else int(captured / target * 100),
                "status": "completed" if captured >= target else "stopped",
                "person_name": person_name
            }
            cap.release()
            cv2.destroyAllWindows()

    @classmethod
    def train_lbph_model(cls):
        """
        Trains the LBPH face recognition model:
        1. Reads all face images in TrainingImage/
        2. Parses the integer serial ID from filename (Name.Serial.PersonID.SampleNumber.jpg)
        3. Trains LBPHFaceRecognizer
        4. Saves model to TrainingImageLabel/Trainer.yml
        """
        cls.ensure_directories()

        if not os.path.exists(Config.TRAINING_IMAGE_DIR):
            return {"success": False, "message": "Training directory does not exist."}

        image_files = [f for f in os.listdir(Config.TRAINING_IMAGE_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

        if len(image_files) == 0:
            return {
                "success": False,
                "message": "No training images found in TrainingImage/ directory. Please capture face images first."
            }

        faces = []
        labels = []
        unique_persons = set()

        for filename in image_files:
            filepath = os.path.join(Config.TRAINING_IMAGE_DIR, filename)
            try:
                # Expected format: Name.Serial.PersonID.SampleNumber.jpg
                parts = filename.split(".")
                if len(parts) >= 5:
                    serial_id = int(parts[1])
                elif len(parts) >= 4:
                    # fallback format: Name.Serial.SampleNumber.jpg
                    serial_id = int(parts[1])
                else:
                    # Try extracting any integer
                    numbers = re.findall(r'\d+', filename)
                    if not numbers:
                        continue
                    serial_id = int(numbers[0])

                # Read image in grayscale using PIL or cv2
                pil_image = Image.open(filepath).convert("L")
                image_np = np.array(pil_image, "uint8")

                # Ensure proper size
                if image_np.shape[0] != 200 or image_np.shape[1] != 200:
                    image_np = cv2.resize(image_np, (200, 200))

                faces.append(image_np)
                labels.append(serial_id)
                unique_persons.add(serial_id)

            except Exception as e:
                logger.warning(f"Skipping corrupt or unparseable image {filename}: {e}")
                continue

        if len(faces) == 0:
            return {
                "success": False,
                "message": "Could not process any valid training face images."
            }

        try:
            # Create LBPH Face Recognizer
            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.train(faces, np.array(labels, dtype=np.int32))
            recognizer.write(Config.TRAINER_FILE)

            logger.info(f"Trained LBPH model with {len(faces)} images across {len(unique_persons)} registered persons.")

            return {
                "success": True,
                "message": f"Face recognition model trained successfully with {len(faces)} samples for {len(unique_persons)} person(s).",
                "total_samples": len(faces),
                "total_persons": len(unique_persons),
                "model_path": Config.TRAINER_FILE
            }
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return {"success": False, "message": f"Model training failed: {str(e)}"}

    @classmethod
    def recognize_face_from_frame(cls, frame_bgr):
        """
        Performs face recognition on an input camera frame:
        1. Checks if Trainer.yml exists.
        2. Detects face.
        3. Predicts person using LBPHFaceRecognizer.
        4. Compares confidence against CONFIDENCE_THRESHOLD.
        5. Returns recognized person details or error.
        """
        # 1. Check if trained model exists
        if not os.path.exists(Config.TRAINER_FILE):
            return {
                "success": False,
                "message": "Face recognition model does not exist. Please train the model in Admin Dashboard first."
            }

        # 2. Detect face
        gray, faces, err = cls.detect_face(frame_bgr)
        if err or gray is None:
            return {"success": False, "message": err or "Failed to process image."}

        if len(faces) == 0:
            return {"success": False, "message": "No face detected in camera frame. Please look directly at the camera."}
        
        if len(faces) > 1:
            return {"success": False, "message": "Multiple faces detected. Only one person should be in camera view."}

        x, y, w, h = faces[0]
        face_roi = gray[y:y+h, x:x+w]
        face_roi = cv2.resize(face_roi, (200, 200))

        # 3. Load model and predict
        try:
            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.read(Config.TRAINER_FILE)

            serial_id, confidence = recognizer.predict(face_roi)
            logger.info(f"LBPH Prediction: Serial={serial_id}, Distance/Confidence={confidence:.2f}")

            # For LBPH, confidence is distance: 0 is exact match, higher values mean less confident.
            if confidence > Config.CONFIDENCE_THRESHOLD:
                return {
                    "success": False,
                    "message": f"Face not recognized (confidence distance {confidence:.1f} exceeds threshold). Please position your face clearly or register.",
                    "confidence_score": round(confidence, 1)
                }

            # Retrieve person from DB
            person = DatabaseService.get_person_by_id(serial_id)
            if not person:
                return {
                    "success": False,
                    "message": f"Recognized label ID #{serial_id} is no longer found in the database."
                }

            # Approximate confidence percentage for display: lower distance = higher match %
            match_percentage = max(10, min(99, int(100 - (confidence / Config.CONFIDENCE_THRESHOLD * 50))))

            return {
                "success": True,
                "person": person,
                "confidence_score": round(confidence, 1),
                "match_percentage": match_percentage,
                "face_box": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
            }

        except Exception as e:
            logger.error(f"Recognition error: {e}")
            return {"success": False, "message": f"Face recognition error: {str(e)}"}

    @classmethod
    def check_face_already_registered(cls, frame_bgr, current_person_id):
        """
        Checks whether the face in frame_bgr matches an already-registered student
        in the system other than current_person_id.
        Returns a dict indicating if a biometric duplicate exists.
        """
        if not os.path.exists(Config.TRAINER_FILE):
            return {"is_duplicate": False}

        try:
            rec_result = cls.recognize_face_from_frame(frame_bgr)
            if rec_result.get("success") and rec_result.get("person"):
                matched_person = rec_result["person"]
                # If the recognized face belongs to a different student
                if int(matched_person["id"]) != int(current_person_id):
                    matched_name = matched_person.get("name") or "Student"
                    matched_code = matched_person.get("person_code") or "N/A"
                    matched_dept = matched_person.get("department") or "General"
                    return {
                        "is_duplicate": True,
                        "already_registered_to_other": True,
                        "matched_person": matched_person,
                        "confidence": rec_result.get("confidence_score"),
                        "match_percentage": rec_result.get("match_percentage"),
                        "message": (
                            f"Face already registered! This face matches enrolled student "
                            f"'{matched_name}' (ID: {matched_code}) in '{matched_dept}' department. "
                            f"Duplicate biometric registration across students is not allowed."
                        )
                    }
                else:
                    return {
                        "is_duplicate": False,
                        "is_same_person": True,
                        "matched_person": matched_person,
                        "confidence": rec_result.get("confidence_score")
                    }
        except Exception as e:
            logger.warning(f"Error checking biometric duplicate: {e}")

        return {"is_duplicate": False}
