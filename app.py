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
QTY = 65

# OB - Live NIFTY varun track karu
OB3 = {"h":0,"l":0,"fifty":0,"active":False,"start":"09:15","end":"09:18","locked":False}
OB5 = {"h":0,"l":0,"fifty":0,"active":False,"start":"09:15","end":"09:20","locked":False}

def ist_now(): return datetime.now(IST)

def get_client():
    global angel
    from SmartApi import SmartConnect
    import pyotp
    if angel is None:
        obj = SmartConnect(api_key=API_KEY)
        obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
        angel = obj
    return angel

def get_atm(obj, nifty, typ):
    strike = int(round(nifty/50)*50)
    try:
        res = obj.searchScrip("NFO", "NIFTY")
        for it in res.get('data',[]):
            sym = it.get('tradingsymbol','')
            if str(strike) in sym and typ in sym and "15" in sym and "SEP" in sym:
                tok = it['symboltoken']
                ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                return sym, tok, ltp, strike
    except: pass
    return f"NIFTY{strike}{typ}", "0", 0.0, strike

@app.route('/')
def home():
    obj = get_client()
    now = ist_now()
    cur_time_str = now.strftime("%H:%M:%S")
    cur_hm = now.strftime("%H:%M")
    
    nifty = 23415.95
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass

    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

    # 3MIN OB TRACK - 09:15 te 09:18 paryant NIFTY cha H/L ghe
    if "09:15" <= cur_hm <= "09:18":
        if OB3["h"]==0:
            OB3["h"]=nifty; OB3["l"]=nifty
        else:
            if nifty > OB3["h"]: OB3["h"]=nifty
            if nifty < OB3["l"]: OB3["l"]=nifty
    elif cur_hm > "09:18" and not OB3["locked"] and OB3["h"]!=0:
        OB3["fifty"]=round((OB3["h"]+OB3["l"])/2,2)
        OB3["locked"]=True

    # 5MIN OB TRACK - 09:15 te 09:20
    if "09:15" <= cur_hm <= "09:20":
        if OB5["h"]==0:
            OB5["h"]=nifty; OB5["l"]=nifty
        else:
            if nifty > OB5["h"]: OB5["h"]=nifty
            if nifty < OB5["l"]: OB5["l"]=nifty
    elif cur_hm > "09:20" and not OB5["locked"] and OB5["h"]!=0:
        OB5["fifty"]=round((OB5["h"]+OB5["l"])/2,2)
        OB5["locked"]=True

    # Break Check - 09:18 nantar High break zala ka?
    if OB3["locked"] and cur_hm > "09:18":
        if nifty > OB3["h"]:
            OB3["active"]=True

    if OB5["locked"] and cur_hm > "09:20":
        if nifty > OB5["h"]:
            OB5["active"]=True

    return f"""
    <html><head>
    <meta http-equiv="refresh" content="3">
    <script>setTimeout(()=>{{location.reload();}}, 3000);</script>
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:8px;margin:4px;border-radius:6px;background:#111}}</style>
    </head><body>
    <h3 style="color:#0f0">AKASH LIVE - AUTO 3SEC | NO CANDLE API - LIVE NIFTY TRACK | {cur_time_str}</h3>
    <div class="box" style="border-color:yellow">NIFTY: <b style="font-size:22px;color:#ff0">{nifty}</b> | STRIKE: {strike} | CE {ce_sym} LTP <b style="font-size:22px;color:#0ff">{ce_ltp}</b> | PE {pe_ltp}</div>
    <div style="display:flex;gap:5px">
        <div class="box" style="flex:1;border-color:#0ff"><b>3 MIN OB (09:15-09:18) LIVE TRACK</b><br>H: {round(OB3['h'],2)} L: {round(OB3['l'],2)}<br>50%: {OB3['fifty']}<br>Locked: {OB3['locked']} Active Break: {OB3['active']}</div>
        <div class="box" style="flex:1;border-color:#f0f"><b>5 MIN OB (09:15-09:20) LIVE TRACK</b><br>H: {round(OB5['h'],2)} L: {round(OB5['l'],2)}<br>50%: {OB5['fifty']}<br>Locked: {OB5['locked']} Active Break: {OB5['active']}</div>
    </div>
    <div class="box" style="border-color:#0f0">✓ Auto Refresh 3 Sec ON | ✓ Candle API nako - Direct NIFTY LTP varun OB | {cur_time_str} la update</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
