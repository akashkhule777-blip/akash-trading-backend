from flask import Flask
from flask_cors import CORS
import os, json, re
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

def parse_expiry(sym):
    try:
        m = re.search(r'(\d{2})([A-Z]{3})(\d{2,4})', sym.upper())
        if not m: return None
        dd = int(m.group(1)); mon_str = m.group(2); yy = int(m.group(3))
        if yy < 100: yy += 2000
        mon_map = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        mon = mon_map.get(mon_str, 9)
        return datetime(yy, mon, dd)
    except: return None

def get_atm_15sep(obj, nifty):
    strike = int(round(nifty/50)*50)
    ce_sym=ce_tok=pe_sym=pe_tok=""; ce_l=pe_l=0.0
    try:
        r = obj.searchScrip("NFO", f"NIFTY {strike}")
        data = r.get('data', []) if r else []
        if not data:
            r2 = obj.searchScrip("NFO", "NIFTY")
            data = r2.get('data', []) if r2 else []
        ce_cands = [x for x in data if str(strike) in x.get('tradingsymbol','') and x.get('tradingsymbol','').endswith('CE')]
        dated = []
        for it in ce_cands:
            dt = parse_expiry(it['tradingsymbol'])
            if dt: dated.append((dt, it))
        if dated:
            dated = sorted(dated, key=lambda x: x[0])
            it = dated[0][1]
            ce_sym = it['tradingsymbol']; ce_tok = it['symboltoken']
            try: ce_l = float(obj.ltpData("NFO", ce_sym, ce_tok)['data']['ltp'])
            except: ce_l = 0.0
            ce_exp = parse_expiry(ce_sym)
            pe_match = [x for x in data if str(strike) in x.get('tradingsymbol','') and x.get('tradingsymbol','').endswith('PE') and parse_expiry(x.get('tradingsymbol',''))==ce_exp]
            if pe_match:
                pe_sym = pe_match[0]['tradingsymbol']; pe_tok = pe_match[0]['symboltoken']
                try: pe_l = float(obj.ltpData("NFO", pe_sym, pe_tok)['data']['ltp'])
                except: pe_l = 0.0
    except Exception as e:
        print(e)
    return strike, ce_sym, ce_tok, ce_l, pe_sym, pe_tok, pe_l

def get_ob_strong(obj, nifty_now):
    today = ist_now()
    for delta in [0,1,2,3]:
        try_date = (today - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            d = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"ONE_MINUTE","fromdate":f"{try_date} 09:15","todate":f"{try_date} 09:40"})
            if d and d.get('data') and len(d['data'])>=6:
                c = d['data']
                h3 = max(float(c[i][2]) for i in range(0,3)); l3 = min(float(c[i][3]) for i in range(0,3)); f3 = round((h3+l3)/2,2)
                h5 = max(float(c[i][2]) for i in range(0,5)); l5 = min(float(c[i][3]) for i in range(0,5)); f5 = round((h5+l5)/2,2)
                ob = {"h3":h3,"l3":l3,"f3":f3,"h5":h5,"l5":l5,"f5":f5,"date":try_date}
                save(OB_FILE, ob)
                return ob
        except: pass
    cached = load(OB_FILE, {})
    if cached.get("h3",0)!=0: return cached
    return {"h3":nifty_now+20,"l3":nifty_now-20,"f3":nifty_now,"h5":nifty_now+30,"l5":nifty_now-30,"f5":nifty_now,"date":today.strftime("%Y-%m-%d")}

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
    return "CLEARED - <a href='/'>HOME</a> | <a href='/debug'>DEBUG</a>"

@app.route('/debug')
def debug():
    try:
        obj = get_client()
        nifty = 23435.1
        try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: pass
        strike, ce_s, ce_t, ce_l, pe_s, pe_t, pe_l = get_atm_15sep(obj, nifty)
        ob = get_ob_strong(obj, nifty)
        return f"NIFTY {nifty} ATM {strike}<br>CE {ce_s} TOK {ce_t} LTP {ce_l}<br>PE {pe_s} LTP {pe_l}<br>OB {ob}<br><a href='/clear'>clear</a> <a href='/'>home</a>"
    except Exception as e:
        return f"DEBUG ERR {e}"

