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

angel = None
IST = timezone(timedelta(hours=5, minutes=30))

# Tujha Size - 1 Lot = 65 Qty
LOT = 1
QTY_PER_LOT = 65
TOTAL_QTY = 65

OB3 = {"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"tf":"3MIN"}
OB5 = {"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"tf":"5MIN"}
TRADE3 = {"active":False,"symbol":"","token":"","type":"WAIT 3MIN","buy":0,"ltp":0,"sl":0,"tgt":0,"pnl":0}
TRADE5 = {"active":False,"symbol":"","token":"","type":"WAIT 5MIN","buy":0,"ltp":0,"sl":0,"tgt":0,"pnl":0}

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

def get_atm_live(obj, nifty, opt_type):
    strike = int(round(nifty/50)*50)
    try:
        res = obj.searchScrip("NFO", "NIFTY")
        if res and res.get('data'):
            # STEP 1 - Weekly 15-SEP-26 expiry shodh
            for it in res['data']:
                sym = it.get('tradingsymbol','')
                # NIFTY15SEP26 23450 CE OR NIFTY 15Sep 23450CE
                if str(strike) in sym and opt_type in sym and "15" in sym and "SEP" in sym.upper():
                    tok = it['symboltoken']
                    try:
                        ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                        print(f"WEEKLY FOUND {sym} LTP {ltp}")
                        return sym, tok, ltp, strike
                    except: continue

            # STEP 2 - Jar 15SEP na sapadla tar konta pan javalcha strike ghe
            for it in res['data']:
                sym = it.get('tradingsymbol','')
                if str(strike) in sym and opt_type in sym:
                    tok = it['symboltoken']
                    try:
                        ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                        return sym, tok, ltp, strike
                    except: continue
    except Exception as e:
        print(f"ATM Error {e}")
    return f"NIFTY{strike}{opt_type}", "0", 0.0, strike

def get_ob_data(obj, interval, ob_dict):
    try:
        now = ist_now()
        frm = now.strftime("%Y-%m-%d 09:15")
        to = now.strftime("%Y-%m-%d %H:%M")
        candles = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":interval,"fromdate":frm,"todate":to})
        if candles and candles.get('data') and len(candles['data'])>0:
            first = candles['data'][0]
            ob_dict["h"]=float(first[2]); ob_dict["l"]=float(first[3])
            ob_dict["fifty"]=round((ob_dict["h"]+ob_dict["l"])/2,2)
            ob_dict["high1"]=ob_dict["h"]; ob_dict["first_done"]=True
            for c in candles['data'][1:]:
                if float(c[2]) > ob_dict["high1"]:
                    ob_dict["active"]=True
                    break
    except Exception as e:
        print(f"OB {interval} Error {e}")

@app.route('/')
def home():
    try:
        obj = get_client()
        now = ist_now()
        nifty = 23431.5
        try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: pass

        ce_sym, ce_tok, ce_ltp, strike = get_atm_live(obj, nifty, "CE")
        pe_sym, pe_tok, pe_ltp, _ = get_atm_live(obj, nifty, "PE")

        get_ob_data(obj, "THREE_MINUTE", OB3)
        get_ob_data(obj, "FIVE_MINUTE", OB5)

        # 3MIN Entry Logic
        if OB3["active"] and not TRADE3["active"]:
            if OB3["fifty"]-15 <= nifty <= OB3["fifty"]+15:
                TRADE3.update({"active":True,"symbol":ce_sym,"token":ce_tok,"type":"CE BUY 3MIN REAL","buy":ce_ltp,"ltp":ce_ltp,"sl":round(ce_ltp*0.7,2),"tgt":round(ce_ltp*1.5,2)})

        # 5MIN Entry Logic
        if OB5["active"] and not TRADE5["active"]:
            if OB5["fifty"]-15 <= nifty <= OB5["fifty"]+15:
                TRADE5.update({"active":True,"symbol":ce_sym,"token":ce_tok,"type":"CE BUY 5MIN REAL","buy":ce_ltp,"ltp":ce_ltp,"sl":round(ce_ltp*0.7,2),"tgt":round(ce_ltp*1.5,2)})

        if TRADE3["active"]:
            try: TRADE3["ltp"]=float(obj.ltpData("NFO", TRADE3["symbol"], TRADE3["token"])['data']['ltp'])
            except: pass
            TRADE3["pnl"]=round((TRADE3["ltp"]-TRADE3["buy"])*TOTAL_QTY,2)

        if TRADE5["active"]:
            try: TRADE5["ltp"]=float(obj.ltpData("NFO", TRADE5["symbol"], TRADE5["token"])['data']['ltp'])
            except: pass
            TRADE5["pnl"]=round((TRADE5["ltp"]-TRADE5["buy"])*TOTAL_QTY,2)

        html = f"""
        <html><head><meta http-equiv="refresh" content="5">
        <style>
            body{{background:#000;color:#fff;font-family:monospace;padding:8px;margin:0}}
           .box{{border:1px solid #0f0;padding:10px;margin:5px;border-radius:8px;background:#111}}
           .y{{border-color:#ff0;color:#ff0}}.c{{border-color:#0ff;color:#0ff}}.p{{border-color:#f0f;color:#f0f}}
           .grid{{display:flex;gap:6px;flex-wrap:wrap}}.big{{font-size:19px;font-weight:bold}}
        </style></head><body>
        <h3 style="color:#0f0;margin:4px">AKASH LIVE - 3MIN + 5MIN | LOT {LOT} = {TOTAL_QTY} QTY | WEEKLY 15-SEP-26</h3>
        <div class="box y">NIFTY: <b class="big">{nifty}</b> | STRIKE: {strike} | CE: {ce_sym} LTP <b class="big">{ce_ltp}</b> | PE LTP {pe_ltp} | Time {now.strftime('%H:%M:%S')}</div>
        <div class="grid">
            <div class="box c" style="flex:1"><b>3 MIN OB (9:15-9:18)</b><br>H: {OB3['h']} L: {OB3['l']}<br>50%: {OB3['fifty']}<br>Active: {OB3['active']} Break: {OB3['active']}</div>
            <div class="box p" style="flex:1"><b>5 MIN OB (9:15-9:20)</b><br>H: {OB5['h']} L: {OB5['l']}<br>50%: {OB5['fifty']}<br>Active: {OB5['active']} Break: {OB5['active']}</div>
        </div>
        <div class="grid">
            <div class="box" style="flex:1;border-color:#0f0"><b>TRADE 3MIN</b><br>{TRADE3['type']}<br>Sym: {TRADE3['symbol'] if TRADE3['symbol'] else ce_sym}<br>BUY {TRADE3['buy']} LTP {TRADE3['ltp']}<br>SL {TRADE3['sl']} TGT {TRADE3['tgt']}<br><b style="font-size:18px;color:#0f0">PNL {TRADE3['pnl']} Rs | QTY {TOTAL_QTY}</b></div>
            <div class="box" style="flex:1;border-color:#0ff"><b>TRADE 5MIN</b><br>{TRADE5['type']}<br>Sym: {TRADE5['symbol'] if TRADE5['symbol'] else ce_sym}<br>BUY {TRADE5['buy']} LTP {TRADE5['ltp']}<br>SL {TRADE5['sl']} TGT {TRADE5['tgt']}<br><b style="font-size:18px;color:#0ff">PNL {TRADE5['pnl']} Rs | QTY {TOTAL_QTY}</b></div>
        </div>
        <div class="box y">Angel LTP: 23450CE = 154.55 - Backend la pan hech disel. 3MIN 9:18 la ani 5MIN 9:20 la OB fix hoil. 1 Lot = 65 Qty</div>
        </body></html>
        """
        return html
    except Exception as e:
        return f"<h2 style='color:red'>Error: {e}</h2>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
