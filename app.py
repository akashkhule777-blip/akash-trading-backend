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

OB_FILE = "/tmp/ob_auto_atm.json"
STATE_FILE = "/tmp/state_auto_atm.json"

def ist_now(): return datetime.now(IST)
def load(p,d):
    if os.path.exists(p):
        try:
            with open(p,'r') as f: return json.load(f)
        except: pass
    return d
def save(p,d):
    try:
        with open(p,'w') as f: json.dump(d,f)
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

def get_live_atm(obj):
    nifty = 23450.0
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass
    strike = int(round(nifty/50)*50) # AUTO ATM
    ce_sym=ce_tok=pe_sym=pe_tok=""; ce_l=pe_l=0.0
    try:
        r = obj.searchScrip("NFO", "NIFTY")
        for it in r.get('data', []):
            s = it.get('tradingsymbol','')
            if str(strike) in s and "SEP" in s and "2026" in s:
                if s.endswith("CE") and not ce_sym:
                    ce_sym=s; ce_tok=it['symboltoken']
                    try: ce_l=float(obj.ltpData("NFO", s, ce_tok)['data']['ltp'])
                    except: pass
                if s.endswith("PE") and not pe_sym:
                    pe_sym=s; pe_tok=it['symboltoken']
                    try: pe_l=float(obj.ltpData("NFO", s, pe_tok)['data']['ltp'])
                    except: pass
    except: pass
    return nifty, strike, ce_sym, ce_tok, ce_l, pe_sym, pe_tok, pe_l

def place(obj, sym, tok, side):
    if not REAL: return "PAPER"
    try:
        p = {"variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","price":"0","triggerprice":"0","squareoff":"0","stoploss":"0","quantity":str(QTY)}
        return obj.placeOrder(p)
    except Exception as e: return f"FAIL {e}"

def fetch_ob(obj, token, strike):
    today = ist_now().strftime("%Y-%m-%d")
    cached = load(OB_FILE, {})
    # Strike badlala tar nava OB fetch kara
    if cached.get("date")==today and cached.get("strike")==strike and cached.get("h3",0)!=0:
        return cached
    try:
        d = obj.getCandleData({"exchange":"NFO","symboltoken":token,"interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:40"})
        if d and d.get('data') and len(d['data'])>=10:
            c = d['data']
            h3 = max(float(c[i][2]) for i in range(0,3)); l3 = min(float(c[i][3]) for i in range(0,3)); f3 = round((h3+l3)/2,2)
            h2 = max(float(c[i][2]) for i in range(3,6)); cl2 = float(c[5][4]); up3 = cl2 > h3 or h2 > h3
            l2 = min(float(c[i][3]) for i in range(3,6)); down3 = cl2 < l3 or l2 < l3

            h5 = max(float(c[i][2]) for i in range(0,5)); l5 = min(float(c[i][3]) for i in range(0,5)); f5 = round((h5+l5)/2,2)
            h2_5 = max(float(c[i][2]) for i in range(5,10)); cl2_5 = float(c[9][4]); up5 = cl2_5 > h5 or h2_5 > h5
            l2_5 = min(float(c[i][3]) for i in range(5,10)); down5 = cl2_5 < l5 or l2_5 < l5

            ob = {"h3":h3,"l3":l3,"f3":f3,"up3":up3,"down3":down3,"h5":h5,"l5":l5,"f5":f5,"up5":up5,"down5":down5,"date":today,"strike":strike,"tok":token}
            save(OB_FILE, ob)
            return ob
    except Exception as e:
        print(e)
    return cached if cached.get("h3") else {"h3":0,"l3":0,"f3":0,"up3":False,"down3":False,"h5":0,"l5":0,"f5":0,"up5":False,"down5":False,"date":today,"strike":strike,"tok":token}

