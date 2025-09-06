from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

DB_FILE = "app_usage.db"
MODEL_FILE = "productivity_model.pkl"
META_FILE = "productivity_meta.pkl"

# Connect database
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()


PRODUCTIVE_APPS = {"Code.exe", "explorer.exe", "electron.exe", "ShellHost.exe", "WINWORD.EXE", "EXCEL.EXE", "POWERPNT.EXE"}
DISTRACTING_APPS = {"vlc.exe", "chrome.exe", "msedge.exe", "steam.exe", "discord.exe", "spotify.exe"}

def weak_label(app_name):
    if app_name in PRODUCTIVE_APPS:
        return 1
    elif app_name in DISTRACTING_APPS:
        return 0
    return 0

def train_or_load_model():
    last_trained_rows = 0

    if os.path.exists(META_FILE):
        meta = joblib.load(META_FILE)
        last_trained_rows = meta.get("rows", 0)

    df = pd.read_sql_query("SELECT * FROM app_sessions", conn)
    row_count = len(df)

    if os.path.exists(MODEL_FILE) and row_count < last_trained_rows + 100:
        print(f" Loaded model trained on {last_trained_rows} rows (DB now {row_count})")
        return joblib.load(MODEL_FILE)

    if df.empty:
        raise ValueError("No app usage data available to train")

    df["hour"] = pd.to_datetime(df["start_time"]).dt.hour
    df["label"] = df["app"].apply(weak_label)

    le = LabelEncoder()
    df["app_encoded"] = le.fit_transform(df["app"])

    X = df[["duration_seconds", "brightness", "hour", "app_encoded"]]
    y = df["label"]

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)

    joblib.dump((model, le), MODEL_FILE)
    joblib.dump({"rows": row_count}, META_FILE)

    print(f"📈 Retrained productivity model on {row_count} rows")
    return model, le

model, le_app = train_or_load_model()

@app.route("/")
def home():
    return jsonify({"status": "Productivity API running", "port": 5006})

@app.route("/predict/productivity/latest", methods=["GET"])
def predict_latest():
    c.execute("""
        SELECT app, duration_seconds, brightness, start_time
        FROM app_sessions
        ORDER BY id DESC
        LIMIT 1
    """)
    row = c.fetchone()
    if not row:
        return jsonify({"error": "No app usage found"})

    app_name, duration_seconds, brightness, start_time = row
    hour = int(start_time[11:13])

    if app_name in le_app.classes_:
        app_encoded = le_app.transform([app_name])[0]
    else:
        app_encoded = -1

    features = pd.DataFrame([{
        "duration_seconds": duration_seconds,
        "brightness": brightness if brightness else 0,
        "hour": hour,
        "app_encoded": app_encoded
    }])

    pred = model.predict(features)[0]
    prob = model.predict_proba(features)[0].tolist()

    return jsonify({
        "app": app_name,
        "duration_seconds": duration_seconds,
        "brightness": brightness,
        "hour": hour,
        "prediction": "Productive" if pred == 1 else "Distracting",
        "probability": {"distracting": prob[0], "productive": prob[1]}
    })

@app.route("/predict/productivity/daily", methods=["GET"])
def predict_daily():
    """Daily productivity summary with optional date parameter"""
    date_param = request.args.get('date')
    
    if date_param:
        # Filter by specific date
        query = "SELECT * FROM app_sessions WHERE date(start_time) = ?"
        df = pd.read_sql_query(query, conn, params=[date_param])
    else:
        # Default to today
        query = "SELECT * FROM app_sessions WHERE date(start_time) = date('now')"
        df = pd.read_sql_query(query, conn)
    
    if df.empty:
        return jsonify({"error": "No app usage data for selected date"})

    df["hour"] = pd.to_datetime(df["start_time"]).dt.hour
    
    # Predict productivity for each session
    predictions = []
    for _, row in df.iterrows():
        if row["app"] in le_app.classes_:
            app_encoded = le_app.transform([row["app"]])[0]
        else:
            app_encoded = -1
            
        features = [[
            row["duration_seconds"], 
            row["brightness"] or 0, 
            row["hour"], 
            app_encoded
        ]]
        
        pred = model.predict(features)[0]
        predictions.append({
            "app": row["app"],
            "duration_seconds": row["duration_seconds"],
            "prediction": pred,
            "productive": pred == 1
        })

    # Calculate totals
    productive_seconds = sum(p["duration_seconds"] for p in predictions if p["productive"])
    distracting_seconds = sum(p["duration_seconds"] for p in predictions if not p["productive"])
    total_seconds = productive_seconds + distracting_seconds
    
    # Calculate percentages
    productive_percentage = round((productive_seconds / total_seconds * 100), 1) if total_seconds > 0 else 0
    distracting_percentage = round((distracting_seconds / total_seconds * 100), 1) if total_seconds > 0 else 0

    return jsonify({
        "date": date_param if date_param else datetime.now().strftime("%Y-%m-%d"),
        "productive_minutes": round(productive_seconds / 60, 1),
        "distracting_minutes": round(distracting_seconds / 60, 1),
        "total_minutes": round(total_seconds / 60, 1),
        "productive_percentage": productive_percentage,
        "distracting_percentage": distracting_percentage,
        "productive_seconds": productive_seconds,
        "distracting_seconds": distracting_seconds,
        "total_seconds": total_seconds,
        "session_count": len(predictions)
    })

@app.route("/predict/productivity/available_dates", methods=["GET"])
def get_available_dates():
    """Get list of available dates with productivity data"""
    c.execute("""
        SELECT DISTINCT date(start_time) as usage_date 
        FROM app_sessions 
        ORDER BY usage_date DESC
        LIMIT 30
    """)
    dates = [row[0] for row in c.fetchall()]
    return jsonify({"available_dates": dates})

if __name__ == "__main__":
    app.run(port=5006, debug=True)