@app.route('/')
def home():
    try:
        global STATE
        obj = get_client()
        now = ist_now(); ct = now.strftime("%H:%M:%S"); chm = now.strftime("%H:%M"); today = now.strftime("%Y-%m-%d")
        if STATE.get("date")!=today:
            STATE = {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","e3":0,"pnl3":0,"date":today}
            save(STATE_FILE, STATE)

        nifty = 23435.1
        try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: pass

        strike, ce_s, ce_t, ce_l, pe_s, pe_t, pe_l = get_atm_15sep(obj, nifty)
        ob = get_ob_strong(obj, nifty)
        h3,l3,f3 = ob["h3"],ob["l3"],ob["f3"]
        h5,l5,f5 = ob["h5"],ob["l5"],ob["f5"]
        tgt_up = round(f3 + 2*(f3-l3),2) if l3 else 0

        # NO UPTREND / NO 20 EMA - Fakt 50% Retrace
        msg = f"ATM {strike} CE {ce_s} LTP {ce_l} | OB H:{round(h3,1)} L:{round(l3,1)} 50%:{f3} | NIFTY {nifty}"

        if h3!=0 and not STATE["a3"] and STATE["e3"]<10 and "09:21" <= chm <= "15:00":
            if abs(nifty - f3) <= 15 and ce_t!="":
                place(obj, ce_s, ce_t, "BUY")
                STATE.update({"a3":True,"buy3":ce_l,"sl3":l3,"tgt3":tgt_up,"sym3":ce_s,"tok3":ce_t,"e3":STATE["e3"]+1,"date":today}); save(STATE_FILE, STATE)
                msg = f"BUY CE {strike} @ {ce_l} | 50% RETRACE ENTRY | SL {l3} TGT {tgt_up}"

        if STATE["a3"]:
            STATE["pnl3"]=round((ce_l-STATE["buy3"])*QTY,2); save(STATE_FILE, STATE)
            if nifty <= STATE["sl3"] or nifty >= STATE["tgt3"]:
                place(obj, STATE["sym3"], STATE["tok3"], "SELL"); STATE["a3"]=False; save(STATE_FILE, STATE)
                msg = f"EXIT Spot {nifty} PNL {STATE['pnl3']}"
            else:
                msg = f"LIVE BUY {STATE['buy3']} LTP {ce_l} PNL {STATE['pnl3']} | {msg}"

        return f"""<html><head><meta http-equiv="refresh" content="2"><style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:10px;background:#111}}.gold{{border-color:gold;background:#221d00}}</style></head><body>
        <h2 style="color:gold">FINAL NO FILTER | {ct} | NIFTY {nifty} | ATM {strike} | CE {ce_l}</h2>
        <div class="box">NIFTY {nifty} → ATM <b style="color:yellow;font-size:22px">{strike}</b> | CE <b style="color:#0ff;font-size:26px">{ce_l}</b> {ce_s}<br>PE {pe_l} | QTY {QTY} REAL {REAL} | <a href='/debug' style='color:cyan'>/debug</a> <a href='/clear' style='color:red'>/clear</a></div>
        <div class="box gold"><b>3MIN OB - NO TREND NO EMA:</b> {msg}<br>Entries {STATE['e3']}/10 TGT {tgt_up}</div>
        <div class="box gold" style="border-color:#0ff"><b>5MIN OB:</b> H:{round(h5,1)} L:{round(l5,1)} 50%:{f5}</div>
        <div class="box" style="border-color:lime">✓ 15 SEP weekly - 06 OCT nahi<br>✓ OB H:0 fix<br>✓ Uptrend filter kadhla<br>✓ 20 EMA filter kadhla<br>✓ Fakt 50% retrace var entry</div>
        </body></html>"""
    except Exception as e:
        return f"<h3 style='color:red'>ERR {e}</h3><a href='/clear'>CLEAR</a> | <a href='/debug'>DEBUG</a>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
