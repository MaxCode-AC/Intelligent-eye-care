from flask import Flask, request, jsonify
from flask_cors import CORS 
import cv2, numpy as np, screen_brightness_control as sbc

app = Flask(__name__)
CORS(app) 
def compute_screen_brightness(avg_pixel_brightness, theme_mode="Dark"):
    if avg_pixel_brightness < 25:
        return 0
    rounded = int(round(avg_pixel_brightness / 10.0) * 10)
    if avg_pixel_brightness < 100:
        return max(0, (rounded // 2) - (10 if theme_mode == "Dark" else 15))
    else:
        return (rounded // 2) if theme_mode == "Dark" else max(0, (rounded // 2) - 10)


@app.route("/")
def home():
    return jsonify({"status": "Flask server is running!", "port": 5001})


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/adjust_brightness", methods=["POST"])
def adjust_brightness():
    data = request.json
    theme_mode = data.get("theme_mode", "auto")  # Default to auto
    
    # Get ambient light level
    avg_pixel_brightness = 100  # Default
    try:
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                avg_pixel_brightness = float(np.mean(gray))
            cap.release()
    except Exception as e:
        print(f"Webcam error: {e}")
    
    # Auto-detect theme if requested
    if theme_mode == "auto":
        theme_mode = "Light" if avg_pixel_brightness > 127 else "Dark"
    
    # Calculate screen brightness
    screen_brightness = compute_screen_brightness(avg_pixel_brightness, theme_mode)
    
    # Apply brightness
    try:
        sbc.set_brightness(screen_brightness)
    except Exception as e:
        print(f"Brightness setting error: {e}")
    
    return jsonify({
        "avg_pixel_brightness": avg_pixel_brightness,
        "screen_brightness": screen_brightness,
        "theme_mode": theme_mode,
        "detected_theme": "Light" if avg_pixel_brightness > 127 else "Dark"
    })
if __name__ == "__main__":
    app.run(port=5001)
