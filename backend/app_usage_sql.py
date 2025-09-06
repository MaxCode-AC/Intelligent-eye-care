import time, psutil, win32gui, win32process, threading, sqlite3
import screen_brightness_control as sbc
import platform
import subprocess
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database setup
DB_FILE = "app_usage.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Database setup with session tracking including brightness and theme
c.execute("""
CREATE TABLE IF NOT EXISTS app_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app TEXT,
    start_time TEXT,
    end_time TEXT,
    duration_seconds INTEGER,
    brightness INTEGER,
    theme_mode TEXT
)
""")
conn.commit()

# Track current app session
current_app = None
session_start_time = None

def get_active_app():
    try:
        hwnd = win32gui.GetForegroundWindow()
        tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        return process.name()
    except Exception:
        return "Unknown"

def get_current_brightness():
    """Get current screen brightness"""
    try:
        return sbc.get_brightness()[0]  # Returns first monitor's brightness
    except:
        return None

def get_current_theme():
    """Get current system theme"""
    try:
        if platform.system() == "Windows":
            # Windows theme detection using registry
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return "Light" if value == 1 else "Dark"
            except:
                return "Unknown"
        elif platform.system() == "Darwin":  # macOS
            # macOS theme detection
            result = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'], 
                                  capture_output=True, text=True)
            return "Dark" if "Dark" in result.stdout else "Light"
        else:
            # Linux or other - try to detect from environment
            return "Unknown"
    except:
        return "Unknown"

def log_active_app():
    """Background loop: track app sessions with start/end times including brightness and theme"""
    global current_app, session_start_time
    
    while True:
        app_name = get_active_app()
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        current_brightness = get_current_brightness()
        current_theme = get_current_theme()
        
       
        if app_name != current_app:
          
            if current_app is not None and session_start_time is not None:
                duration = int(time.time() - time.mktime(time.strptime(session_start_time, "%Y-%m-%d %H:%M:%S")))
                c.execute(
                    "INSERT INTO app_sessions (app, start_time, end_time, duration_seconds, brightness, theme_mode) VALUES (?, ?, ?, ?, ?, ?)",
                    (current_app, session_start_time, current_time, duration, current_brightness, current_theme)
                )
                conn.commit()
                print(f"Session ended: {current_app} ({duration}s), Brightness: {current_brightness}%, Theme: {current_theme}")
            
            # Start new session
            current_app = app_name
            session_start_time = current_time
            print(f"Session started: {app_name}, Brightness: {current_brightness}%, Theme: {current_theme}")
        
        time.sleep(5)  # Check every 5 seconds, but only log session changes

@app.route("/app_report", methods=["GET"])
def app_report():
    """Get recent app sessions with brightness and theme data"""
    c.execute("""
        SELECT app, start_time, end_time, duration_seconds, brightness, theme_mode 
        FROM app_sessions 
        ORDER BY id DESC 
        LIMIT 100
    """)
    rows = c.fetchall()
    sessions = [{
        "app": row[0], 
        "start_time": row[1], 
        "end_time": row[2],
        "duration": row[3],
        "brightness": row[4],
        "theme_mode": row[5]
    } for row in rows]
    return jsonify(sessions)

@app.route("/usage_summary", methods=["GET"])
def usage_summary():
    """Get usage summary by app with brightness and theme statistics"""
    c.execute("""
        SELECT 
            app,
            COUNT(*) as session_count,
            SUM(duration_seconds) as total_seconds,
            AVG(duration_seconds) as avg_duration,
            AVG(brightness) as avg_brightness,
            GROUP_CONCAT(DISTINCT theme_mode) as themes_used
        FROM app_sessions 
        WHERE date(start_time) = date('now')
        GROUP BY app
        ORDER BY total_seconds DESC
    """)
    rows = c.fetchall()
    summary = [{
        "app": row[0],
        "session_count": row[1],
        "total_seconds": row[2],
        "total_minutes": round(row[2] / 60, 1),
        "avg_duration": round(row[3], 1) if row[3] else 0,
        "avg_brightness": round(row[4], 1) if row[4] else "N/A",
        "themes_used": row[5] if row[5] else "Unknown"
    } for row in rows]
    return jsonify(summary)

@app.route("/brightness_stats", methods=["GET"])
def brightness_stats():
    """Get brightness statistics"""
    c.execute("""
        SELECT 
            AVG(brightness) as avg_brightness,
            MIN(brightness) as min_brightness,
            MAX(brightness) as max_brightness,
            COUNT(*) as records_with_brightness
        FROM app_sessions 
        WHERE brightness IS NOT NULL
    """)
    row = c.fetchone()
    stats = {
        "avg_brightness": round(row[0], 1) if row[0] else "N/A",
        "min_brightness": row[1] if row[1] else "N/A",
        "max_brightness": row[2] if row[2] else "N/A",
        "records_count": row[3] if row[3] else 0
    }
    return jsonify(stats)

@app.route("/theme_stats", methods=["GET"])
def theme_stats():
    """Get theme usage statistics"""
    c.execute("""
        SELECT 
            theme_mode,
            COUNT(*) as count,
            SUM(duration_seconds) as total_seconds
        FROM app_sessions 
        WHERE theme_mode IS NOT NULL AND theme_mode != 'Unknown'
        GROUP BY theme_mode
        ORDER BY total_seconds DESC
    """)
    rows = c.fetchall()
    stats = [{
        "theme_mode": row[0],
        "session_count": row[1],
        "total_minutes": round(row[2] / 60, 1) if row[2] else 0
    } for row in rows]
    return jsonify(stats)

@app.route("/usage_by_hour", methods=["GET"])
def usage_by_hour():
    """Get app usage grouped by hour with brightness and theme data"""
    c.execute("""
        SELECT 
            substr(start_time, 12, 2) || ':00' as hour,
            app,
            SUM(duration_seconds) as total_seconds,
            AVG(brightness) as avg_brightness,
            GROUP_CONCAT(DISTINCT theme_mode) as themes
        FROM app_sessions 
        WHERE substr(start_time, 1, 10) = date('now')
        GROUP BY hour, app
        ORDER BY hour, total_seconds DESC
    """)
    rows = c.fetchall()
    data = [{
        "hour": row[0],
        "app": row[1],
        "total_minutes": round(row[2] / 60, 1),
        "avg_brightness": round(row[3], 1) if row[3] else "N/A",
        "themes": row[4] if row[4] else "Unknown"
    } for row in rows]
    return jsonify(data)

@app.route("/usage_by_date", methods=["GET"])
def usage_by_date():
    """Get app usage grouped by date with brightness and theme data"""
    c.execute("""
        SELECT 
            substr(start_time, 1, 10) as date,
            app,
            SUM(duration_seconds) as total_seconds,
            AVG(brightness) as avg_brightness,
            GROUP_CONCAT(DISTINCT theme_mode) as themes
        FROM app_sessions 
        GROUP BY date, app
        ORDER BY date, total_seconds DESC
        LIMIT 50
    """)
    rows = c.fetchall()
    data = [{
        "date": row[0],
        "app": row[1],
        "total_minutes": round(row[2] / 60, 1),
        "avg_brightness": round(row[3], 1) if row[3] else "N/A",
        "themes": row[4] if row[4] else "Unknown"
    } for row in rows]
    return jsonify(data)

if __name__ == "__main__":
    t = threading.Thread(target=log_active_app, daemon=True)
    t.start()
    app.run(port=5004)