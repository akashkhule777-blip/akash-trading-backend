from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>BOT LIVE LOT 65 🟢</h1><p>3Min 0/10 | 5Min 0/10 | Total 0/20 | Strategy ROJ</p>"

@app.route('/check')
def check():
    return {"status": "Live", "lot": 65}

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
