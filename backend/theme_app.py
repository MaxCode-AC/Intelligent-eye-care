from flask import Flask, request, jsonify
import datetime, json, os, re
from flask_cors import CORS
import platform
import subprocess
import sys
import screen_brightness_control as sbc

app = Flask(__name__)
CORS(app)  

# Default settings
current_theme = "Dark"
blue_light_level = 20
schedule_active = False
schedule_settings = {"start": "06:00", "end": "16:00", "theme": "Light"}
PREF_FILE = "user_prefs.json"

def apply_theme_system_changes(theme, blue_light):
    """Apply actual system changes for theme and blue light filter"""
    print(f"Applying system changes: Theme={theme}, Blue Light={blue_light}%")
    
    try:
        # 1. Apply blue light filter (adjust screen temperature)
        apply_blue_light_filter(blue_light)
        
        # 2. Apply theme (dark/light mode) - this is OS specific
        apply_system_theme(theme)
        
        return True
    except Exception as e:
        print(f"Error applying system changes: {e}")
        return False

def apply_blue_light_filter(level):
    """Apply blue light filter by adjusting screen color temperature"""
    try:
        # Convert blue light level (0-100) to temperature adjustment
        # Higher level = more filtering = warmer color
        warmth_intensity = level  # 0-100%
        
        # For Windows: Use PowerShell commands to adjust color temperature
        if platform.system() == "Windows":
            adjust_windows_color_temperature(warmth_intensity)
            
        # For macOS: Use night shift equivalent
        elif platform.system() == "Darwin":
            adjust_macos_night_shift(warmth_intensity)
            
        # For Linux: Use redshift
        elif platform.system() == "Linux":
            adjust_linux_redshift(warmth_intensity)
            
        print(f"Blue light filter applied: {level}%")
        return True
        
    except Exception as e:
        print(f"Blue light filter error: {e}")
        return False

def adjust_windows_color_temperature(warmth):
    """Adjust color temperature on Windows"""
    try:
        # Adjust brightness as a proxy for color temperature (warmer = slightly dimmer)
        current_brightness = sbc.get_brightness()[0]
        adjusted_brightness = max(10, current_brightness - (warmth / 10))
        sbc.set_brightness(int(adjusted_brightness))
        
    except Exception as e:
        print(f"Windows color adjustment error: {e}")

def adjust_macos_night_shift(intensity):
    """Adjust night shift on macOS"""
    try:
        # Use osascript to control night shift
        strength = intensity / 100.0
        subprocess.run([
            'osascript', '-e',
            f'tell application "System Events" to tell appearance preferences to set night shift intensity to {strength}'
        ], timeout=10, capture_output=True)
    except Exception as e:
        print(f"macOS night shift error: {e}")

def adjust_linux_redshift(warmth):
    """Adjust redshift on Linux"""
    try:
        # Calculate temperature (6500K = neutral, 3500K = very warm)
        temperature = 6500 - (warmth * 30)
        subprocess.run(['redshift', '-O', str(int(temperature))], timeout=10, capture_output=True)
    except Exception as e:
        print(f"Linux redshift error: {e}")

def apply_system_theme(theme):
    """Apply system-wide dark/light theme"""
    try:
        if platform.system() == "Windows":
            # Windows dark mode registry setting
            value = 0 if theme == "Dark" else 1
            subprocess.run([
                'reg', 'add', 
                'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize',
                '/v', 'AppsUseLightTheme', '/t', 'REG_DWORD', '/d', str(value), '/f'
            ], timeout=10, capture_output=True)
            
        elif platform.system() == "Darwin":
            # macOS dark mode
            dark_mode = "true" if theme == "Dark" else "false"
            subprocess.run([
                'osascript', '-e',
                f'tell application "System Events" to tell appearance preferences to set dark mode to {dark_mode}'
            ], timeout=10, capture_output=True)
            
        elif platform.system() == "Linux":
            # Linux - varies by DE, this is for GNOME
            schema = "org.gnome.desktop.interface"
            key = "gtk-theme"
            theme_name = "Adwaita-dark" if theme == "Dark" else "Adwaita"
            subprocess.run(['gsettings', 'set', schema, key, theme_name], timeout=10, capture_output=True)
            
        print(f"System theme applied: {theme}")
        return True
        
    except Exception as e:
        print(f"Theme application error: {e}")
        return False

