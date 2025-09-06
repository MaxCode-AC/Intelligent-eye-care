
# predict_stub.py
# Reads JSON from stdin: { avg_pixel_brightness, time_of_day, theme_mode }
# Returns JSON with predicted settings.

import sys, json

def compute_rule_based_brightness(avg, theme):
    # snap avg to nearest 10 for smoother behavior
    snapped = round(avg / 10) * 10

    if avg < 25:
        base = 0
    elif avg < 100:
        base = max(0, snapped / 2 - (10 if theme == "Dark" else 15))
    else:
        base = snapped / 2 - (0 if theme == "Dark" else 10)

    # clamp 0..100
    return int(max(0, min(100, base)))

def compute_blue_light(time_of_day):
    # rough heuristic until ML is plugged in
    return {
        "Morning": 10,
        "Afternoon": 5,
        "Evening": 40,
        "Night": 80
    }.get(time_of_day, 20)

def main():
    raw = sys.stdin.read().strip()
    try:
        payload = json.loads(raw) if raw else {}
    except Exception as e:
        print(json.dumps({"error": f"Invalid input JSON: {e}"}))
        return

    avg = int(payload.get("avg_pixel_brightness", 80))
    time_of_day = payload.get("time_of_day", "Evening")
    theme_mode = payload.get("theme_mode", "Dark")

    # You can replace below with your trained models later (joblib.load(...))
    # For now, rule-based predictions:
    predicted_brightness = compute_rule_based_brightness(avg, theme_mode)
    predicted_theme = theme_mode  # echo user's current toggle for demo
    predicted_blue_light = compute_blue_light(time_of_day)

    out = {
        "predicted_screen_brightness": predicted_brightness,
        "predicted_theme": predicted_theme,
        "predicted_blue_light": predicted_blue_light
    }
    print(json.dumps(out))

if __name__ == "__main__":
    main()
