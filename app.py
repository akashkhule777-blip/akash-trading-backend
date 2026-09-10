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

OB3 = {"h":0,"l":0,"fifty":0,"active":False,"cnt":0}
OB5 = {"h":0,"l":0,"fifty":0,"active":False,"cnt":0}

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

def get_ob_via_1min(obj, mins):
    # 1min candle gheun 3min/5min cha OB banav
    try:
        now = ist_now()
        frm = now.strftime("%Y-%m-%d 09:15")
        to = now.strftime("%Y-%m-%d %H:%M")
        data = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"ONE_MINUTE","fromdate":frm,"todate":to})
        if data and data.get('data'):
            candles = data['data']
            if len(candles) >= mins:
                first_n = candles[:mins]
                h = max(float(c[2]) for c in first_n)
                l = min(float(c[3]) for c in first_n)
                fifty = round((h+l)/2,2)
                # Break check - nantarche candles high break kartat ka
                active = False
                if len(candles) > mins:
                    for c in candles[mins:]:
                        if float(c[2]) > h:
                            active=True
                            break
                return h,l,fifty,active,len(candles)
    except Exception as e:
        print(f"OB {mins}M err {e}")
    return 0,0,0,False,0

@app.route('/')
def home():
    obj = get_client()
    now = ist_now()
    nifty = 23426.95
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass

    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

    # NEW METHOD - 1MIN varun
    h3,l3,f3,a3,c3 = get_ob_via_1min(obj, 3)
    if h3!=0:
        OB3.update({"h":h3,"l":l3,"fifty":f3,"active":a3,"cnt":c3})

    h5,l5,f5,a5,c5 = get_ob_via_1min(obj, 5)
    if h5!=0:
        OB5.update({"h":h5,"l":l5,"fifty":f5,"active":a5,"cnt":c5})

    return f"""
    <html><head><meta http-equiv="refresh" content="3">
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:8px;margin:4px;border-radius:6px;background:#111}}</style>
    </head><body>
    <h3 style="color:#0f0">AKASH LIVE - 3MIN + 5MIN FIXED via 1MIN | QTY {QTY}</h3>
    <div class="box" style="border-color:yellow">NIFTY: <b style="font-size:20px">{nifty}</b> | STRIKE: {strike} | CE: {ce_sym} LTP <b style="color:#0ff;font-size:20px">{ce_ltp}</b> | PE {pe_ltp} | {now.strftime('%H:%M:%S')} | Candles: {c3}/{c5}</div>
    <div style="display:flex;gap:5px">
        <div class="box" style="flex:1;border-color:#0ff">3 MIN OB (9:15-9:18 via 1MIN)<br>H: {OB3['h']} L: {OB3['l']}<br>50%: {OB3['fifty']}<br>Active: {OB3['active']} Break | Cnt {OB3['cnt']}</div>
        <div class="box" style="flex:1;border-color:#f0f">5 MIN OB (9:15-9:20 via 1MIN)<br>H: {OB5['h']} L: {OB5['l']}<br>50%: {OB5['fifty']}<br>Active: {OB5['active']} Break | Cnt {OB5['cnt']}</div>
    </div>
    <div class="box">Left Chart: NIFTY 23400 PE 85.28. Market volatile ahe. Aata OB H/L 0 janar nahi. Deploy karun 1 min ne refresh kar.</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
