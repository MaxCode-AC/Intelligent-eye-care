from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import time
import sqlite3
import joblib

app = Flask(__name__)
CORS(app)  # Allow frontend (Electron) to call API

# Load fatigue model
model = joblib.load("fatigue_model.pkl")

# Database connection
DB_FILE = "app_usage.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Auto-trigger state
auto_trigger_enabled = False

def check_latest_fatigue():
    """Background job to auto-check fatigue risk every 60s"""
    global auto_trigger_enabled
    while True:
        if auto_trigger_enabled:
            c.execute("""
                SELECT duration_seconds, brightness, start_time
                FROM app_sessions 
                ORDER BY id DESC 
                LIMIT 1
            """)
            row = c.fetchone()

            if row:
                duration_seconds, brightness, start_time = row
                duration_minutes = duration_seconds / 60
                hour = int(start_time[11:13])
                night_session = 1 if (hour >= 22 or hour < 6) else 0

                features = [[duration_minutes, brightness, night_session]]
                prediction = model.predict(features)[0]
                prob = model.predict_proba(features)[0][1]

                if prediction == 1 and prob > 0.7:
                    print("⚠ AUTO WARNING: High fatigue risk detected!")

        time.sleep(60)  # run every 1 minute

# Start background thread
threading.Thread(target=check_latest_fatigue, daemon=True).start()

@app.route("/")
def home():
    return jsonify({"status": "Flask fatigue API running!", "port": 5005})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/predfatigue/latest", methods=["GET"])
def predict_latest():
    """Manual check for latest session fatigue risk"""
    try:
        c.execute("""
            SELECT duration_seconds, brightness, start_time 
            FROM app_sessions 
            ORDER BY id DESC 
            LIMIT 1
        """)
        row = c.fetchone()

        if not row:
            return jsonify({"error": "No app usage data found"})

        duration_seconds, brightness, start_time = row
        duration_minutes = duration_seconds / 60
        hour = int(start_time[11:13])
        night_session = 1 if (hour >= 22 or hour < 6) else 0

        features = [[duration_minutes, brightness, night_session]]
        prediction = model.predict(features)[0]
        prob = model.predict_proba(features)[0][1]

        return jsonify({
            "duration_minutes": duration_minutes,
            "brightness": brightness,
            "night_session": night_session,
            "fatigue_prediction": int(prediction),
            "fatigue_probability": round(float(prob), 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/toggle_autopredfatigue", methods=["POST"])
def toggle_autopredfatigue():
    """Enable or disable auto fatigue warnings"""
    global auto_trigger_enabled
    enabled = request.json.get("enabled", False)
    auto_trigger_enabled = bool(enabled)
    return jsonify({"auto_trigger_enabled": auto_trigger_enabled})

if __name__ == "__main__":
    app.run(port=5005)
