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

OB_FILE = "/tmp/ob_live.json"
STATE_FILE = "/tmp/state_live.json"

def ist_now(): return datetime.now(IST)

def load(p, d):
    if os.path.exists(p):
        try:
            with open(p,'r') as f: return json.load(f)
        except: pass
    return d

def save(p, d):
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

def get_atm(obj, nifty, typ):
    strike = int(round(nifty/50)*50)
    try:
        r = obj.searchScrip("NFO", "NIFTY")
        for it in r.get('data', []):
            s = it.get('tradingsymbol','')
            if str(strike) in s and typ in s and "SEP" in s:
                tok = it['symboltoken']
                ltp = float(obj.ltpData("NFO", s, tok)['data']['ltp'])
                return s, tok, ltp, strike
    except: pass
    return f"NIFTY{strike}{typ}", "0", 0.0, strike

def place(obj, sym, tok, side):
    if not REAL: return "PAPER"
    try:
        p = {"variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","price":"0","triggerprice":"0","squareoff":"0","stoploss":"0","quantity":str(QTY)}
        return obj.placeOrder(p)
    except Exception as e: return f"FAIL {e}"

def fetch_ob_final(obj):
    today = ist_now().strftime("%Y-%m-%d")
    # 1. File madhe asel tar toch vapra - 0 honar nahi
    cached = load(OB_FILE, {})
    if cached.get("date")==today and cached.get("h3",0)!=0:
        return cached

    # 2. Fresh fetch - 3 vela try
    for tok in ["26000","99926000"]:
        for frm, to in [(f"{today} 09:15", f"{today} 09:35"), (f"{today} 09:15", f"{today} 10:00")]:
            try:
                d = obj.getCandleData({"exchange":"NSE","symboltoken":tok,"interval":"ONE_MINUTE","fromdate":frm,"todate":to})
                if d and d.get('data') and len(d['data'])>=6:
                    c = d['data']
                    h3 = max(float(c[i][2]) for i in range(0,3)); l3 = min(float(c[i][3]) for i in range(0,3)); f3 = round((h3+l3)/2,2)
                    h2_3 = max(float(c[i][2]) for i in range(3,6)); cl2_3 = float(c[5][4])
                    up3 = cl2_3 > h3 or h2_3 > h3
                    l2_3 = min(float(c[i][3]) for i in range(3,6)); down3 = cl2_3 < l3 or l2_3 < l3

                    h5 = max(float(c[i][2]) for i in range(0,5)); l5 = min(float(c[i][3]) for i in range(0,5)); f5 = round((h5+l5)/2,2)
                    h2_5 = max(float(c[i][2]) for i in range(5,10)) if len(c)>=10 else h5
                    cl2_5 = float(c[9][4]) if len(c)>=10 else float(c[4][4])
                    up5 = cl2_5 > h5 or h2_5 > h5
                    l2_5 = min(float(c[i][3]) for i in range(5,10)) if len(c)>=10 else l5
                    down5 = cl2_5 < l5 or l2_5 < l5

                    ob = {"h3":h3,"l3":l3,"f3":f3,"up3":up3,"down3":down3,"h5":h5,"l5":l5,"f5":f5,"up5":up5,"down5":down5,"date":today}
                    save(OB_FILE, ob)
                    print(f"OB FETCHED {ob}")
                    return ob
            except Exception as e:
                print(f"OB FAIL {tok} {e}")

    # 3. Jar sagla fail zala tar cached parat de, nahi tar dummy nahi - 0 pasun vachav
    if cached: return cached
    return {"h3":0,"l3":0,"f3":0,"up3":False,"down3":False,"h5":0,"l5":0,"f5":0,"up5":False,"down5":False,"date":today}

