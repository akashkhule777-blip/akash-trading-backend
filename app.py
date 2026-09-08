from flask import Flask, jsonify
import os
app = Flask(__name__)
count_3min = 0
count_5min = 0
@app.route('/')
def home():
    total = count_3min+count_5min
    env = "ENV OK" if os.getenv("API_KEY") else "ENV Missing - Environment madhe keys taka"
    return f"BOT LIVE | 3Min: {count_3min}/10 | 5Min: {count_5min}/10 | Total {total}/20 | {env} | LOT 65 | EMA20+50% Retest"
@app.route('/check')
def check():
    return jsonify({"3min":count_3min,"5min":count_5min,"total":count_3min+count_5min})
@app.route('/reset')
def reset():
    global count_3min,count_5min
    count_3min=0
    count_5min=0
    return "Reset Done 0/20"
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
