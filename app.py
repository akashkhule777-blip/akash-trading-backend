from flask import Flask, request, jsonify
from flask_cors import CORS
import pyotp
from SmartApi import SmartConnect
import requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/')
def home():
    return "Backend LIVE! Angel One Connected Ready!"

@app.route('/ip')
def get_ip():
    try:
        ip = requests.get('https://api.ipify.org').text
        return f"Render IP: {ip} | Ha IP Angel One madhe takla!"
    except:
        return "Backend LIVE!"

@app.route('/login', methods=['POST', 'OPTIONS'])
@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        obj = SmartConnect(api_key=data.get('api_key'))
        totp = pyotp.TOTP(data.get('totp_secret')).now()
        session = obj.generateSession(data.get('client_id'), data.get('password'), totp)
        return jsonify(session)
    except Exception as e:
        return jsonify({"status": False, "message": str(e)}), 500

@app.route('/holdings', methods=['POST', 'OPTIONS'])
def holdings():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        obj = SmartConnect(api_key=data.get('api_key'))
        obj.setAccessToken(data.get('jwtToken'))
        obj.setRefreshToken(data.get('refreshToken'))
        hold = obj.holding()
        pos = obj.position()
        return jsonify({"holdings": hold, "positions": pos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
