from flask import Flask, jsonify
from flask_cors import CORS
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel_client = None
# Order Block State
OB = {"first_high": 0, "first_low": 0, "fifty": 0, "ready": False, "traded": False, "status": "Waiting for 9:15 Candle"}
CE_history = [] # For 20 EMA

def get_client():
    global angel_client
    if angel_client: return angel_client
    from SmartApi import SmartConnect
    import pyotp
    obj = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET.strip()).now()
    obj.generateSession(CLIENT_ID, PASSWORD, totp)
    angel_client = obj
    return obj

def get_next_thursday():
    today = datetime.now()
    days_ahead = 3 - today.weekday() # Thursday is 3
    if days_ahead <= 0: days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%d%b%y").upper() # 14JAN26

def get_atm_token(obj, nifty_price, option_type="CE"):
    try:
        strike = round(nifty_price / 50) * 50
        expiry = get_next_thursday() # Weekly
        # Search NIFTY CE
        search = f"NIFTY {expiry} {strike} {option_type}"
        res = obj.searchScrip("NFO", search)
        if res['data']:
            return res['data'][0]['symbol'], res['data'][0]['symboltoken']
    except: pass
    return None, None

def get_ema(prices, period=20):
    if len(prices) < period: return 0
    ema = sum(prices[:period])/period
    k = 2/(period+1)
    for p in prices[period:]: ema = p*k + ema*(1-k)
    return ema

@app.route('/')
def home():
    return f"NIFTY Live: {fetch_logic()['price']} | OB: {OB['status']}"

@app.route('/get_ltp')
def get_ltp():
    data = fetch_logic()
    return jsonify(data)

def fetch_logic():
    global OB, CE_history
    obj = get_client()
    if not obj: return {"price": 0, "status": "Login Fail"}

    try:
        # 1. Nifty Price
        nifty_data = obj.ltpData("NSE", "NIFTY", "26000")
        nifty = float(nifty_data['data']['ltp'])

        # 2. ATM CE Price for EMA filter
        ce_symbol, ce_token = get_atm_token(obj, nifty, "CE")
        ce_price = 0
        if ce_token:
            ce_data = obj.ltpData("NFO", ce_symbol, ce_token)
            ce_price = float(ce_data['data']['ltp'])
            CE_history.append(ce_price)
            if len(CE_history) > 50: CE_history.pop(0)

        ema20 = get_ema(CE_history, 20)

        # 3. ORDER BLOCK LOGIC (Simplified for testing - 9:15 candle logic)
        now = datetime.now()
        # Demo: First price of day = First Candle
        if OB["first_high"] == 0:
            OB["first_high"] = nifty + 15
            OB["first_low"] = nifty - 15
            OB["fifty"] = (OB["first_high"] + OB["first_low"]) / 2
            OB["status"] = f"1st Candle H:{OB['first_high']} L:{OB['first_low']} 50%:{OB['fifty']}"

        # Check second candle breakout (nifty > first_high)
        if not OB["ready"] and nifty > OB["first_high"]:
            OB["ready"] = True
            OB["status"] = f"SETUP READY! Wait for 50% retest: {OB['fifty']}"

        # 4. ENTRY at 50%
        if OB["ready"] and not OB["traded"] and abs(nifty - OB["fifty"]) < 5:
            trend_up = ce_price > ema20 if ema20 > 0 else True

            if trend_up: # Call entry
                OB["status"] = f"BUY CALL {ce_symbol} @ {ce_price} EMA20:{ema20:.2f} SL:{OB['first_low']}"
                # AUTO ORDER
                try:
                    orderparams = {
                        "variety": "NORMAL", "tradingsymbol": ce_symbol,
                        "symboltoken": ce_token, "transactiontype": "BUY",
                        "exchange": "NFO", "ordertype": "MARKET",
                        "producttype": "INTRADAY", "duration": "DAY", "quantity": "75"
                    }
                    # obj.placeOrder(orderparams) # Pahila Paper Test kar, mag uncomment kar
                    OB["traded"] = True
                except Exception as e:
                    OB["status"] = f"Order Fail {e}"
            else:
                OB["status"] = "Downtrend - PUT setup (EMA below)"

        return {"price": nifty, "ce_price": ce_price, "ema20": ema20, "ob": OB, "status": OB["status"]}

    except Exception as e:
        return {"price": 0, "status": f"Error {e}", "ob": OB}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
