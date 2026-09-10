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

# AAJ SATHI MANUAL - jar 0 disla tar TradingView varun High Low tak
MANUAL_3M_H = 0 # udha. 23458
MANUAL_3M_L = 0 # udha. 23420
MANUAL_5M_H = 0
MANUAL_5M_L = 0

OB3 = {"h":0,"l":0,"fifty":0,"active":False,"locked":False}
OB5 = {"h":0,"l":0,"fifty":0,"active":False,"locked":False}

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

def get_ob_history(obj):
    global OB3, OB5
    try:
        now = ist_now()
        today = now.strftime("%Y-%m-%d")
        frm = f"{today} 09:15"
        to = f"{today} 09:30"
        print(f"Trying candle {frm} to {to}")
        data = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"ONE_MINUTE","fromdate":frm,"todate":to})
        print(f"Candle response: {data}")
        if data and data.get('data') and len(data['data'])>=5:
            candles = data['data']
            # 3MIN = first 3 candles
            c3 = candles[:3]
            h3 = max(float(c[2]) for c in c3)
            l3 = min(float(c[3]) for c in c3)
            # 5MIN = first 5 candles
            c5 = candles[:5]
            h5 = max(float(c[2]) for c in c5)
            l5 = min(float(c[3]) for c in c5)
            # Break check
            high3 = h3
            active3 = any(float(c[2])>high3 for c in candles[3:])
            high5 = h5
            active5 = any(float(c[2])>high5 for c in candles[5:])

            OB3.update({"h":h3,"l":l3,"fifty":round((h3+l3)/2,2),"active":active3,"locked":True})
            OB5.update({"h":h5,"l":l5,"fifty":round((h5+l5)/2,2),"active":active5,"locked":True})
            return True
    except Exception as e:
        print(f"History err {e}")
    return False

@app.route('/')
def home():
    obj = get_client()
    now = ist_now()
    cur_time_str = now.strftime("%H:%M:%S")
    cur_hm = now.strftime("%H:%M")

    nifty = 23432.35
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass

    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

    # MANUAL OVERRIDE
    if MANUAL_3M_H!=0:
        OB3.update({"h":MANUAL_3M_H,"l":MANUAL_3M_L,"fifty":round((MANUAL_3M_H+MANUAL_3M_L)/2,2),"locked":True})
    if MANUAL_5M_H!=0:
        OB5.update({"h":MANUAL_5M_H,"l":MANUAL_5M_L,"fifty":round((MANUAL_5M_H+MANUAL_5M_L)/2,2),"locked":True})

    # 1. Jar OB ajun 0 asel tar history try kar
    if OB3["h"]==0 or OB5["h"]==0:
        get_ob_history(obj)

    # 2. Jar ajun 09:15-09:20 madhe asel tar live track
    if "09:15" <= cur_hm <= "09:18" and OB3["h"]==0:
        OB3["h"]=nifty; OB3["l"]=nifty
    if "09:15" <= cur_hm <= "09:20" and OB5["h"]==0:
        OB5["h"]=nifty; OB5["l"]=nifty

    if "09:15" <= cur_hm <= "09:18":
        if OB3["h"]!=0:
            if nifty>OB3["h"]: OB3["h"]=nifty
            if nifty<OB3["l"]: OB3["l"]=nifty
    if "09:15" <= cur_hm <= "09:20":
        if OB5["h"]!=0:
            if nifty>OB5["h"]: OB5["h"]=nifty
            if nifty<OB5["l"]: OB5["l"]=nifty

    if cur_hm > "09:18" and OB3["h"]!=0 and not OB3["locked"]:
        OB3["fifty"]=round((OB3["h"]+OB3["l"])/2,2); OB3["locked"]=True
    if cur_hm > "09:20" and OB5["h"]!=0 and not OB5["locked"]:
        OB5["fifty"]=round((OB5["h"]+OB5["l"])/2,2); OB5["locked"]=True

    # Break
    if OB3["locked"] and nifty > OB3["h"]: OB3["active"]=True
    if OB5["locked"] and nifty > OB5["h"]: OB5["active"]=True

    return f"""
    <html><head>
    <meta http-equiv="refresh" content="3">
    <script>setTimeout(()=>{{location.reload();}}, 3000);</script>
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:8px;margin:4px;border-radius:6px;background:#111}}</style>
    </head><body>
    <h3 style="color:#0f0">AKASH LIVE - 3SEC AUTO | {cur_time_str} IST</h3>
    <div class="box" style="border-color:yellow">NIFTY: <b style="font-size:22px;color:#ff0">{nifty}</b> | STRIKE: {strike} | CE LTP <b style="font-size:22px;color:#0ff">{ce_ltp}</b> | PE {pe_ltp}</div>
    <div style="display:flex;gap:5px">
        <div class="box" style="flex:1;border-color:#0ff"><b>3 MIN OB (09:15-09:18)</b><br>H: {round(OB3['h'],2)} L: {round(OB3['l'],2)}<br>50%: {OB3['fifty']}<br>Locked: {OB3['locked']} Active: {OB3['active']}</div>
        <div class="box" style="flex:1;border-color:#f0f"><b>5 MIN OB (09:15-09:20)</b><br>H: {round(OB5['h'],2)} L: {round(OB5['l'],2)}<br>50%: {OB5['fifty']}<br>Locked: {OB5['locked']} Active: {OB5['active']}</div>
    </div>
    <div class="box">Auto Refresh 3 Sec ON | Render Logs madhe Candle response disel - jar 0 asel tar TradingView varun H/L sanga</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
