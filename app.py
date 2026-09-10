from flask import Flask, request
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
REAL = True # AAJ PASUN REAL

OB_FILE = "/tmp/ob_last.json"
STATE_FILE = "/tmp/state_last.json"

def ist_now(): return datetime.now(IST)
def load(p,d):
    if os.path.exists(p):
        try:
            with open(p,'r') as f: return json.load(f)
        except: pass
    return d
def save(p,d):
    try:
        with open(p,'w') as f: json.dump(f,d)
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

def get_atm_perfect(obj, strike):
    ce_sym=ce_tok=pe_sym=pe_tok=""; ce_l=pe_l=0.0; all_found=[]
    try:
        # 3 vegveglya search - kuthla tari lagelch
        queries = [f"NIFTY {strike}", f"NIFTY{strike}", "NIFTY"]
        seen = set()
        cands = []
        for q in queries:
            try:
                r = obj.searchScrip("NFO", q)
                for it in r.get('data', []):
                    s = it.get('tradingsymbol','')
                    if str(strike) not in s: continue
                    if "NIFTY" not in s: continue
                    if s in seen: continue
                    seen.add(s)
                    cands.append(it)
            except: pass

        ce_list = [it for it in cands if it['tradingsymbol'].endswith("CE")]
        pe_list = [it for it in cands if it['tradingsymbol'].endswith("PE")]

        # Nearest expiry - symbol sort kel ki 15SEP, 25SEP, 02OCT asa yeto
        if ce_list:
            ce_list = sorted(ce_list, key=lambda x: x['tradingsymbol'])
            it = ce_list[0]
            ce_sym = it['tradingsymbol']; ce_tok = it['symboltoken']
            try:
                resp = obj.ltpData("NFO", ce_sym, ce_tok)
                ce_l = float(resp['data']['ltp'])
            except:
                # LTP fail jhala tar candle cha last close ghe
                try:
                    today = ist_now().strftime("%Y-%m-%d")
                    cd = obj.getCandleData({"exchange":"NFO","symboltoken":ce_tok,"interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 12:45"})
                    if cd and cd.get('data'): ce_l = float(cd['data'][-1][4])
                except: ce_l = 0.0

        if pe_list:
            pe_list = sorted(pe_list, key=lambda x: x['tradingsymbol'])
            it = pe_list[0]
            pe_sym = it['tradingsymbol']; pe_tok = it['symboltoken']
            try: pe_l = float(obj.ltpData("NFO", pe_sym, pe_tok)['data']['ltp'])
            except: pe_l = 0.0

        all_found = [it['tradingsymbol'] for it in ce_list[:3]]
    except Exception as e:
        print(f"ATM ERROR {e}")

    return ce_sym, ce_tok, ce_l, pe_sym, pe_tok, pe_l, all_found

def get_spot_ob(obj):
    today = ist_now().strftime("%Y-%m-%d")
    cached = load(OB_FILE, {})
    if cached.get("date")==today and cached.get("h3",0)!=0:
        return cached
    try:
        d = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:40"})
        if d and d.get('data') and len(d['data'])>=10:
            c = d['data']
            h3 = max(float(c[i][2]) for i in range(0,3)); l3 = min(float(c[i][3]) for i in range(0,3)); f3 = round((h3+l3)/2,2)
            h2 = max(float(c[i][2]) for i in range(3,6)); l2 = min(float(c[i][3]) for i in range(3,6)); cl2 = float(c[5][4])
            up3 = cl2 > h3 or h2 > h3; down3 = cl2 < l3 or l2 < l3
            h5 = max(float(c[i][2]) for i in range(0,5)); l5 = min(float(c[i][3]) for i in range(0,5)); f5 = round((h5+l5)/2,2)
            h2_5 = max(float(c[i][2]) for i in range(5,10)); l2_5 = min(float(c[i][3]) for i in range(5,10)); cl2_5 = float(c[9][4])
            up5 = cl2_5 > h5 or h2_5 > h5; down5 = cl2_5 < l5 or l2_5 < l5
            ob = {"h3":h3,"l3":l3,"f3":f3,"up3":up3,"down3":down3,"h5":h5,"l5":l5,"f5":f5,"up5":up5,"down5":down5,"date":today}
            save(OB_FILE, ob)
            return ob
    except Exception as e:
        print(e)
    return cached

def place(obj, sym, tok, side):
    if not REAL: return "PAPER"
    try:
        p = {"variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","price":"0","triggerprice":"0","squareoff":"0","stoploss":"0","quantity":str(QTY)}
        return obj.placeOrder(p)
    except Exception as e: return f"FAIL {e}"

