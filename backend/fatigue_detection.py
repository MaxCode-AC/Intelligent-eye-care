
import cv2
import mediapipe as mp
import numpy as np
from sklearn.naive_bayes import GaussianNB
from flask import Flask, Response, jsonify, request
import time
import threading

app = Flask(__name__)

# MediaPipe setup
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True)

# Eye landmark indices (from MediaPipe Face Mesh)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [263, 387, 385, 362, 380, 373]

# Classifier (Naive Bayes)
clf = GaussianNB()
X_train = np.array([[15, 100], [16, 110], [14, 90], [6, 200], [7, 180], [5, 220]])
y_train = np.array([0, 0, 0, 1, 1, 1])
clf.fit(X_train, y_train)

# Global variables
last_blink_time = time.time()
blink_count, frame_counter = 0, 0
blink_durations = []
closed_frames = 0
EAR_THRESH = 0.22
CONSEC_FRAMES = 3
fatigue_status = "Normal"
camera = None
is_camera_active = False
frame_lock = threading.Lock()
frame = None
stop_event = threading.Event()

def eye_aspect_ratio(landmarks, eye_indices):
    p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in eye_indices]
    vertical1 = np.linalg.norm(np.array(p2) - np.array(p6))
    vertical2 = np.linalg.norm(np.array(p3) - np.array(p5))
    horizontal = np.linalg.norm(np.array(p1) - np.array(p4))
    return (vertical1 + vertical2) / (2.0 * horizontal)

def generate_frames():
    global last_blink_time, blink_count, frame_counter, blink_durations, closed_frames, fatigue_status, camera, is_camera_active, frame
    while not stop_event.is_set():
        with frame_lock:
            if not is_camera_active or camera is None:
                time.sleep(0.1)
                continue
            success, frame = camera.read()
            if not success:
                print("Error: Failed to read frame from camera.")
                break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        eyes_detected = False
        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                h, w, _ = frame.shape
                landmarks = [(int(lm.x * w), int(lm.y * h)) for lm in face_landmarks.landmark]

                leftEAR = eye_aspect_ratio(landmarks, LEFT_EYE)
                rightEAR = eye_aspect_ratio(landmarks, RIGHT_EYE)
                avgEAR = (leftEAR + rightEAR) / 2.0

                if avgEAR < EAR_THRESH:
                    closed_frames += 1
                else:
                    if closed_frames >= CONSEC_FRAMES:
                        blink_count += 1
                        blink_durations.append(closed_frames * (1000 / 30))
                    closed_frames = 0

                eyes_detected = True

        if not eyes_detected:
            if time.time() - last_blink_time > 5:
                fatigue_status = "⚠️ Fatigue Detected (Eyes Closed!)"
        else:
            last_blink_time = time.time()
            fatigue_status = "Normal"

        frame_counter += 1
        with frame_lock:
            if frame is not None:
                cv2.putText(frame, f"EAR: {avgEAR:.2f}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Blinks: {blink_count}", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Status: {fatigue_status}", (30, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
            
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def start_camera():
    global camera, is_camera_active
    with frame_lock:
        if camera is None:
            camera = cv2.VideoCapture(0)
            if not camera.isOpened():
                raise RuntimeError("Could not open camera.")
        is_camera_active = True

def stop_camera():
    global is_camera_active, camera
    with frame_lock:
        is_camera_active = False
        if camera is not None:
            camera.release()
            camera = None

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    global blink_count, blink_durations, frame_counter
    with frame_lock:
        if frame_counter > 0:
            avg_duration = np.mean(blink_durations) if blink_durations else 0
            blink_rate = blink_count / (frame_counter / 30 / 60)
            features = np.array([[blink_rate, avg_duration]])
            fatigue_prob = clf.predict_proba(features)[0][1]
            if fatigue_prob > 0.3 or (time.time() - last_blink_time > 5):
                if time.time() - last_blink_time > 5:
                    fatigue_status = "⚠️ Fatigue Detected (Eyes Closed!)"
                    recommendation = "Recommendation: Take a 5-minute break and rest your eyes."
                else:
                    fatigue_status = f"⚠️ Fatigue Detected (Prob: {fatigue_prob:.2f})"
                    recommendation = "Recommendation: Consider taking a short break to reduce eye strain."
            else:
                fatigue_status = "Normal"
                recommendation = "Recommendation: Keep up good eye health habits!"
        else:
            fatigue_status = "Normal"
            recommendation = "Recommendation: Start detection to monitor eye fatigue."
    return jsonify({"fatigue_status": fatigue_status, "recommendation": recommendation})

@app.route('/start_detection', methods=['POST'])
def start_detection():
    try:
        stop_event.clear()
        start_camera()
        return jsonify({"status": "started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stop_detection', methods=['POST'])
def stop_detection():
    stop_camera()
    stop_event.set()
    return jsonify({"status": "stopped"})

if __name__ == "__main__":
    try:
        app.run(host='0.0.0.0', port=5003, debug=True)
    finally:
        stop_event.set()
        with frame_lock:
            if camera is not None:
                camera.release()
                cv2.destroyAllWindows()
