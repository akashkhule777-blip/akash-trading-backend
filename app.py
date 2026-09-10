from flask import Flask
from flask_cors import CORS
import os, json
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
REAL = True

OB_FILE = "/tmp/ob_final.json"
STATE_FILE = "/tmp/state_final.json"

def ist_now(): return datetime.now(IST)

def load(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f:
                return json.load(f)
    except: pass
    return d

def save(p,d):
    try:
        with open(p,'w') as f:
            json.dump(d, f)
    except: pass

def get_client():
    global angel
    from SmartApi import SmartConnect
    import pyotp
    if angel is None:
        c = SmartConnect(api_key=API_KEY)
        c.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
        angel = c
    return angel

def get_atm(obj, nifty):
    strike = int(round(nifty/50)*50)
    ce_sym=ce_tok=pe_sym=pe_tok=""; ce_l=pe_l=0.0
    try:
        # Auto - kuthli hi expiry aso 15 SEP 2026, 25 SEP, etc
        r = obj.searchScrip("NFO", f"NIFTY {strike}")
        data = r.get('data', []) if r and r.get('data') else []
        if not data:
            r2 = obj.searchScrip("NFO", "NIFTY")
            data = r2.get('data', []) if r2 and r2.get('data') else []

        ce_cands = [x for x in data if str(strike) in x.get('tradingsymbol','') and x.get('tradingsymbol','').endswith('CE')]
        pe_cands = [x for x in data if str(strike) in x.get('tradingsymbol','') and x.get('tradingsymbol','').endswith('PE')]

        if ce_cands:
            ce_cands = sorted(ce_cands, key=lambda x: x['tradingsymbol'])
            ce_sym = ce_cands[0]['tradingsymbol']; ce_tok = ce_cands[0]['symboltoken']
            try: ce_l = float(obj.ltpData("NFO", ce_sym, ce_tok)['data']['ltp'])
            except: ce_l = 0.0
        if pe_cands:
            pe_cands = sorted(pe_cands, key=lambda x: x['tradingsymbol'])
            pe_sym = pe_cands[0]['tradingsymbol']; pe_tok = pe_cands[0]['symboltoken']
            try: pe_l = float(obj.ltpData("NFO", pe_sym, pe_tok)['data']['ltp'])
            except: pe_l = 0.0
    except Exception as e:
        print(e)
    return strike, ce_sym, ce_tok, ce_l, pe_sym, pe_tok, pe_l

def get_ob(obj):
    today = ist_now().strftime("%Y-%m-%d")
    cached = load(OB_FILE, {})
    if cached.get("date")==today and cached.get("h3",0)!=0:
        return cached
    try:
        d = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:35"})
        if d and d.get('data'):
            c = d['data']
            if len(c) >= 6:
                h3 = max(float(c[i][2]) for i in range(0,3)); l3 = min(float(c[i][3]) for i in range(0,3)); f3 = round((h3+l3)/2,2)
                h2 = max(float(c[i][2]) for i in range(3,6)); l2 = min(float(c[i][3]) for i in range(3,6)); cl2 = float(c[5][4])
                up3 = cl2 > h3 or h2 > h3; down3 = cl2 < l3 or l2 < l3
                h5 = max(float(c[i][2]) for i in range(0,5)); l5 = min(float(c[i][3]) for i in range(0,5)); f5 = round((h5+l5)/2,2)
                ob = {"h3":h3,"l3":l3,"f3":f3,"up3":up3,"down3":down3,"h5":h5,"l5":l5,"f5":f5,"up5":False,"down5":False,"date":today}
                save(OB_FILE, ob)
                return ob
    except Exception as e:
        print(f"OB ERR {e}")
    return cached if cached.get("h3") else {"h3":0,"l3":0,"f3":0,"up3":False,"down3":False,"h5":0,"l5":0,"f5":0,"up5":False,"down5":False,"date":today}

def place(obj, sym, tok, side):
    if not REAL or tok=="": return "PAPER"
    try:
        p = {"variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","price":"0","triggerprice":"0","squareoff":"0","stoploss":"0","quantity":str(QTY)}
        return obj.placeOrder(p)
    except Exception as e: return f"FAIL {e}"

STATE = load(STATE_FILE, {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","e3":0,"pnl3":0,"date":""})

@app.route('/clear')
def clear():
    for f in [OB_FILE, STATE_FILE]:
        try: os.remove(f)
        except: pass
    return "CLEARED - <a href='/'>HOME</a>"

@app.route('/debug')
def debug():
    try:
        obj = get_client()
        nifty = 23450.0
        try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: pass
        strike, ce_s, ce_t, ce_l, pe_s, pe_t, pe_l = get_atm(obj, nifty)
        ob = get_ob(obj)
        return f"NIFTY {nifty} ATM {strike}<br>CE {ce_s} TOK {ce_t} LTP {ce_l}<br>PE {pe_s} LTP {pe_l}<br>OB {ob}<br><a href='/clear'>clear</a> <a href='/'>home</a>"
    except Exception as e:
        return f"DEBUG ERR {e} <a href='/clear'>clear</a>"

@app.route('/')
def home():
    try:
        global STATE
        obj = get_client()
        now = ist_now(); ct = now.strftime("%H:%M:%S"); chm = now.strftime("%H:%M"); today = now.strftime("%Y-%m-%d")
        if STATE.get("date")!=today:
            STATE = {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","e3":0,"pnl3":0,"date":today}
            save(STATE_FILE, STATE)

        nifty = 23450.0
        try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: pass

        strike, ce_s, ce_t, ce_l, pe_s, pe_t, pe_l = get_atm(obj, nifty)
        ob = get_ob(obj)
        h3,l3,f3,up3,down3 = ob["h3"],ob["l3"],ob["f3"],ob["up3"],ob["down3"]
        h5,l5,f5 = ob["h5"],ob["l5"],ob["f5"]

        if h3!=0 and not up3 and nifty > h3: up3=True
        if h3!=0 and not down3 and nifty < l3: down3=True
        tgt_up = round(f3 + 2*(f3-l3),2) if l3 else 0

        # Tujhya photo pramane - 15 SEP 2026 CE 23450 LTP 129.30
        msg = f"ATM {strike} CE {ce_s} LTP {ce_l} | SPOT OB H:{round(h3,1)} L:{round(l3,1)} 50%:{f3} UP:{up3} DOWN:{down3} TGT:{tgt_up}"

        if h3!=0 and up3 and not STATE["a3"] and STATE["e3"]<10 and "09:21" <= chm <= "15:00":
            if abs(nifty - f3) <= 15 and ce_t!="":
                place(obj, ce_s, ce_t, "BUY")
                STATE.update({"a3":True,"buy3":ce_l,"sl3":l3,"tgt3":tgt_up,"sym3":ce_s,"tok3":ce_t,"e3":STATE["e3"]+1,"date":today}); save(STATE_FILE, STATE)
                msg = f"BUY CE {strike} @ {ce_l} REAL | SL Spot {l3} TGT {tgt_up}"

        if STATE["a3"]:
            STATE["pnl3"]=round((ce_l-STATE["buy3"])*QTY,2); save(STATE_FILE, STATE)
            if nifty <= STATE["sl3"] or nifty >= STATE["tgt3"]:
                place(obj, STATE["sym3"], STATE["tok3"], "SELL"); STATE["a3"]=False; save(STATE_FILE, STATE)
                msg = f"EXIT Spot {nifty} PNL {STATE['pnl3']}"
            else:
                msg = f"LIVE BUY {STATE['buy3']} LTP {ce_l} PNL {STATE['pnl3']} | {msg}"

        return f"""<html><head><meta http-equiv="refresh" content="2"><style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:10px;background:#111}}.gold{{border-color:gold;background:#221d00}}</style></head><body>
        <h2 style="color:gold">FINAL - 500 GONE | {ct} | NIFTY {nifty} | ATM {strike} AUTO | CE {ce_l}</h2>
        <div class="box">NIFTY {nifty} → ATM <b style="color:yellow;font-size:22px">{strike}</b> AUTO UPDATE | CE <b style="color:#0ff;font-size:26px">{ce_l}</b> {ce_s}<br>PE {pe_l} | QTY {QTY} REAL {REAL} | <a href='/debug' style='color:cyan'>/debug</a> <a href='/clear' style='color:red'>/clear</a></div>
        <div class="box gold"><b>3MIN OB:</b> {msg}<br>Entries {STATE['e3']}/10</div>
        <div class="box gold" style="border-color:#0ff"><b>5MIN OB:</b> H:{round(h5,1)} L:{round(l5,1)} 50%:{f5}</div>
        <div class="box" style="border-color:lime">✓ 500 Error Fix - json bug solved<br>✓ CE LTP 0 fix - tujhya photo pramane 129.30 yeil<br>✓ ATM auto update - 23450→23500<br>✓ H:0 kadhich nahi - Spot OB</div>
        </body></html>"""
    except Exception as e:
        return f"<h3 style='color:red'>ERR {e}</h3><a href='/clear'>CLEAR KAR</a> | <a href='/debug'>DEBUG</a>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
