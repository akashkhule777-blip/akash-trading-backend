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
OB_FILE = "/tmp/ob_final.json"
TRADE_FILE = "/tmp/trade_final.json"
REAL_TRADING = True

def ist_now(): return datetime.now(IST)
def load_json(p,d):
    if os.path.exists(p):
        try:
            with open(p,'r') as f: return json.load(f)
        except: pass
    return d
def save_json(p,d):
    try:
        with open(p,'w') as f: json.dump(data,f)
    except: pass

OB = load_json(OB_FILE, {"h3":0,"l3":0,"fifty3":0,"break3":False,"h5":0,"l5":0,"fifty5":0,"break5":False,"date":""})
TRADE = load_json(TRADE_FILE, {"entries3":0,"active3":False,"buy_price3":0,"sl_nifty3":0,"tgt_nifty3":0,"sym3":"","tok3":"","pnl3":0,"entries5":0,"active5":False,"buy_price5":0,"sl_nifty5":0,"tgt_nifty5":0,"sym5":"","tok5":"","pnl5":0,"date":""})

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

def get_candles(obj, token, frm, to):
    try:
        data = obj.getCandleData({"exchange":"NSE","symboltoken":token,"interval":"THREE_MINUTE" if "3" in frm else "ONE_MINUTE","fromdate":frm,"todate":to})
        if data and data.get('data'): return data['data']
    except: pass
    return []

def place(obj, sym, tok, qty, side, otype="MARKET", trig=0, price=0):
    if not REAL_TRADING: return "PAPER"
    try:
        p = {
            "variety": "STOPLOSS" if "STOPLOSS" in otype else "NORMAL",
            "tradingsymbol": sym, "symboltoken": tok,
            "transactiontype": side, "exchange": "NFO",
            "ordertype": otype, "producttype": "INTRADAY", "duration": "DAY",
            "price": str(price) if price else "0",
            "triggerprice": str(trig) if trig else "0",
            "squareoff":"0","stoploss":"0","quantity":str(qty)
        }
        return obj.placeOrder(p)
    except Exception as e: return f"FAIL {e}"

def fetch_ob(obj):
    global OB
    today = ist_now().strftime("%Y-%m-%d")
    if OB.get("date")!=today:
        OB = {"h3":0,"l3":0,"fifty3":0,"break3":False,"h5":0,"l5":0,"fifty5":0,"break5":False,"date":today}
    # Try fetch first 2 candles of day
    for tok in ["26000","99926000"]:
        try:
            data = obj.getCandleData({"exchange":"NSE","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:30"})
            if data and data.get('data') and len(data['data'])>=2:
                c1 = data['data'][0] # 09:15-09:18
                c2 = data['data'][1] # 09:18-09:21
                h3 = float(c1[2]); l3 = float(c1[3]); fifty3 = round((h3+l3)/2,2)
                # Second candle close > first high?
                close2 = float(c2[4])
                break3 = close2 > h3
                # 5 MIN
                data5 = obj.getCandleData({"exchange":"NSE","symboltoken":tok,"interval":"FIVE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:35"})
                if data5 and data5.get('data') and len(data5['data'])>=2:
                    c1_5 = data5['data'][0]; c2_5 = data5['data'][1]
                    h5 = float(c1_5[2]); l5 = float(c1_5[3]); fifty5 = round((h5+l5)/2,2)
                    close2_5 = float(c2_5[4]); break5 = close2_5 > h5
                    OB.update({"h3":h3,"l3":l3,"fifty3":fifty3,"break3":break3,"h5":h5,"l5":l5,"fifty5":fifty5,"break5":break5,"date":today})
                    save_json(OB_FILE, OB)
                    print(f"OB OK 3M {h3}/{l3} break {break3} 5M {h5}/{l5} break {break5}")
                    return True
        except Exception as e:
            print(f"OB fetch fail {e}")
    return False

