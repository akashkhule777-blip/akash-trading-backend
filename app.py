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
REAL_TRADING = True # Aaj pasun REAL BUY/SELL

def ist_now(): return datetime.now(IST)

def get_client():
    global angel
    from SmartApi import SmartConnect
    import pyotp
    if angel is None:
        s = SmartConnect(api_key=API_KEY)
        s.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
        angel = s
    return angel

def get_atm(obj, nifty, typ):
    strike = int(round(nifty/50)*50)
    try:
        r = obj.searchScrip("NFO", "NIFTY")
        for it in r.get('data', []):
            sym = it.get('tradingsymbol','')
            if str(strike) in sym and typ in sym and "SEP" in sym:
                tok = it['symboltoken']
                ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                return sym, tok, ltp, strike
    except: pass
    return f"NIFTY{strike}{typ}", "0", 0.0, strike

def place(obj, sym, tok, side):
    if not REAL_TRADING: return "PAPER"
    try:
        p = {"variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","price":"0","triggerprice":"0","squareoff":"0","stoploss":"0","quantity":str(QTY)}
        return obj.placeOrder(p)
    except Exception as e: return f"FAIL {e}"

def get_ob():
    """First candle = OB, Second candle break check"""
    obj = get_client()
    today = ist_now().strftime("%Y-%m-%d")
    try:
        data = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:35"})
        if data and data.get('data') and len(data['data'])>=10:
            c = data['data']
            # 3MIN OB = 0,1,2
            h3 = max(float(c[i][2]) for i in range(0,3))
            l3 = min(float(c[i][3]) for i in range(0,3))
            fifty3 = round((h3+l3)/2,2)
            # 2nd 3MIN = 3,4,5
            high2_3 = max(float(c[i][2]) for i in range(3,6))
            close2_3 = float(c[5][4])
            break3 = close2_3 > h3 or high2_3 > h3

            # 5MIN OB = 0-4
            h5 = max(float(c[i][2]) for i in range(0,5))
            l5 = min(float(c[i][3]) for i in range(0,5))
            fifty5 = round((h5+l5)/2,2)
            # 2nd 5MIN = 5-9
            high2_5 = max(float(c[i][2]) for i in range(5,10))
            close2_5 = float(c[9][4])
            break5 = close2_5 > h5 or high2_5 > h5

            return h3,l3,fifty3,break3, h5,l5,fifty5,break5
    except Exception as e:
        print(e)
    return 0,0,0,False,0,0,0,False

# In-memory store
STATE = {"active3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","e3":0,"pnl3":0,
         "active5":False,"buy5":0,"sl5":0,"tgt5":0,"sym5":"","tok5":"","e5":0,"pnl5":0, "date":""}

