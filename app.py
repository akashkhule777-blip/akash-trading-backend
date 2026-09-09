from flask import Flask, jsonify
from flask_cors import CORS
import os
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel = None
QTY = "65"
IST = timezone(timedelta(hours=5, minutes=30))

# Order Block Storage
OB = {"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False}
POS = {"active":False,"buy_price":0,"symbol":"","token":"","sl":0,"tgt":0,"order_id":""}

def ist_now(): return datetime.now(IST)

def get_client():
    global angel
    if angel: return angel
    from SmartApi import SmartConnect
    import pyotp
    obj = SmartConnect(api_key=API_KEY)
    obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
    angel = obj
    return obj

def place_order(obj, sym, tok, side):
    params = {"variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":QTY}
    return obj.placeOrder(params)

def get_atm_ce(obj, nifty):
    try:
        strike = round(nifty/50)*50
        res = obj.searchScrip("NFO", f"NIFTY {strike} CE")
        sym = res['data'][0]['symbol']; tok = res['data'][0]['symboltoken']
        ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
        return sym, tok, ltp, strike
    except:
        return None, None, 0, 0

@app.route('/')
def home():
    try:
        obj = get_client()
        now = ist_now()
        nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp']) if obj else 23553.0
        ce_sym, ce_tok, ce_ltp, strike = get_atm_ce(obj, nifty)

        # --- ORDER BLOCK LOGIC ---
        # 1st Candle 9:15-9:18
        if now.hour==9 and now.minute>=15 and now.minute<18 and not OB["first_done"]:
            if OB["h"]==0: OB["h"]=nifty; OB["l"]=nifty
            else:
                OB["h"]=max(OB["h"], nifty)
                OB["l"]=min(OB["l"], nifty)
            OB["fifty"]=(OB["h"]+OB["l"])/2

        # 9:18 la 1st candle lock
        if now.hour==9 and now.minute>=18 and not OB["first_done"] and OB["h"]!=0:
            OB["first_done"]=True

        # 2nd Candle 9:18-9:21 check 1st high cha var close
        if OB["first_done"] and not OB["second_done"]:
            if now.hour==9 and now.minute>=18 and now.minute<21:
                if nifty > OB["h"]:
                    OB["active"]=True
            if now.hour==9 and now.minute>=21 and not OB["second_done"]:
                OB["second_done"]=True # 2nd candle time over

        # Testing sathi - market band asel tari setup active karu
        if OB["h"]==0 and now.hour>9:
            OB["h"]=nifty+15; OB["l"]=nifty-15; OB["fifty"]=nifty
            OB["active"]=True; OB["first_done"]=True; OB["second_done"]=True

        status_text = f"Waiting 50% {OB['fifty']:.1f}"
        # ENTRY at 50% Retest
        if OB["active"] and not POS["active"] and abs(nifty - OB["fifty"]) < 6 and OB["fifty"]!=0:
            try:
                oid = place_order(obj, ce_sym, ce_tok, "BUY")
                risk = OB["h"]-OB["l"]
                POS["active"]=True; POS["buy_price"]=ce_ltp; POS["symbol"]=ce_sym; POS["token"]=ce_tok
                POS["sl"]=ce_ltp - risk; POS["tgt"]=ce_ltp + (risk*2); POS["order_id"]=oid
                status_text = f"REAL BUY DONE {ce_sym} @ {ce_ltp} ID:{oid}"
            except Exception as e:
                status_text = f"BUY Fail {e}"

        # EXIT - SL / TGT
        if POS["active"] and ce_ltp>0:
            if ce_ltp <= POS["sl"] or ce_ltp >= POS["tgt"]:
                try:
                    oid = place_order(obj, POS["symbol"], POS["token"], "SELL")
                    reason = "TGT HIT" if ce_ltp>=POS["tgt"] else "SL HIT"
                    status_text = f"{reason} SELL DONE @ {ce_ltp} ID:{oid}"
                    POS["active"]=False; OB["active"]=False
                except Exception as e:
                    status_text = f"SELL Fail {e}"
            else:
                status_text = f"LIVE POS {POS['symbol']} BUY:{POS['buy_price']} LTP:{ce_ltp} SL:{POS['sl']:.1f} TGT:{POS['tgt']:.1f} P/L:{ce_ltp-POS['buy_price']:.1f}"

        return f"""
        <html><head><meta http-equiv="refresh" content="3">
        <style>body{{background:#000;color:#0f0;font-family:monospace;padding:15px;font-size:14px}} b{{color:#ff0}}</style>
        </head><body>
        ✅ Backend OK | IST:{now.strftime('%d-%m-%Y %H:%M:%S')} | NIFTY:{nifty} | LOT:{QTY}<br>
        ATM CE: {ce_sym} @ {ce_ltp} | Strike: {strike}<br><br>
        1st Candle: 9:15-9:18 IST | 50% Entry | SL: Low | TGT 1:2<br>
        OB: H={OB['h']:.1f} L={OB['l']:.1f} 50%={OB['fifty']:.1f} Active={OB['active']} FirstDone={OB['first_done']}<br>
        POS: {POS}<br><br>
        <b>Status: {status_text}</b><br><br>
        Auto Refresh: 3 sec ON | REAL TRADING ON
        </body></html>
        """
    except Exception as e:
        return f"<html><head><meta http-equiv='refresh' content='3'></head><body>Error {e}<br>IST {ist_now()}</body></html>"

@app.route('/get_ltp')
def ltp():
    try:
        obj = get_client()
        now = ist_now()
        nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp']) if obj else 0
        _, _, ce_ltp, _ = get_atm_ce(obj, nifty)
        return jsonify({"price":nifty,"ce":ce_ltp,"qty":QTY,"ist_time":now.strftime('%H:%M:%S %d-%m-%Y'),"ob":OB,"pos":POS})
    except Exception as e:
        return jsonify({"error":str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
