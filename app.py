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
OB_FILE = "/tmp/ob_real.json"
TRADE_FILE = "/tmp/trade_real.json"
REAL_TRADING = True
SL_PERCENT = 30 # 30% SL
TARGET_PERCENT = 60 # 60% Target = 1:2

def ist_now(): return datetime.now(IST)
def load_json(p,d):
    if os.path.exists(p):
        try:
            with open(p,'r') as f: return json.load(f)
        except: pass
    return d
def save_json(p,data):
    try:
        with open(p,'w') as f: json.dump(data,f)
    except: pass

OB_STORE = load_json(OB_FILE, {"h3":0,"l3":0,"fifty3":0,"locked3":False,"active3":False,"h5":0,"l5":0,"fifty5":0,"locked5":False,"active5":False,"date":""})
TRADE_STORE = load_json(TRADE_FILE, {"buy3":0,"ltp3":0,"pnl3":0,"sym3":"","tok3":"0","ordered3":False,"sl_ordered3":False,"tgt_ordered3":False,"sl_price3":0,"tgt_price3":0,"date":""})

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
    return f"NIFTY15SEP26{strike}{typ}", "0", 0.0, strike

def place_order(obj, symbol, token, qty, side, otype, trigger=0, price=0):
    try:
        variety = "STOPLOSS" if "STOPLOSS" in otype else "NORMAL"
        params = {
            "variety": variety,
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": side,
            "exchange": "NFO",
            "ordertype": otype,
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": str(price) if price!=0 else "0",
            "triggerprice": str(trigger) if trigger!=0 else "0",
            "squareoff": "0","stoploss": "0",
            "quantity": str(qty)
        }
        resp = obj.placeOrder(params)
        print(f"{side} {otype} {symbol} P:{price} T:{trigger} -> {resp}")
        return resp
    except Exception as e:
        print(f"FAIL {e}")
        return f"FAIL {e}"

def fetch_history(obj):
    global OB_STORE
    today = ist_now().strftime("%Y-%m-%d")
    if OB_STORE.get("date")!=today:
        OB_STORE = {"h3":0,"l3":0,"fifty3":0,"locked3":False,"active3":False,"h5":0,"l5":0,"fifty5":0,"locked5":False,"active5":False,"date":today}
    for token in ["26000","99926000"]:
        try:
            frm = f"{today} 09:15"; to = f"{today} 09:35"
            data = obj.getCandleData({"exchange":"NSE","symboltoken":token,"interval":"ONE_MINUTE","fromdate":frm,"todate":to})
            if data and data.get('data') and len(data['data'])>=5:
                c = data['data']
                c3 = c[:3]; h3 = max(float(x[2]) for x in c3); l3 = min(float(x[3]) for x in c3)
                c5 = c[:5]; h5 = max(float(x[2]) for x in c5); l5 = min(float(x[3]) for x in c5)
                a3 = any(float(x[2])>h3 for x in c[3:]); a5 = any(float(x[2])>h5 for x in c[5:])
                OB_STORE.update({"h3":h3,"l3":l3,"fifty3":round((h3+l3)/2,2),"locked3":True,"active3":a3,"h5":h5,"l5":l5,"fifty5":round((h5+l5)/2,2),"locked5":True,"active5":a5,"date":today})
                save_json(OB_FILE, OB_STORE)
                return True
        except: pass
    return False

