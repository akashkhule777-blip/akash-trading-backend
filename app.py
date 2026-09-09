from flask import Flask, jsonify
from flask_cors import CORS
import threading, time, json, urllib.request
from datetime import datetime
import pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
CORS(app)

# ========== ANGEL ONE CONFIG - ITHE TUJHA DATA TAK ==========
API_KEY = "TUJHI_API_KEY"
CLIENT_ID = "TUJHA_CLIENT_ID"
PASSWORD = "TUJHA_PASSWORD"
TOTP_SECRET = "TUJHA_TOTP_SECRET" # Google Authenticator cha secret
# ==========================================================

LTP_DATA = {"price": 0, "option_price": 0, "status": "Starting"}
obj = None

# Order Block Variables
CANDLE_3M = {"high": 0, "low": 0, "close": 0, "ready": False, "50": 0}
option_closes = [] # 20 EMA sathi

def get_ema(prices, period=20):
    if len(prices) < period: return 0
    ema = sum(prices[:period]) / period
    k = 2 / (period + 1)
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def angel_login():
    global obj
    try:
        obj = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = obj.generateSession(CLIENT_ID, PASSWORD, totp)
        print("Angel Login SUCCESS")
        return True
    except Exception as e:
        print(f"Login Fail: {e}")
        return False

def get_nifty_price():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m&range=1d"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
    except: return 0

def place_angel_order(symbol, token, side):
    try:
        orderparams = {
            "variety": "NORMAL",
            "tradingsymbol": symbol, # Eg: NIFTY09JAN25C23450
            "symboltoken": token,
            "transactiontype": side, # BUY / SELL
            "exchange": "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "quantity": "50" # 1 Lot
        }
        orderId = obj.placeOrder(orderparams)
        print(f"ORDER PLACED: {side} {symbol} ID: {orderId}")
        LTP_DATA["status"] = f"ORDER {side} {symbol}"
    except Exception as e:
        print(f"Order Fail: {e}")

def trading_loop():
    global CANDLE_3M
    angel_login()
    first_candle_done = False
    second_candle_high = 0

    while True:
        nifty = get_nifty_price()
        if nifty > 0:
            LTP_DATA["price"] = nifty

            # ----- YAHA TUJHA ATM OPTION PRICE FETCH KARAYCHA -----
            # Nifty 23470 asel tar ATM = 23450 CE
            # Ya sathi Angel cha LTP API vapraycha
            # Sadhya apan demo option price = nifty samajtoy
            option_price = nifty
            option_closes.append(option_price)
            if len(option_closes) > 50: option_closes.pop(0)
            ema20 = get_ema(option_closes, 20)

            # ----- ORDER BLOCK LOGIC (3 Min) -----
            now = datetime.now()
            # 9:15 - 9:18 pahila candle (Demo logic - tu candle aggregation add karu shaktos)
            if now.hour == 9 and now.minute >= 15 and now.minute < 18 and not first_candle_done:
                CANDLE_3M["high"] = max(CANDLE_3M["high"], nifty) if CANDLE_3M["high"] else nifty
                CANDLE_3M["low"] = min(CANDLE_3M["low"], nifty) if CANDLE_3M["low"] else nifty
                LTP_DATA["status"] = f"Forming 1st Candle H:{CANDLE_3M['high']} L:{CANDLE_3M['low']}"

            # 9:18 nantar 2nd candle check
            if now.hour == 9 and now.minute >= 18 and now.minute < 21 and not CANDLE_3M["ready"]:
                if nifty > CANDLE_3M["high"]: # 2nd candle 1st chya var close
                    CANDLE_3M["50"] = (CANDLE_3M["high"] + CANDLE_3M["low"]) / 2
                    CANDLE_3M["ready"] = True
                    LTP_DATA["status"] = f"SETUP READY! 50% Level: {CANDLE_3M['50']}"
                    print(f"SETUP READY 50%: {CANDLE_3M['50']}")

            # Entry Check - 50% retracement
            if CANDLE_3M["ready"] and ema20 > 0:
                if abs(nifty - CANDLE_3M["50"]) < 3: # 50% javal ala
                    if option_price > ema20: # Uptrend -> CALL
                        # ATM CALL Symbol kadhaycha
                        # place_angel_order("NIFTY...CE", "token", "BUY")
                        LTP_DATA["status"] = f"CALL ENTRY @ {nifty} SL {CANDLE_3M['low']} TARGET 1:2"
                        print("CALL ENTRY CONDITION MET!")
                        CANDLE_3M["ready"] = False # ekda entry zali ki parat setup nahi
                    else: # Downtrend -> PUT
                        LTP_DATA["status"] = f"PUT ENTRY @ {nifty}"
                        print("PUT ENTRY CONDITION MET!")
                        CANDLE_3M["ready"] = False

        time.sleep(2)

threading.Thread(target=trading_loop, daemon=True).start()

@app.route('/')
def home(): return f"Live {LTP_DATA}"

@app.route('/get_ltp')
def get_ltp(): return jsonify(LTP_DATA)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
