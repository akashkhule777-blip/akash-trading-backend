from flask import Flask, request, jsonify
from flask_cors import CORS
import pyotp, os, requests
from SmartApi import SmartConnect

app = Flask(__name__)
CORS(app, origins="*", allow_headers="*", methods="*")

@app.route('/')
def home():
    return "Akash Trading Backend LIVE Ahe!"

@app.route('/ip')
def get_ip():
    try:
        ip = requests.get("https://api.ipify.org").text
        return f"Render cha IP: {ip} - Ha IP Angel One madhe taka!"
    except:
        return "IP nahi milala"

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
        
        totp = pyotp.TOTP(totp_secret).now()
        obj = SmartConnect(api_key=api_key)
        session = obj.generateSession(client_id, pwd, totp)
        return jsonify(session)
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