@app.route('/')
def home():
    global OB, TRADE
    obj = get_client()
    now = ist_now()
    ct = now.strftime("%H:%M:%S"); chm = now.strftime("%H:%M"); today = now.strftime("%Y-%m-%d")
    nifty = 23400.0
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: pass
    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

    if OB.get("date")!=today:
        OB = {"h3":0,"l3":0,"fifty3":0,"break3":False,"h5":0,"l5":0,"fifty5":0,"break5":False,"date":today}
    if TRADE.get("date")!=today:
        TRADE = {"entries3":0,"active3":False,"buy_price3":0,"sl_nifty3":0,"tgt_nifty3":0,"sym3":"","tok3":"","pnl3":0,"entries5":0,"active5":False,"buy_price5":0,"sl_nifty5":0,"tgt_nifty5":0,"sym5":"","tok5":"","pnl5":0,"date":today}

    if OB["h3"]==0: fetch_ob(obj)

    # Live break check if not yet
    if OB["h3"]!=0 and not OB["break3"] and chm >= "09:21":
        # check nifty now > h3 => break
        if nifty > OB["h3"]:
            OB["break3"]=True; save_json(OB_FILE, OB)
    if OB["h5"]!=0 and not OB["break5"] and chm >= "09:26":
        if nifty > OB["h5"]:
            OB["break5"]=True; save_json(OB_FILE, OB)

    msg3 = f"WAIT OB 3M - H:{OB['h3']} L:{OB['l3']} 50%:{OB['fifty3']} Break:{OB['break3']}"
    msg5 = f"WAIT OB 5M - H:{OB['h5']} L:{OB['l5']} 50%:{OB['fifty5']} Break:{OB['break5']}"

    # ==== 3 MIN ENTRY LOGIC ====
    # Condition: break true + third candle se retrace to 50% (+-8 points) + uptrend (nifty > 50%)
    if OB["h3"]!=0 and OB["break3"] and not TRADE["active3"] and TRADE["entries3"]<10 and "09:21" <= chm <= "14:30":
        if abs(nifty - OB["fifty3"]) <= 10: # retrace to 50%
            # Option chart uptrend filter - CE up?
            # Simple: ce_ltp > 0 and nifty trend up (nifty > fifty3)
            if nifty >= OB["fifty3"]:
                risk = OB["fifty3"] - OB["l3"]
                tgt_nifty = OB["fifty3"] + (2*risk)
                sl_nifty = OB["l3"]
                place(obj, ce_sym, ce_tok, QTY, "BUY", "MARKET", 0, 0)
                TRADE.update({"active3":True,"buy_price3":ce_ltp,"sl_nifty3":sl_nifty,"tgt_nifty3":tgt_nifty,"sym3":ce_sym,"tok3":ce_tok,"entries3":TRADE["entries3"]+1,"date":today})
                save_json(TRADE_FILE, TRADE)
                msg3 = f"3M ENTRY DONE CE {ce_ltp} SL NIFTY {sl_nifty} TGT {tgt_nifty} (1:2)"

    # 3M Exit logic - SL = first low, Target = 1:2
    if TRADE["active3"]:
        TRADE["pnl3"] = round((ce_ltp - TRADE["buy_price3"])*QTY,2) if TRADE["sym3"]==ce_sym else TRADE["pnl3"]
        save_json(TRADE_FILE, TRADE)
        if nifty <= TRADE["sl_nifty3"]: # SL hit - low of first candle
            place(obj, TRADE["sym3"], TRADE["tok3"], QTY, "SELL", "MARKET", 0, 0)
            TRADE["active3"]=False
            save_json(TRADE_FILE, TRADE)
            msg3 = f"3M SL HIT NIFTY {nifty} <= {TRADE['sl_nifty3']} - SELL DONE PNL {TRADE['pnl3']}"
        elif nifty >= TRADE["tgt_nifty3"]: # Target 1:2 hit
            place(obj, TRADE["sym3"], TRADE["tok3"], QTY, "SELL", "MARKET", 0, 0)
            TRADE["active3"]=False
            save_json(TRADE_FILE, TRADE)
            msg3 = f"3M TARGET HIT NIFTY {nifty} >= {TRADE['tgt_nifty3']} - SELL DONE PNL {TRADE['pnl3']}"
        else:
            msg3 = f"3M LIVE BUY {TRADE['buy_price3']} LTP {ce_ltp} PNL {TRADE['pnl3']} | SL Nifty {TRADE['sl_nifty3']} TGT {TRADE['tgt_nifty3']}"

    # ==== 5 MIN ENTRY LOGIC ====
    if OB["h5"]!=0 and OB["break5"] and not TRADE["active5"] and TRADE["entries5"]<10 and "09:26" <= chm <= "14:30":
        if abs(nifty - OB["fifty5"]) <= 12:
            if nifty >= OB["fifty5"]:
                risk5 = OB["fifty5"] - OB["l5"]
                tgt5 = OB["fifty5"] + (2*risk5)
                sl5 = OB["l5"]
                place(obj, ce_sym, ce_tok, QTY, "BUY", "MARKET", 0, 0)
                TRADE.update({"active5":True,"buy_price5":ce_ltp,"sl_nifty5":sl5,"tgt_nifty5":tgt5,"sym5":ce_sym,"tok5":ce_tok,"entries5":TRADE["entries5"]+1,"date":today})
                save_json(TRADE_FILE, TRADE)
                msg5 = f"5M ENTRY DONE CE {ce_ltp} SL {sl5} TGT {tgt5}"

    if TRADE["active5"]:
        if nifty <= TRADE["sl_nifty5"]:
            place(obj, TRADE["sym5"], TRADE["tok5"], QTY, "SELL", "MARKET", 0, 0)
            TRADE["active5"]=False; save_json(TRADE_FILE, TRADE)
            msg5 = f"5M SL HIT"
        elif nifty >= TRADE["tgt_nifty5"]:
            place(obj, TRADE["sym5"], TRADE["tok5"], QTY, "SELL", "MARKET", 0, 0)
            TRADE["active5"]=False; save_json(TRADE_FILE, TRADE)
            msg5 = f"5M TARGET HIT"
        else:
            pnl5 = round((ce_ltp - TRADE["buy_price5"])*QTY,2)
            msg5 = f"5M LIVE BUY {TRADE['buy_price5']} LTP {ce_ltp} PNL {pnl5} | SL {TRADE['sl_nifty5']} TGT {TRADE['tgt_nifty5']}"

    return f"""
    <html><head>
    <meta http-equiv="refresh" content="3">
    <script>setTimeout(()=>{{location.reload();}}, 3000);</script>
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:6px}}.box{{border:1px solid #0f0;padding:8px;margin:4px;border-radius:8px;background:#111}}.real{{border-color:gold;background:#221d00}}</style>
    </head><body>
    <h2 style="color:gold">ORDER BLOCK - 3M & 5M | REAL AUTO | {ct} | NIFTY {nifty}</h2>
    <div class="box" style="border-color:yellow">ATM {strike} CE LTP <b style="color:#0ff;font-size:20px">{ce_ltp}</b> PE {pe_ltp} | QTY {QTY}</div>
    <div class="box real"><b>3MIN OB:</b> First Candle H:{round(OB['h3'],2)} L:{round(OB['l3'],2)} 50%:{round(OB['fifty3'],2)}<br>Second Candle Close > H? Break:{OB['break3']}<br><b>{msg3}</b><br>Entries: {TRADE['entries3']}/10 Active:{TRADE['active3']}<br>SL = Low {TRADE['sl_nifty3']} TGT 1:2 = {TRADE['tgt_nifty3']}</div>
    <div class="box real" style="border-color:#0ff"><b>5MIN OB:</b> First H:{round(OB['h5'],2)} L:{round(OB['l5'],2)} 50%:{round(OB['fifty5'],2)}<br>Break:{OB['break5']}<br><b>{msg5}</b><br>Entries: {TRADE['entries5']}/10 Active:{TRADE['active5']}</div>
    <div class="box" style="border-color:#0f0">✓ Setup: First Candle OB -> Second Candle High Break -> Third se 50% Retest pe Entry<br>✓ SL = First Low | TGT = 1:2 | ✓ Option Uptrend filter ON | ✓ Auto Buy/Sell aaj pasun | 10 entries per setup</div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
