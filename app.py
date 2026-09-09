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

LOT = 1
QTY_PER_LOT = 65
TOTAL_QTY = 65

OB3 = {"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"tf":"3MIN"}
OB5 = {"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"tf":"5MIN"}
TRADE3 = {"active":False,"symbol":"","type":"WAIT 3MIN","buy":0,"ltp":0,"sl":0,"tgt":0,"pnl":0}
TRADE5 = {"active":False,"symbol":"","type":"WAIT 5MIN","buy":0,"ltp":0,"sl":0,"tgt":0,"pnl":0}

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
            for it in res['data']:
                sym = it.get('tradingsymbol','')
                if str(strike) in sym and opt_type in sym and "NIFTY" in sym:
                    tok = it['symboltoken']
                    ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                    return sym, tok, ltp, strike
    except: pass
    return f"NIFTY{strike}{opt_type}", "0", 0.0, strike

def get_ob_data(obj, interval, ob_dict):
    try:
        now = ist_now()
        frm = now.strftime("%Y-%m-%d 09:15")
        to = now.strftime("%Y-%m-%d %H:%M")
        candles = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":interval,"fromdate":frm,"todate":to})
        if candles and candles.get('data'):
            first = candles['data'][0]
            ob_dict["h"]=float(first[2]); ob_dict["l"]=float(first[3])
            ob_dict["fifty"]=round((ob_dict["h"]+ob_dict["l"])/2,2)
            ob_dict["high1"]=ob_dict["h"]; ob_dict["first_done"]=True
            for c in candles['data'][1:]:
                if float(c[2]) > ob_dict["high1"]:
                    ob_dict["active"]=True
                    break
    except: pass

@app.route('/')
def home():
    obj = get_client()
    now = ist_now()
    nifty = 23457.0
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass

    ce_sym, ce_tok, ce_ltp, strike = get_atm_live(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm_live(obj, nifty, "PE")

    get_ob_data(obj, "THREE_MINUTE", OB3)
    get_ob_data(obj, "FIVE_MINUTE", OB5)

    # 3MIN Entry
    if OB3["active"] and not TRADE3["active"]:
        if OB3["fifty"]-10 <= nifty <= OB3["fifty"]+10:
            TRADE3.update({"active":True,"symbol":ce_sym,"type":"CE BUY 3MIN REAL","buy":ce_ltp,"ltp":ce_ltp,"sl":round(ce_ltp*0.7,2),"tgt":round(ce_ltp*1.5,2)})

    # 5MIN Entry
    if OB5["active"] and not TRADE5["active"]:
        if OB5["fifty"]-10 <= nifty <= OB5["fifty"]+10:
            TRADE5.update({"active":True,"symbol":ce_sym,"type":"CE BUY 5MIN REAL","buy":ce_ltp,"ltp":ce_ltp,"sl":round(ce_ltp*0.7,2),"tgt":round(ce_ltp*1.5,2)})

    if TRADE3["active"]:
        try: TRADE3["ltp"]=float(obj.ltpData("NFO", TRADE3["symbol"], ce_tok)['data']['ltp'])
        except: pass
        TRADE3["pnl"]=round((TRADE3["ltp"]-TRADE3["buy"])*TOTAL_QTY,2)

    if TRADE5["active"]:
        try: TRADE5["ltp"]=float(obj.ltpData("NFO", TRADE5["symbol"], ce_tok)['data']['ltp'])
        except: pass
        TRADE5["pnl"]=round((TRADE5["ltp"]-TRADE5["buy"])*TOTAL_QTY,2)

    html = f"""
    <html><head><meta http-equiv="refresh" content="6">
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:10px;margin:5px;border-radius:8px;background:#111}}.y{{border-color:#ff0;color:#ff0}}.grid{{display:flex;gap:6px;flex-wrap:wrap}}</style></head><body>
    <h3 style="color:#0f0">AKASH LIVE - 3MIN + 5MIN SETUP | LOT {LOT} = {TOTAL_QTY} QTY</h3>
    <div class="box y">NIFTY: {nifty} | STRIKE: {strike} | CE {ce_sym} LTP {ce_ltp} | PE LTP {pe_ltp} | Time {now.strftime('%H:%M:%S')}</div>
    <div class="grid">
        <div class="box" style="flex:1;border-color:#0ff;color:#0ff"><b>3 MIN OB</b><br>H: {OB3['h']} L: {OB3['l']}<br>50%: {OB3['fifty']}<br>Active: {OB3['active']} HighBreak: {OB3['active']}</div>
        <div class="box" style="flex:1;border-color:#f0f;color:#f0f"><b>5 MIN OB</b><br>H: {OB5['h']} L: {OB5['l']}<br>50%: {OB5['fifty']}<br>Active: {OB5['active']} HighBreak: {OB5['active']}</div>
    </div>
    <div class="grid">
        <div class="box" style="flex:1"><b>TRADE 3MIN</b><br>{TRADE3['type']}<br>BUY {TRADE3['buy']} LTP {TRADE3['ltp']}<br>SL {TRADE3['sl']} TGT {TRADE3['tgt']}<br><b>PNL {TRADE3['pnl']} Rs | QTY {TOTAL_QTY}</b></div>
        <div class="box" style="flex:1"><b>TRADE 5MIN</b><br>{TRADE5['type']}<br>BUY {TRADE5['buy']} LTP {TRADE5['ltp']}<br>SL {TRADE5['sl']} TGT {TRADE5['tgt']}<br><b>PNL {TRADE5['pnl']} Rs | QTY {TOTAL_QTY}</b></div>
    </div>
    <div class="box y">Setup: 3MIN candle 9:15-9:18 | 5MIN candle 9:15-9:20 | Donhi la same logic - High Break -> 50% Retest -> 65 Qty CE BUY | Donhi timeframe independent entry denar</div>
    </body></html>
    """
    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