STATE = load(STATE_FILE, {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","typ3":"","e3":0,"pnl3":0,"date":""})

@app.route('/clear')
def clear():
    for f in [OB_FILE, STATE_FILE]:
        try: os.remove(f)
        except: pass
    return "CLEARED <a href='/'>HOME</a>"

@app.route('/')
def home():
    global STATE
    obj = get_client()
    now = ist_now(); ct = now.strftime("%H:%M:%S"); chm = now.strftime("%H:%M"); today = now.strftime("%Y-%m-%d")
    if STATE.get("date")!=today:
        STATE = {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","typ3":"","e3":0,"pnl3":0,"date":today}
        save(STATE_FILE, STATE)

    # AUTO ATM UPDATE - pratyek refresh la navin strike
    nifty, strike, ce_s, ce_t, ce_l, pe_s, pe_t, pe_l = get_live_atm(obj)

    ob = fetch_ob(obj, ce_t, strike)
    h3,l3,f3,up3,down3 = ob["h3"],ob["l3"],ob["f3"],ob["up3"],ob["down3"]
    h5,l5,f5,up5,down5 = ob["h5"],ob["l5"],ob["f5"],ob["up5"],ob["down5"]

    if h3!=0 and not up3 and ce_l > h3: up3=True
    if h3!=0 and not down3 and ce_l < l3: down3=True

    tgt_up = round(f3 + 2*(f3-l3),2) if l3 else 0
    tgt_dn = round(f3 - 2*(h3-f3),2) if h3 else 0

    m3 = f"Strike:{strike} H:{round(h3,2)} L:{round(l3,2)} 50%:{f3} UP:{up3} DOWN:{down3} TGT:{tgt_up}"
    m5 = f"H:{round(h5,2)} L:{round(l5,2)} 50%:{f5} UP:{up5} DOWN:{down5}"

    if h3!=0:
        if up3 and not STATE["a3"] and STATE["e3"]<10 and "09:21" <= chm <= "15:00":
            if abs(ce_l - f3) <= 5:
                place(obj, ce_s, ce_t, "BUY")
                STATE.update({"a3":True,"buy3":ce_l,"sl3":l3,"tgt3":tgt_up,"sym3":ce_s,"tok3":ce_t,"typ3":"CE","e3":STATE["e3"]+1,"date":today}); save(STATE_FILE, STATE)
                m3 = f"BUY CE {strike} @ {ce_l} 50% {f3} SL {l3} TGT {tgt_up} REAL"
        if STATE["a3"]:
            STATE["pnl3"]=round((ce_l-STATE["buy3"])*QTY,2); save(STATE_FILE, STATE)
            if ce_l <= STATE["sl3"] or ce_l >= STATE["tgt3"]:
                place(obj, STATE["sym3"], STATE["tok3"], "SELL"); STATE["a3"]=False; save(STATE_FILE, STATE)
                m3 = f"EXIT HIT LTP {ce_l} PNL {STATE['pnl3']}"
            else:
                m3 = f"LIVE {STATE['typ3']} BUY {STATE['buy3']} LTP {ce_l} PNL {STATE['pnl3']} | SL Low {STATE['sl3']} TGT 1:2 {STATE['tgt3']} | {m3}"

    return f"""<html><head><meta http-equiv="refresh" content="2"><style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:10px;background:#111}}.gold{{border-color:gold;background:#221d00}}</style></head><body>
    <h2 style="color:gold">AUTO ATM UPDATE | {ct} | NIFTY {nifty} | STRIKE {strike} AUTO</h2>
    <div class="box">NIFTY {nifty} → AUTO ATM <b style="color:yellow;font-size:22px">{strike}</b> | CE LTP <b style="color:#0ff;font-size:26px">{ce_l}</b> PE {pe_l} | QTY {QTY} | REAL {REAL} | <a href='/clear' style='color:red'>/clear</a><br>Strike Nifty halala ki auto badlel: 23450 → 23500 → 23400</div>
    <div class="box gold"><b>3MIN OB (ATM {strike} CE CHART):</b> {m3}<br>Entry 50% var | SL Low | TGT 1:2 | Entries {STATE['e3']}/10</div>
    <div class="box gold" style="border-color:#0ff"><b>5MIN OB:</b> {m5}</div>
    <div class="box" style="border-color:lime">✓ ATM chi strike price auto update - Nifty 23451 asel tar 23450, 23476 jhala ki 23500 hoil<br>✓ OB pan navin strike var auto banil | CE/PE LTP live</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
