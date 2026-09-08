from flask import Flask, jsonify, request
import os, pyotp, time
from SmartApi import SmartConnect

app = Flask(__name__)

# CONFIG
LOT = 65
MAX_TRADES = 20
count_3min = 0
count_5min = 0

# Angel Creds from Render ENV
API_KEY = os.getenv("API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
PASSWORD = os.getenv("PASSWORD")
TOTP_SECRET = os.getenv("TOTP_SECRET")

def get_smart_api():
    try:
        if not all([API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET]):
            return None, "ENV Missing"
        totp = pyotp.TOTP(TOTP_SECRET).now()
        obj = SmartConnect(api_key=API_KEY)
        data = obj.generateSession(CLIENT_ID, PASSWORD, totp)
        return obj, "Connected"
    except Exception as e:
        return None, str(e)

@app.route('/')
def home():
    status = "ENV Missing - Render Environment madhe keys taka" if not API_KEY else "ENV OK"
    total = count_3min + count_5min
    return f"BOT LIVE | 3Min: {count_3min}/10 | 5Min: {count_5min}/10 | Total {total}/20 | Angel API: {status} | Logic: Option ATM 50% Retest + EMA20 | LOT: {LOT}"

@app.route('/check')
def check():
    return jsonify({"3min": count_3min, "5min": count_5min, "total": count_3min+count_5min, "lot": LOT, "max": MAX_TRADES, "env_status": "OK" if API_KEY else "Missing"})

@app.route('/buy_signal', methods=['POST'])
def buy_signal():
    global count_3min, count_5min
    data = request.json
    tf = data.get("timeframe", "3min") # 3min or 5min
    total = count_3min + count_5min
    if total >= MAX_TRADES:
        return jsonify({"status": "rejected", "reason": "20 trades done"})
    
    # EMA + 50% Retest logic will come from TradingView webhook
    # Here we place order
    smart, msg = get_smart_api()
    if not smart:
        return jsonify({"status": "error", "reason": msg})

    try:
        # Example: BUY NIFTY ATM CE - 65 Qty
        # orderparams = { "variety": "NORMAL", "tradingsymbol": "NIFTY...", "symboltoken": "99926000", "transactiontype": "BUY", "exchange": "NFO", "ordertype": "MARKET", "producttype": "INTRADAY", "duration": "DAY", "quantity": LOT }
        # orderId = smart.placeOrder(orderparams)
        if tf == "3min" and count_3min < 10:
            count_3min += 1
        elif tf == "5min" and count_5min < 10:
            count_5min += 1
        
        return jsonify({"status": "success", "3min": count_3min, "5min": count_5min, "total": count_3min+count_5min, "angel": msg})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})

@app.route('/reset')
def reset():
    global count_3min, count_5min
    count_3min = 0
    count_5min = 0
    return jsonify({"status": "reset done", "total": 0})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