@app.route('/')
def home():
    global OB_STORE, TRADE_STORE
    obj = get_client()
    now = ist_now()
    cur_time = now.strftime("%H:%M:%S"); cur_hm = now.strftime("%H:%M"); today = now.strftime("%Y-%m-%d")
    nifty = 23432.0
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass
    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")

    if OB_STORE.get("date")!=today:
        OB_STORE = {"h3":0,"l3":0,"fifty3":0,"locked3":False,"active3":False,"h5":0,"l5":0,"fifty5":0,"locked5":False,"active5":False,"date":today}
    if TRADE_STORE.get("date")!=today:
        TRADE_STORE = {"buy3":0,"ltp3":0,"pnl3":0,"sym3":"","tok3":"0","ordered3":False,"sl_ordered3":False,"tgt_ordered3":False,"sl_price3":0,"tgt_price3":0,"date":today}

    if OB_STORE["h3"]==0: fetch_history(obj)
    if "09:15" <= cur_hm <= "09:18":
        if OB_STORE["h3"]==0: OB_STORE["h3"]=nifty; OB_STORE["l3"]=nifty
        else:
            if nifty>OB_STORE["h3"]: OB_STORE["h3"]=nifty
            if nifty<OB_STORE["l3"]: OB_STORE["l3"]=nifty
        save_json(OB_FILE, OB_STORE)
    if "09:15" <= cur_hm <= "09:20":
        if OB_STORE["h5"]==0: OB_STORE["h5"]=nifty; OB_STORE["l5"]=nifty
        else:
            if nifty>OB_STORE["h5"]: OB_STORE["h5"]=nifty
            if nifty<OB_STORE["l5"]: OB_STORE["l5"]=nifty
        save_json(OB_FILE, OB_STORE)
    if cur_hm > "09:30" and OB_STORE["h3"]==0:
        OB_STORE.update({"h3":nifty+12,"l3":nifty-12,"fifty3":nifty,"locked3":True,"active3":True,"h5":nifty+18,"l5":nifty-18,"fifty5":nifty,"locked5":True,"active5":True,"date":today})
        save_json(OB_FILE, OB_STORE)
    if OB_STORE["h3"]!=0 and not OB_STORE["locked3"] and cur_hm>"09:18":
        OB_STORE["fifty3"]=round((OB_STORE["h3"]+OB_STORE["l3"])/2,2); OB_STORE["locked3"]=True; save_json(OB_FILE, OB_STORE)
    if OB_STORE["h5"]!=0 and not OB_STORE["locked5"] and cur_hm>"09:20":
        OB_STORE["fifty5"]=round((OB_STORE["h5"]+OB_STORE["l5"])/2,2); OB_STORE["locked5"]=True; save_json(OB_FILE, OB_STORE)
    if OB_STORE["locked3"] and nifty>OB_STORE["h3"]: OB_STORE["active3"]=True; save_json(OB_FILE, OB_STORE)
    if OB_STORE["locked5"] and nifty>OB_STORE["h5"]: OB_STORE["active5"]=True; save_json(OB_FILE, OB_STORE)

    # BUY + SL + TARGET
    msg = "WAIT"
    if OB_STORE["locked3"] and OB_STORE["active3"] and cur_hm>"09:18":
        if abs(nifty - OB_STORE["fifty3"]) < 15 and not TRADE_STORE["ordered3"] and "09:20" <= cur_hm <= "14:30":
            place_order(obj, ce_sym, ce_tok, QTY, "BUY", "MARKET", 0, 0)
            TRADE_STORE.update({"buy3":ce_ltp,"ltp3":ce_ltp,"sym3":ce_sym,"tok3":ce_tok,"ordered3":True,"date":today})
            save_json(TRADE_FILE, TRADE_STORE)

    if TRADE_STORE["ordered3"] and not TRADE_STORE["sl_ordered3"]:
        sl = round(TRADE_STORE["buy3"] * (1 - SL_PERCENT/100),1)
        if sl<1: sl=1
        place_order(obj, TRADE_STORE["sym3"], TRADE_STORE["tok3"], QTY, "SELL", "STOPLOSS_MARKET", sl, 0)
        TRADE_STORE["sl_price3"]=sl; TRADE_STORE["sl_ordered3"]=True
        save_json(TRADE_FILE, TRADE_STORE)

    if TRADE_STORE["ordered3"] and not TRADE_STORE["tgt_ordered3"]:
        tgt = round(TRADE_STORE["buy3"] * (1 + TARGET_PERCENT/100),1)
        place_order(obj, TRADE_STORE["sym3"], TRADE_STORE["tok3"], QTY, "SELL", "LIMIT", 0, tgt)
        TRADE_STORE["tgt_price3"]=tgt; TRADE_STORE["tgt_ordered3"]=True
        save_json(TRADE_FILE, TRADE_STORE)
        msg = f"BUY {TRADE_STORE['buy3']} | SL {TRADE_STORE['sl_price3']} | TGT {tgt} LAGLE"

    if TRADE_STORE["ordered3"]:
        TRADE_STORE["ltp3"]=ce_ltp
        TRADE_STORE["pnl3"]=round((ce_ltp - TRADE_STORE["buy3"])*QTY,2)
        save_json(TRADE_FILE, TRADE_STORE)
        msg = f"LIVE BUY {TRADE_STORE['buy3']} LTP {ce_ltp} PNL {TRADE_STORE['pnl3']} | SL {TRADE_STORE['sl_price3']} TGT {TRADE_STORE['tgt_price3']}"

    return f"""
    <html><head>
    <meta http-equiv="refresh" content="3">
    <script>setTimeout(()=>{{location.reload();}}, 3000);</script>
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:6px}}.box{{border:1px solid #0f0;padding:8px;margin:4px;border-radius:8px;background:#111}}.real{{border-color:gold;background:#332200}}</style>
    </head><body>
    <h2 style="color:gold">🟡 REAL BUY + SL {SL_PERCENT}% + TGT {TARGET_PERCENT}% | {cur_time} IST</h2>
    <div class="box" style="border-color:yellow">NIFTY: <b style="font-size:22px;color:#ff0">{nifty}</b> | {ce_sym} LTP <b style="color:#0ff;font-size:22px">{ce_ltp}</b></div>
    <div style="display:flex;gap:6px">
        <div class="box" style="flex:1">3M H:{round(OB_STORE['h3'],2)} L:{round(OB_STORE['l3'],2)} 50%:{OB_STORE['fifty3']} Brk:{OB_STORE['active3']}</div>
        <div class="box" style="flex:1">5M H:{round(OB_STORE['h5'],2)} L:{round(OB_STORE['l5'],2)} 50%:{OB_STORE['fifty5']} Brk:{OB_STORE['active5']}</div>
    </div>
    <div class="box real"><b>{msg}</b><br>BUY: {TRADE_STORE['buy3']} | SL: {TRADE_STORE['sl_price3']} ({SL_PERCENT}%) | TGT: {TRADE_STORE['tgt_price3']} ({TARGET_PERCENT}%)<br><b style="font-size:22px;color:{'lime' if TRADE_STORE['pnl3']>=0 else 'red'}">PNL: {TRADE_STORE['pnl3']} Rs | QTY {QTY}</b><br>SL: {TRADE_STORE['sl_ordered3']} TGT: {TRADE_STORE['tgt_ordered3']}</div>
    <div class="box">✓ 3 Sec Refresh | ✓ Buy + SL + Target Sota | Buy=100 asel tar SL=70 TGT=160</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
