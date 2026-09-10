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

OB3 = {"h":0,"l":0,"fifty":0,"active":False}
OB5 = {"h":0,"l":0,"fifty":0,"active":False}
TRADE3 = {"buy":0,"ltp":0,"pnl":0,"type":"WAIT 3MIN","sym":""}
TRADE5 = {"buy":0,"ltp":0,"pnl":0,"type":"WAIT 5MIN","sym":""}

def ist_now(): return datetime.now(IST)

def get_client():
    global angel
    try:
        from SmartApi import SmartConnect
        import pyotp
        if angel is None:
            obj = SmartConnect(api_key=API_KEY)
            obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
            angel = obj
        return angel
    except Exception as e:
        print(f"Login err {e}")
        angel = None
        return None

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

def get_first_candle(obj, interval):
    try:
        now = ist_now()
        frm = now.strftime("%Y-%m-%d 09:15")
        to = now.strftime("%Y-%m-%d %H:%M")
        data = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":interval,"fromdate":frm,"todate":to})
        if data and data.get('data') and len(data['data'])>=1:
            f = data['data'][0]
            h = float(f[2]); l = float(f[3])
            fifty = round((h+l)/2,2)
            active = False
            high1 = h
            if len(data['data'])>1:
                for c in data['data'][1:]:
                    if float(c[2]) > high1:
                        active=True; break
            return h,l,fifty,active
    except Exception as e:
        print(f"Candle {interval} err {e}")
    return 0,0,0,False

@app.route('/')
def home():
    obj = get_client()
    if not obj:
        return "<h2>Login Fail - Check ENV</h2>"

    now = ist_now()
    nifty = 23446.6
    try:
        nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass

    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

    # OB safe fetch - crash honar nahi
    h3,l3,f3,a3 = get_first_candle(obj, "THREE_MINUTE")
    if h3!=0:
        OB3.update({"h":h3,"l":l3,"fifty":f3,"active":a3})

    h5,l5,f5,a5 = get_first_candle(obj, "FIVE_MINUTE")
    if h5!=0:
        OB5.update({"h":h5,"l":l5,"fifty":f5,"active":a5})

    html = f"""
    <html><head><meta http-equiv="refresh" content="3">
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:8px;margin:4px;border-radius:6px;background:#111}}</style>
    </head><body>
    <h3 style="color:#0f0">AKASH LIVE - 3MIN + 5MIN | QTY {QTY} | WEEKLY 15-SEP-26 - FIXED</h3>
    <div class="box" style="border-color:yellow">NIFTY: <b style="font-size:20px">{nifty}</b> | STRIKE: {strike} | CE: {ce_sym} LTP <b style="font-size:20px;color:#0ff">{ce_ltp}</b> | PE LTP {pe_ltp} | Time {now.strftime('%H:%M:%S')} IST</div>
    <div style="display:flex;gap:5px">
        <div class="box" style="flex:1;border-color:#0ff">3 MIN OB (9:15-9:18)<br>H: {OB3['h']} L: {OB3['l']}<br>50%: {OB3['fifty']}<br>Active: {OB3['active']}</div>
        <div class="box" style="flex:1;border-color:#f0f">5 MIN OB (9:15-9:20)<br>H: {OB5['h']} L: {OB5['l']}<br>50%: {OB5['fifty']}<br>Active: {OB5['active']}</div>
    </div>
    <div style="display:flex;gap:5px">
        <div class="box" style="flex:1">TRADE 3MIN<br>{TRADE3['type']}<br>Sym: {ce_sym}<br>BUY {TRADE3['buy']} LTP {TRADE3['ltp']}<br><b>PNL {TRADE3['pnl']} | QTY {QTY}</b></div>
        <div class="box" style="flex:1">TRADE 5MIN<br>{TRADE5['type']}<br>Sym: {ce_sym}<br>BUY {TRADE5['buy']} LTP {TRADE5['ltp']}<br><b>PNL {TRADE5['pnl']} | QTY {QTY}</b></div>
    </div>
    <div class="box" style="border-color:#555;color:#aaa">Chart Left - NIFTY PE 94.90. Backend aata crash honar nahi. 09:11 cha atakla hota te fix zala. Hard Refresh kar - Ctrl+Shift+R</div>
    </body></html>
    """
    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
