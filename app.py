
from flask import Flask, request, jsonify
from flask_cors import CORS
from SmartApi import SmartConnect
import pyotp, os

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "Akash Trading Backend LIVE"

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    try:
        api_key = data.get('api_key')
        client_id = data.get('client_id')
        password = data.get('password')
        totp_secret = data.get('totp')
        smartApi = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        session_data = smartApi.generateSession(client_id, password, totp)
        if session_data['status']:
            return jsonify({"status": True, "message": "Login Success", "data": session_data['data']})
        else:
            return jsonify({"status": False, "message": str(session_data['message'])})
    except Exception as e:
        return jsonify({"status": False, "message": str(e)})

@app.route('/portfolio', methods=['POST'])
def portfolio():
    data = request.json
    try:
        api_key = data.get('api_key')
        jwt = data.get('jwtToken')
        feed = data.get('feedToken')
        smartApi = SmartConnect(api_key=api_key)
        smartApi.setAccessToken(jwt)
        smartApi.setFeedToken(feed)
        holdings = smartApi.holding()
        positions = smartApi.position()
        return jsonify({"status": True, "holdings": holdings, "positions": positions})
    except Exception as e:
        return jsonify({"status": False, "message": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
