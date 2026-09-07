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
        # TOTP CLEAN - space kadhne
        raw_secret = data.get('totp_secret','').replace(' ','').strip().upper()
        raw_secret = raw_secret.replace('\n','').replace('\r','')
        
        print(f"Trying login for: {data.get('client_id')}")
        
        obj = SmartConnect(api_key=data.get('api_key'))
        totp_code = pyotp.TOTP(raw_secret).now()
        print(f"TOTP Generated: {totp_code}")
        
        session = obj.generateSession(data.get('client_id'), data.get('password'), totp_code)
        return jsonify(session)
    except Exception as e:
        print(f"Login Error: {str(e)}")
        return jsonify({"status": False, "message": str(e)}), 500

@app.route('/holdings', methods=['POST', 'OPTIONS'])
def holdings():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        obj = SmartConnect(api_key=data.get('api_key'))
        obj.setAccessToken(data.get('jwtToken'))
        
        holdings_data = obj.holding()
        positions_data = obj.position()
        
        return jsonify({
            "holdings": holdings_data,
            "positions": positions_data
        })
    except Exception as e:
        print(f"Holdings Error: {str(e)}")
        return jsonify({"status": False, "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