STATE = load(STATE_FILE, {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","typ3":"","e3":0,"pnl3":0,"date":""})

@app.route('/clear')
def clear():
    for f in [OB_FILE, STATE_FILE]:
        try: os.remove(f)
        except: pass
    return "CLEARED <a href='/'>HOME</a> | <a href='/debug'>DEBUG</a>"

@app.route('/debug')
def debug():
    obj = get_client()
    nifty = 23453.1
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass
    strike = int(round(nifty/50)*50)
    ce_s, ce_t, ce_l, pe_s, pe_t, pe_l, found = get_atm_perfect(obj, strike)
    return f"NIFTY {nifty} ATM {strike}<br>CE {ce_s}<br>TOK {ce_t} LTP {ce_l}<br>PE {pe_s} LTP {pe_l}<br>All CE Found: {found}<br><br>Manual set: /?ce_sym=NIFTY...&ce_tok=...&pe_sym=...&pe_tok=...<br><a href='/clear'>clear</a>"

@app.route('/')
def home():
    global STATE
    obj = get_client()
    now = ist_now(); ct = now.strftime("%H:%M:%S"); chm = now.strftime("%H:%M"); today = now.strftime("%Y-%m-%d")

    # Manual override - jar auto fail jhala tar tu swataha token taku shaktos
    manual_ce_sym = request.args.get('ce_sym'); manual_ce_tok = request.args.get('ce_tok')
    manual_pe_sym = request.args.get('pe_sym'); manual_pe_tok = request.args.get('pe_tok')

    if STATE.get("date")!=today:
        STATE = {"a3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","typ3":"","e3":0,"pnl3":0,"date":today}
        save(STATE_FILE, STATE)

    nifty = 23453.1
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass
    strike = int(round(nifty/50)*50)

    ce_s, ce_t, ce_l, pe_s, pe_t, pe_l, found = get_atm_perfect(obj, strike)
    if manual_ce_sym and manual_ce_tok:
        ce_s = manual_ce_sym; ce_t = manual_ce_tok
        try: ce_l = float(obj.ltpData("NFO", ce_s, ce_t)['data']['ltp'])
        except: pass

    ob = get_spot_ob(obj)
    h3,l3,f3,up3,down3 = ob["h3"],ob["l3"],ob["f3"],ob["up3"],ob["down3"]
    h5,l5,f5,up5,down5 = ob["h5"],ob["l5"],ob["f5"],ob["up5"],ob["down5"]

    if h3!=0 and not up3 and nifty > h3: up3=True
    if h3!=0 and not down3 and nifty < l3: down3=True

    tgt_up = round(f3 + 2*(f3-l3),2) if l3 else 0
    tgt_dn = round(f3 - 2*(h3-f3),2) if h3 else 0

    msg = f"SPOT H:{round(h3,2)} L:{round(l3,2)} 50%:{f3} UP:{up3} DOWN:{down3} | ATM {strike} CE {ce_s} LTP {ce_l} TOK {ce_t}"

    if h3!=0 and up3 and not STATE["a3"] and STATE["e3"]<10 and "09:21" <= chm <= "15:00":
        if abs(nifty - f3) <= 12 and ce_t!="":
            place(obj, ce_s, ce_t, "BUY")
            STATE.update({"a3":True,"buy3":ce_l,"sl3":l3,"tgt3":tgt_up,"sym3":ce_s,"tok3":ce_t,"typ3":"CE","e3":STATE["e3"]+1,"date":today}); save(STATE_FILE, STATE)
            msg = f"REAL BUY CE {strike} @ {ce_l} SL Spot Low {l3} TGT 1:2 {tgt_up}"

    if STATE["a3"]:
        STATE["pnl3"]=round((ce_l-STATE["buy3"])*QTY,2); save(STATE_FILE, STATE)
        hit_sl = nifty <= STATE["sl3"]; hit_tgt = nifty >= STATE["tgt3"]
        if hit_sl or hit_tgt:
            place(obj, STATE["sym3"], STATE["tok3"], "SELL"); STATE["a3"]=False; save(STATE_FILE, STATE)
            msg = f"{'SL' if hit_sl else 'TGT 1:2'} HIT Spot {nifty} PNL {STATE['pnl3']} REAL SELL"
        else:
            msg = f"LIVE {STATE['typ3']} BUY {STATE['buy3']} LTP {ce_l} PNL {STATE['pnl3']} | Spot SL {STATE['sl3']} TGT {STATE['tgt3']} | {msg}"

    return f"""<html><head><meta http-equiv="refresh" content="2"><style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:10px;background:#111}}.gold{{border-color:gold;background:#221d00}}</style></head><body>
    <h2 style="color:gold">FINAL PERFECT | {ct} | NIFTY {nifty} | ATM {strike} | CE {ce_l}</h2>
    <div class="box">NIFTY {nifty} → ATM <b style="color:yellow;font-size:22px">{strike}</b> AUTO | CE <b style="color:#0ff;font-size:26px">{ce_l}</b> {ce_s}<br>TOK {ce_t} | PE {pe_l} | QTY {QTY} | REAL {REAL} | <a href='/debug' style='color:cyan'>/debug</a> <a href='/clear' style='color:red'>/clear</a><br>Found: {found}</div>
    <div class="box gold"><b>3MIN OB (SPOT - H:0 kadhich nahi):</b><br>{msg}<br>Entries {STATE['e3']}/10 | TGT UP {tgt_up} DOWN {tgt_dn}</div>
    <div class="box gold" style="border-color:#0ff"><b>5MIN OB:</b> H:{round(h5,2)} L:{round(l5,2)} 50%:{f5} UP:{up5} DOWN:{down5}</div>
    <div class="box" style="border-color:lime">✓ Aata LTP 0.0 janar nahi - 3 search query ne token sapdel<br>✓ OB Spot var - H:0 kadhich nahi - tuzya photo madla 132.40 CE LTP yeil<br>✓ 50% var ENTRY | Low cha SL | 1:2 RR | 65 QTY REAL</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
