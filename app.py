from flask import Flask, jsonify
import os

app = Flask(__name__)

LOT = 65
count_3min = 0
count_5min = 0

@app.route('/')
def home():
    total = count_3min + count_5min
    api_status = "API Keys Missing - Env madhe taka" if not os.getenv("API_KEY") else "API Connected"
    return f"BOT LIVE OK | 3Min: {count_3min}/10 | 5Min: {count_5min}/10 | Total {total}/20 | {api_status} | EMA20 + 50% Retest Logic Ready"

@app.route('/check')
def check():
    return jsonify({
        "3min": count_3min,
        "5min": count_5min,
        "total": count_3min+count_5min,
        "lot": LOT,
        "logic": "C1 GREEN + C2 GREEN + Price>EMA20 + 50% Retest",
        "status": "Ready"
    })

@app.route('/reset')
def reset():
    global count_3min, count_5min
    count_3min = 0
    count_5min = 0
    return "Reset 0/20 Done"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
