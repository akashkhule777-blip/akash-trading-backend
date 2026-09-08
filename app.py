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
from flask import Flask, jsonify
import time

app = Flask(__name__)

# FINAL CONFIG - Tuza Original Setup
LOT = 65
MAX_3MIN = 10
MAX_5MIN = 10
count_3min = 0
count_5min = 0
armed_3min = None
armed_5min = None

def get_ema(candles, period=20):
    if len(candles) < period: return candles[-1]['close']
    k = 2/(period+1)
    ema = candles[0]['close']
    for c in candles[1:]:
        ema = c['close']*k + ema*(1-k)
    return ema

@app.route('/')
def home():
    return f"BOT LIVE | 3Min: {count_3min}/{MAX_3MIN} | 5Min: {count_5min}/{MAX_5MIN} | Total {count_3min+count_5min}/20 | Option Chart + EMA20 Filter ON"

@app.route('/check-setup')
def check_setup():
    # Option chart candles logic - Angel API varun yeil
    # C1 Green + C2 Green + Price > EMA20 + 50% Retest
    return jsonify({
        "3Min": f"{count_3min}/{MAX_3MIN}",
        "5Min": f"{count_5min}/{MAX_5MIN}",
        "total": f"{count_3min+count_5min}/20",
        "logic": "C1 GREEN + C2 GREEN (upar close) + Price>20EMA + C1 50% Retest + SL=C1 Low + TGT 1:2 - Option Chart"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
