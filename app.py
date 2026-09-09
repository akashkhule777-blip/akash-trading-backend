from flask import Flask, jsonify
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel = None
OB = {"h":0,"l":0,"fifty":0,"active":False}
POS = {"active":False, "buy_price":0, "symbol":"", "token":""}
QTY = "65" # Tujha Lot

def get_client():
    global angel
    if angel: return angel
    try:
        from SmartApi import SmartConnect
        import pyotp
        obj = SmartConnect(api_key=API_KEY)
        obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
        angel = obj
        return obj
    except Exception as e:
        print(f"LOGIN FAIL {e}")
        return None

def place_order(obj, symbol, token, ttype):
    params = {"variety":"NORMAL","tradingsymbol":symbol,"symboltoken":token,
              "transactiontype":ttype,"exchange":"NFO","ordertype":"MARKET",
              "producttype":"INTRADAY","duration":"DAY","quantity":QTY}
    return obj.placeOrder(params)

@app.route('/')
def home():
    try:
        obj = get_client()
        if not obj:
            return f"Angel Login Fail - Check ENV - ID:{CLIENT_ID}"

        # Nifty LTP
        try:
            nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except:
            nifty = 25500 # Market band asel tar dummy

        status = f"Backend OK | NIFTY:{nifty} | LOT:{QTY} | Time:{datetime.now().strftime('%H:%M:%S')}"

        # ATM Token - Market band asel tari crash nahi honar
        try:
            strike = round(nifty/50)*50
            # NIFTY Weekly - Token hardcode karu market band sathi
            search = obj.searchScrip("NFO", f"NIFTY {strike} CE")
            if search['data']:
                ce_sym = search['data'][0]['symbol']
                ce_tok = search['data'][0]['symboltoken']
                ce_ltp = float(obj.ltpData("NFO", ce_sym, ce_tok)['data']['ltp'])
                status += f" | ATM CE:{ce_sym} LTP:{ce_ltp}"
            else:
                status += f" | ATM Search No Data (Market Closed?) Strike:{strike}"
        except Exception as e:
            status += f" | Token Error (Market Closed): {e}"

        return status

    except Exception as e:
        return f"Error Caught: {e} | ID:{CLIENT_ID}"

@app.route('/get_ltp')
def get_ltp():
    try:
        obj = get_client()
        nifty = 0
        if obj:
            try:
                nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
            except:
                nifty = 25500

        return jsonify({"price": nifty, "qty": QTY, "status": "LIVE", "ob": OB, "pos": POS, "time": datetime.now().strftime("%H:%M:%S")})
    except Exception as e:
        return jsonify({"price": 0, "status": f"Error {e}", "qty": QTY})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