STATE = load(STATE_FILE, {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","typ3":"","e3":0,"pnl3":0,"a5":False,"buy5":0,"sl5":0,"tgt5":0,"sym5":"","tok5":"","typ5":"","e5":0,"pnl5":0,"date":""})

@app.route('/clear')
def clear():
    for f in [OB_FILE, STATE_FILE, "/tmp/ob_live.json", "/tmp/state_live.json", "/tmp/ob.json"]:
        try: os.remove(f)
        except: pass
    return "CLEARED - <a href='/'>HOME</a>"

@app.route('/')
def home():
    global STATE
    obj = get_client()
    now = ist_now(); ct = now.strftime("%H:%M:%S"); chm = now.strftime("%H:%M"); today = now.strftime("%Y-%m-%d")
    if STATE.get("date")!=today:
        STATE = {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","typ3":"","e3":0,"pnl3":0,"a5":False,"buy5":0,"sl5":0,"tgt5":0,"sym5":"","tok5":"","typ5":"","e5":0,"pnl5":0,"date":today}
        save(STATE_FILE, STATE)

    nifty = 23450.0
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass
    ce_s,ce_t,ce_l,strike = get_atm(obj, nifty, "CE")
    pe_s,pe_t,pe_l,_ = get_atm(obj, nifty, "PE")

    ob = fetch_ob_final(obj)
    h3,l3,f3,up3,down3 = ob["h3"],ob["l3"],ob["f3"],ob["up3"],ob["down3"]
    h5,l5,f5,up5,down5 = ob["h5"],ob["l5"],ob["f5"],ob["up5"],ob["down5"]

    if h3!=0 and not up3 and nifty>h3: up3=True
    if h3!=0 and not down3 and nifty<l3: down3=True
    if h5!=0 and not up5 and nifty>h5: up5=True
    if h5!=0 and not down5 and nifty<l5: down5=True

    tgt3_up = round(f3 + 2*(f3-l3),2) if l3 else 0
    tgt3_dn = round(f3 - 2*(h3-f3),2) if h3 else 0
    tgt5_up = round(f5 + 2*(f5-l5),2) if l5 else 0
    tgt5_dn = round(f5 - 2*(h5-f5),2) if h5 else 0

    m3 = f"H:{round(h3,2)} L:{round(l3,2)} 50%:{f3} Break UP:{up3} DOWN:{down3}"
    m5 = f"H:{round(h5,2)} L:{round(l5,2)} 50%:{f5} Break UP:{up5} DOWN:{down5}"

    if h3==0:
        m3 = f"OB FETCH FAIL - Angel data nahi - 09:15 candle nahi milala - <a href='/clear'>Clear kar</a> - Time {ct}"
    else:
        # 3MIN ENTRY
        if up3 and not STATE["a3"] and STATE["e3"]<10 and "09:21" <= chm <= "15:00":
            if abs(nifty-f3)<=15:
                place(obj, ce_s, ce_t, "BUY")
                STATE.update({"a3":True,"buy3":ce_l,"sl3":l3,"tgt3":tgt3_up,"sym3":ce_s,"tok3":ce_t,"typ3":"CE","e3":STATE["e3"]+1,"date":today}); save(STATE_FILE, STATE)
                m3 = f"3M CE BUY {ce_l} Nifty {nifty} SL Low {l3} TGT 1:2 {tgt3_up} REAL"
        if down3 and not STATE["a3"] and STATE["e3"]<10 and "09:21" <= chm <= "15:00":
            if abs(nifty-f3)<=15:
                place(obj, pe_s, pe_t, "BUY")
                STATE.update({"a3":True,"buy3":pe_l,"sl3":h3,"tgt3":tgt3_dn,"sym3":pe_s,"tok3":pe_t,"typ3":"PE","e3":STATE["e3"]+1,"date":today}); save(STATE_FILE, STATE)

        if STATE["a3"]:
            cur = ce_l if STATE["typ3"]=="CE" else pe_l
            STATE["pnl3"]=round((cur-STATE["buy3"])*QTY,2); save(STATE_FILE, STATE)
            hit_sl = (STATE["typ3"]=="CE" and nifty<=STATE["sl3"]) or (STATE["typ3"]=="PE" and nifty>=STATE["sl3"])
            hit_tgt = (STATE["typ3"]=="CE" and nifty>=STATE["tgt3"]) or (STATE["typ3"]=="PE" and nifty<=STATE["tgt3"])
            if hit_sl or hit_tgt:
                place(obj, STATE["sym3"], STATE["tok3"], "SELL"); STATE["a3"]=False; save(STATE_FILE, STATE)
                m3 = f"3M {STATE['typ3']} {'SL' if hit_sl else 'TGT 1:2'} HIT PNL {STATE['pnl3']}"
            else:
                m3 = f"3M {STATE['typ3']} LIVE BUY {STATE['buy3']} LTP {cur} PNL {STATE['pnl3']} | SL {STATE['sl3']} (OB Low) TGT {STATE['tgt3']} (1:2) - {m3}"

    return f"""<html><head><meta http-equiv="refresh" content="3"><style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:10px;background:#111}}.gold{{border-color:gold;background:#221d00}}</style></head><body>
    <h2 style="color:gold">OB 50% ENTRY | LOW SL | 1:2 RR | {ct} | NIFTY {nifty} | H:0 FIXED</h2>
    <div class="box">ATM {strike} CE <b style="color:#0ff;font-size:24px">{ce_l}</b> PE {pe_l} QTY {QTY} REAL {REAL}</div>
    <div class="box gold"><b>3 MIN:</b> {m3}<br>Entries {STATE['e3']}/10 | TGT UP {tgt3_up} DOWN {tgt3_dn}</div>
    <div class="box gold" style="border-color:#0ff"><b>5 MIN:</b> {m5}<br>Entries {STATE['e5']}/10 | TGT UP {tgt5_up} DOWN {tgt5_dn}</div>
    <div class="box" style="border-color:red">Jar ajun H:0 disla tar /clear dabav - OB file clear hoil - Angel data parat fetch hoil - Screenshot madhe H:0 hota mhanun entry nahi lagli</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
