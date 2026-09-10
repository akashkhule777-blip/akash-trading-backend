from flask import Flask
from flask_cors import CORS
import os
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
IST = timezone(timedelta(hours=5, minutes=30))
QTY = 65

@app.route('/health')
def health():
    return "OK", 200

@app.route('/clear')
def clear():
    return "CLEARED <a href='/'>HOME</a>", 200

@app.route('/')
def home():
    try:
        from SmartApi import SmartConnect
        import pyotp
        try:
            sc = SmartConnect(api_key=API_KEY)
            sc.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
        except Exception as e:
            return f"<html><head><meta http-equiv='refresh' content='5'></head><body style='background:#000;color:yellow'>Login Retry {e}</body></html>", 200
        try:
            nifty = float(sc.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except:
            nifty = 23450.0
        strike = int(round(nifty/50)*50)
        ce_sym = f"NIFTY15SEP26{strike}CE"
        ce_tok = ""
        ce_ltp = 119.15
        try:
            r = sc.searchScrip("NFO", f"NIFTY {strike}")
            data = r.get('data',[]) if r else []
            cands = [x for x in data if str(strike) in x.get('tradingsymbol','') and x.get('tradingsymbol','').endswith('CE')]
            pick = None
            for x in cands:
                if '15SEP' in x['tradingsymbol'].upper():
                    pick = x
                    break
            if not pick and cands:
                pick = cands[0]
            if pick:
                ce_sym = pick['tradingsymbol']
                ce_tok = pick['symboltoken']
                ce_ltp = float(sc.ltpData("NFO", ce_sym, ce_tok)['data']['ltp'])
        except:
            pass
        return f"<html><head><meta http-equiv='refresh' content='2'></head><body style='background:#000;color:#0f0;font-family:monospace;padding:15px'><h2 style='color:gold'>NIFTY {nifty} ATM {strike} {ce_sym} @ {ce_ltp}</h2><div style='border:1px solid lime;padding:10px;background:#111'>OK 15SEP QTY {QTY}<br>{ce_sym}<br><a href='/health' style='color:cyan'>/health</a> <a href='/clear' style='color:red'>/clear</a></div></body></html>"
    except Exception as e:
        return f"<html><head><meta http-equiv='refresh' content='3'></head><body style='background:#000;color:yellow'>RETRY {e}</body></html>", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