def save_preference(theme, blue_light=None):
    """Save theme preference with timestamp"""
    data = []
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE, "r") as f:
                data = json.load(f)
        except:
            data = []
    
    entry = {
        "theme": theme, 
        "timestamp": str(datetime.datetime.now())
    }
    if blue_light is not None:
        entry["blue_light"] = blue_light
        
    data.append(entry)
    
    with open(PREF_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.route("/set_manual_theme", methods=["POST"])
def set_manual_theme():
    """Set theme manually and apply system changes"""
    global current_theme, blue_light_level
    try:
        data = request.get_json()
        theme = data.get("theme", "Dark")
        blue_light = data.get("blue_light", blue_light_level)
        
        if theme in ["Light", "Dark"] and 0 <= blue_light <= 100:
            current_theme = theme
            blue_light_level = blue_light
            
            # Apply system changes
            success = apply_theme_system_changes(current_theme, blue_light_level)
            save_preference(current_theme, blue_light_level)
            
            return jsonify({
                "mode": "manual", 
                "theme": current_theme,
                "blue_light": blue_light_level,
                "applied": success
            })
        return jsonify({"error": "Invalid parameters"}), 400
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/set_blue_light", methods=["POST"])
def set_blue_light():
    """Set blue light filter level"""
    global blue_light_level
    try:
        data = request.get_json()
        blue_light = data.get("blue_light", 20)
        
        if 0 <= blue_light <= 100:
            blue_light_level = blue_light
            success = apply_blue_light_filter(blue_light_level)
            save_preference(current_theme, blue_light_level)
            
            return jsonify({
                "blue_light": blue_light_level,
                "theme": current_theme,
                "applied": success
            })
        return jsonify({"error": "Blue light level must be 0-100"}), 400
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/set_schedule", methods=["POST"])
def set_schedule():
    """Set and activate schedule"""
    global schedule_active, schedule_settings
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        schedule_settings = {
            "start": data.get("start", "06:00"),
            "end": data.get("end", "16:00"), 
            "theme": data.get("theme", "Light")
        }
        schedule_active = True
        
        # Validate time format
        try:
            datetime.datetime.strptime(schedule_settings["start"], "%H:%M")
            datetime.datetime.strptime(schedule_settings["end"], "%H:%M")
        except ValueError:
            return jsonify({"error": "Invalid time format. Use HH:MM"}), 400
        
        # Apply schedule immediately
        success = check_and_apply_schedule()
        
        return jsonify({
            "status": "schedule_set", 
            "schedule": schedule_settings,
            "applied": success
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/disable_schedule", methods=["POST"])
def disable_schedule():
    """Disable schedule mode"""
    global schedule_active
    try:
        schedule_active = False
        return jsonify({"status": "schedule_disabled"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def check_and_apply_schedule():
    """Check current time against schedule and apply theme if needed"""
    global current_theme  
    
    if not schedule_active:
        return False
    
    try:
        now = datetime.datetime.now()
        current_time = now.time()
        
        start_time = datetime.datetime.strptime(schedule_settings["start"], "%H:%M").time()
        end_time = datetime.datetime.strptime(schedule_settings["end"], "%H:%M").time()
        
        if start_time <= current_time <= end_time:
            new_theme = schedule_settings["theme"]
        else:
            new_theme = "Dark" if schedule_settings["theme"] == "Light" else "Light"
        
        
        if new_theme != current_theme:
            current_theme = new_theme
            success = apply_theme_system_changes(current_theme, blue_light_level)
            save_preference(current_theme, blue_light_level)
            return success
        else:
            return True  
            
    except Exception as e:
        print(f"Schedule check error: {e}")
        return False

@app.route("/scheduled_theme", methods=["GET"])
def scheduled_theme():
    """Check and apply scheduled theme"""
    try:
        success = check_and_apply_schedule()
        
        return jsonify({
            "mode": "schedule" if schedule_active else "manual",
            "theme": current_theme,
            "hour": datetime.datetime.now().hour,
            "schedule_active": schedule_active,
            "schedule": schedule_settings,
            "applied": success
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_schedule_status", methods=["GET"])
def get_schedule_status():
    """Get current schedule status and settings."""
    try:
        return jsonify({
            "schedule_active": schedule_active,
            "schedule_settings": schedule_settings,
            "current_theme": current_theme,
            "blue_light_level": blue_light_level
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_theme_history", methods=["GET"])
def get_theme_history():
    """Return all past theme choices with timestamps."""
    try:
        if os.path.exists(PREF_FILE):
            with open(PREF_FILE, "r") as f:
                try:
                    data = json.load(f)
                    return jsonify({"history": data})
                except:
                    return jsonify({"error": "Failed to read preferences"}), 500
        return jsonify({"history": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_current_theme", methods=["GET"])
def get_current_theme():
    """Get the current active theme."""
    try:
        return jsonify({
            "theme": current_theme,
            "blue_light": blue_light_level,
            "schedule_active": schedule_active,
            "mode": "schedule" if schedule_active else "manual"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    """Home endpoint to check if server is running."""
    return jsonify({
        "status": "Theme server is running",
        "port": 5002,
        "endpoints": {
            "/set_manual_theme": "POST - Set manual theme",
            "/set_blue_light": "POST - Set blue light filter",
            "/set_schedule": "POST - Set schedule",
            "/disable_schedule": "POST - Disable schedule",
            "/scheduled_theme": "GET - Get scheduled theme",
            "/get_schedule_status": "GET - Get schedule status",
            "/get_theme_history": "GET - Get theme history",
            "/get_current_theme": "GET - Get current theme"
        }
    })

if __name__ == "__main__":
    app.run(port=5002, debug=True)