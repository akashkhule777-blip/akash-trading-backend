from flask import Flask, request, jsonify
from flask_cors import CORS
import pyotp
from SmartApi import SmartConnect
import os

app = Flask(__name__)
CORS(app, origins="*", allow_headers="*", methods="*")

@app.route('/')
def home():
    return "Akash Trading Backend LIVE Ahe!"

@app.route('/login', methods=['POST', 'OPTIONS'])
@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({"status": True}), 200
    try:
        data = request.json or {}
        api_key = os.getenv("API_KEY") or data.get('api_key')
        client_id = os.getenv("CLIENT_ID") or data.get('client_id')
        pwd = os.getenv("CLIENT_PWD") or data.get('password')
        totp_secret = os.getenv("TOTP_SECRET") or data.get('totp_secret')
        
        if not totp_secret:
            return jsonify({"status": False, "error": "TOTP_SECRET missing"}), 400

        totp = pyotp.TOTP(totp_secret).now()
        obj = SmartConnect(api_key=api_key)
        session = obj.generateSession(client_id, pwd, totp)
        
        if session.get('status'):
            return jsonify({"status": True, "message": "Connected!", "data": session})
        else:
            return jsonify({"status": False, "message": str(session)})
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