@app.route('/')
def home():
    global STATE
    obj = get_client()
    now = ist_now()
    ct = now.strftime("%H:%M:%S")
    chm = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")

    if STATE["date"]!= today:
        STATE = {"active3":False,"buy3":0,"sl3":0,"tgt3":0,"sym3":"","tok3":"","e3":0,"pnl3":0,
                 "active5":False,"buy5":0,"sl5":0,"tgt5":0,"sym5":"","tok5":"","e5":0,"pnl5":0,"date":today}

    nifty = 23440.0
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass
    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")

    h3,l3,fifty3,break3, h5,l5,fifty5,break5 = get_ob()

    # Tujha formula: SL = OB Low, Risk = 50% - Low, TGT = 50% + 2*Risk
    tgt3 = round(fifty3 + 2*(fifty3 - l3),2) if l3 else 0
    tgt5 = round(fifty5 + 2*(fifty5 - l5),2) if l5 else 0

    msg3 = f"H:{round(h3,2)} L:{round(l3,2)} 50%:{fifty3} Break:{break3}"
    msg5 = f"H:{round(h5,2)} L:{round(l5,2)} 50%:{fifty5} Break:{break5}"

    # LIVE Break update - third candle pasun pan
    if h3!=0 and not break3 and nifty > h3: break3 = True
    if h5!=0 and not break5 and nifty > h5: break5 = True

    # ===== 3 MIN ENTRY: 50% retracement var =====
    if h3!=0 and break3 and not STATE["active3"] and STATE["e3"] < 10 and "09:21" <= chm <= "14:30":
        if abs(nifty - fifty3) <= 10: # 50% la aala
            place(obj, ce_sym, ce_tok, "BUY")
            STATE.update({"active3":True,"buy3":ce_ltp,"sl3":l3,"tgt3":tgt3,"sym3":ce_sym,"tok3":ce_tok,"e3":STATE["e3"]+1,"date":today})
            msg3 = f"3M ENTRY CE {ce_ltp} @ Nifty {nifty} | SL Low {l3} | TGT 1:2 {tgt3}"

    # 3MIN EXIT: SL = OB Low, TGT = 1:2
    if STATE["active3"]:
        STATE["pnl3"] = round((ce_ltp - STATE["buy3"])*QTY,2)
        if nifty <= STATE["sl3"]:
            place(obj, STATE["sym3"], STATE["tok3"], "SELL")
            STATE["active3"]=False
            msg3 = f"3M SL HIT - OB Low {STATE['sl3']} todla - SELL PNL {STATE['pnl3']}"
        elif nifty >= STATE["tgt3"]:
            place(obj, STATE["sym3"], STATE["tok3"], "SELL")
            STATE["active3"]=False
            msg3 = f"3M TGT 1:2 HIT - Nifty {nifty} >= {STATE['tgt3']} - SELL PNL {STATE['pnl3']}"
        else:
            msg3 = f"3M LIVE BUY {STATE['buy3']} LTP {ce_ltp} PNL {STATE['pnl3']} | SL {STATE['sl3']} (OB Low) TGT {STATE['tgt3']} (1:2)"

    # ===== 5 MIN ENTRY: 50% retracement var =====
    if h5!=0 and break5 and not STATE["active5"] and STATE["e5"] < 10 and "09:26" <= chm <= "14:30":
        if abs(nifty - fifty5) <= 12:
            place(obj, ce_sym, ce_tok, "BUY")
            STATE.update({"active5":True,"buy5":ce_ltp,"sl5":l5,"tgt5":tgt5,"sym5":ce_sym,"tok5":ce_tok,"e5":STATE["e5"]+1,"date":today})
            msg5 = f"5M ENTRY CE {ce_ltp} SL {l5} TGT {tgt5}"

    if STATE["active5"]:
        pnl5 = round((ce_ltp - STATE["buy5"])*QTY,2)
        STATE["pnl5"]=pnl5
        if nifty <= STATE["sl5"]:
            place(obj, STATE["sym5"], STATE["tok5"], "SELL")
            STATE["active5"]=False
            msg5 = f"5M SL HIT Low {STATE['sl5']} PNL {pnl5}"
        elif nifty >= STATE["tgt5"]:
            place(obj, STATE["sym5"], STATE["tok5"], "SELL")
            STATE["active5"]=False
            msg5 = f"5M TGT 1:2 HIT {STATE['tgt5']} PNL {pnl5}"
        else:
            msg5 = f"5M LIVE BUY {STATE['buy5']} LTP {ce_ltp} PNL {pnl5} | SL {STATE['sl5']} TGT {STATE['tgt5']}"

    return f"""
    <html><head><meta http-equiv="refresh" content="2"><style>body{{background:#000;color:#fff;font-family:monospace;padding:8px}}.box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:10px;background:#111}}.gold{{border-color:gold;background:#221d00}}</style></head><body>
    <h2 style="color:gold">OB 50% ENTRY | LOW SL | 1:2 RR | {ct} | NIFTY {nifty}</h2>
    <div class="box">ATM {strike} CE LTP <b style="color:#0ff;font-size:24px">{ce_ltp}</b> | QTY {QTY} | REAL ON</div>
    <div class="box gold"><b>3 MIN ORDER BLOCK:</b><br>First 3min H:{round(h3,2)} L:{round(l3,2)} → 50%:{fifty3}<br>Second Candle Break:{break3}<br>Entry: 50% var | SL: Low {round(l3,2)} | TGT 1:2: {tgt3}<br><b style="color:yellow">{msg3}</b><br>Entries {STATE['e3']}/10</div>
    <div class="box gold" style="border-color:#0ff"><b>5 MIN ORDER BLOCK:</b><br>H:{round(h5,2)} L:{round(l5,2)} 50%:{fifty5} Break:{break5}<br>Entry: 50% var | SL: Low {round(l5,2)} | TGT 1:2: {tgt5}<br><b style="color:cyan">{msg5}</b><br>Entries {STATE['e5']}/10</div>
    <div class="box" style="border-color:lime">✓ Setup: First Candle OB → Second High Break (wick chalel) → Third se 50% Retrace pe ENTRY<br>✓ SL = OB cha Low | Risk = 50%-Low | TGT = 50% + 2*Risk (1:2)<br>✓ Auto BUY/SELL Aaj Pasun</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
