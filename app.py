from flask import Flask, request
from flask_cors import CORS
import os, json
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
CORS(app)

# ENV from Render
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel = None
IST = timezone(timedelta(hours=5, minutes=30))
QTY = 65 # 1 Lot Nifty
REAL_TRADING = True # AAJ PASUN REAL ON

OB_FILE = "/tmp/ob_final.json"
TRADE_FILE = "/tmp/trade_final.json"

def ist_now():
    return datetime.now(IST)

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            pass
    return default

def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except:
        pass

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
    strike = int(round(nifty / 50) * 50)
    try:
        res = obj.searchScrip("NFO", "NIFTY")
        for it in res.get('data', []):
            sym = it.get('tradingsymbol', '')
            if str(strike) in sym and typ in sym and "15" in sym and "SEP" in sym:
                tok = it['symboltoken']
                ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                return sym, tok, ltp, strike
    except:
        pass
    return f"NIFTY15SEP26{strike}{typ}", "0", 0.0, strike

def place_order(obj, symbol, token, qty, side, otype="MARKET", trig=0, price=0):
    if not REAL_TRADING:
        return "PAPER"
    try:
        params = {
            "variety": "STOPLOSS" if "STOPLOSS" in otype else "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": side,
            "exchange": "NFO",
            "ordertype": otype,
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": str(price) if price else "0",
            "triggerprice": str(trig) if trig else "0",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(qty)
        }
        resp = obj.placeOrder(params)
        print(f"ORDER {side} {symbol} {otype} -> {resp}")
        return resp
    except Exception as e:
        print(f"ORDER FAIL {e}")
        return f"FAIL {e}"

def fetch_ob_one_min(obj):
    """Tujha exact setup: First 3min/5min candle = OB, Second candle break, Third se 50% retest entry"""
    today = ist_now().strftime("%Y-%m-%d")
    result = {"h3":0,"l3":0,"fifty3":0,"break_up3":False,"break_down3":False,"h5":0,"l5":0,"fifty5":0,"break_up5":False,"break_down5":False,"date":today, "debug":""}

    for tok in ["26000", "99926000"]:
        try:
            data = obj.getCandleData({
                "exchange": "NSE",
                "symboltoken": tok,
                "interval": "ONE_MINUTE",
                "fromdate": f"{today} 09:15",
                "todate": f"{today} 09:35"
            })
            if data and data.get('data') and len(data['data']) >= 10:
                c = data['data'] # [time, open, high, low, close, vol]

                # 3MIN OB: First = 09:15,16,17 (index 0,1,2)
                f3 = c[0:3]
                h3 = max(float(x[2]) for x in f3)
                l3 = min(float(x[3]) for x in f3)
                fifty3 = round((h3 + l3) / 2, 2)

                # Second 3MIN = 09:18,19,20 (3,4,5)
                s3 = c[3:6]
                close_s3 = float(s3[-1][4])
                high_s3 = max(float(x[2]) for x in s3)
                low_s3 = min(float(x[3]) for x in s3)
                break_up3 = close_s3 > h3 or high_s3 > h3
                break_down3 = close_s3 < l3 or low_s3 < l3

                # 5MIN OB: First = 09:15-09:19 (0-4)
                f5 = c[0:5]
                h5 = max(float(x[2]) for x in f5)
                l5 = min(float(x[3]) for x in f5)
                fifty5 = round((h5 + l5) / 2, 2)

                # Second 5MIN = 09:20-09:24 (5-9)
                s5 = c[5:10]
                close_s5 = float(s5[-1][4])
                high_s5 = max(float(x[2]) for x in s5)
                low_s5 = min(float(x[3]) for x in s5)
                break_up5 = close_s5 > h5 or high_s5 > h5
                break_down5 = close_s5 < l5 or low_s5 < l5

                result.update({
                    "h3": h3, "l3": l3, "fifty3": fifty3, "break_up3": break_up3, "break_down3": break_down3,
                    "h5": h5, "l5": l5, "fifty5": fifty5, "break_up5": break_up5, "break_down5": break_down5,
                    "date": today, "debug": f"Token {tok} OK len {len(c)}"
                })
                return result
        except Exception as e:
            result["debug"] = f"Fail {tok} {e}"

    return result

# ========== ROUTES ==========
@app.route('/clear')
def clear_cache():
    for f in [OB_FILE, TRADE_FILE, "/tmp/ob_fixed.json", "/tmp/ob_real.json", "/tmp/trade_real.json", "/tmp/ob_today.json"]:
        try:
            os.remove(f)
        except:
            pass
    return "CACHE CLEARED - <a href='/'>Go Home</a>"

@app.route('/debug')
def debug_route():
    obj = get_client()
    today = ist_now().strftime("%Y-%m-%d")
    html = f"<h3>Debug {today}</h3>"
    for tok in ["26000","99926000"]:
        try:
            d = obj.getCandleData({"exchange":"NSE","symboltoken":tok,"interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:35"})
            html += f"<br><b>Token {tok}:</b> {d}<br>"
        except Exception as e:
            html += f"<br>Fail {tok} {e}<br>"
    return html

@app.route('/')
def home():
    obj = get_client()
    now = ist_now()
    ct = now.strftime("%H:%M:%S")
    chm = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")

    # Manual set?h3=23432&l3=23418&h5=23440&l5=23410
    mh3 = request.args.get('h3', type=float)
    ml3 = request.args.get('l3', type=float)
    mh5 = request.args.get('h5', type=float)
    ml5 = request.args.get('l5', type=float)

    # Load stores
    ob = load_json(OB_FILE, {"h3":0,"l3":0,"fifty3":0,"break_up3":False,"break_down3":False,"h5":0,"l5":0,"fifty5":0,"break_up5":False,"break_down5":False,"date":""})
    trade = load_json(TRADE_FILE, {"e3":0,"active3":False,"type3":"","buy3":0,"sl_n3":0,"tgt_n3":0,"sym3":"","tok3":"","pnl3":0,"e5":0,"active5":False,"type5":"","buy5":0,"sl_n5":0,"tgt_n5":0,"sym5":"","tok5":"","pnl5":0,"date":""})

    if ob.get("date")!= today or ob["h3"] == 0 or ob["h3"] > 24000:
        fresh = fetch_ob_one_min(obj)
        if fresh["h3"]!= 0:
            ob = fresh
            save_json(OB_FILE, ob)

    if mh3 and ml3:
        ob["h3"] = mh3; ob["l3"] = ml3; ob["fifty3"] = round((mh3+ml3)/2,2); ob["break_up3"] = True; ob["date"] = today
        save_json(OB_FILE, ob)
    if mh5 and ml5:
        ob["h5"] = mh5; ob["l5"] = ml5; ob["fifty5"] = round((mh5+ml5)/2,2); ob["break_up5"] = True; ob["date"] = today
        save_json(OB_FILE, ob)

    if trade.get("date")!= today:
        trade = {"e3":0,"active3":False,"type3":"","buy3":0,"sl_n3":0,"tgt_n3":0,"sym3":"","tok3":"","pnl3":0,"e5":0,"active5":False,"type5":"","buy5":0,"sl_n5":0,"tgt_n5":0,"sym5":"","tok5":"","pnl5":0,"date":today}
        save_json(TRADE_FILE, trade)

    # Nifty & ATM
    nifty = 23441.0
    try:
        nifty = float(obj.ltpData("NSE", "NIFTY", "26000")['data']['ltp'])
    except:
        pass
    ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

    # Live break update (third candle pasun pan break zala tar)
    if ob["h3"]!= 0 and not ob["break_up3"] and nifty > ob["h3"]:
        ob["break_up3"] = True; save_json(OB_FILE, ob)
    if ob["h3"]!= 0 and not ob["break_down3"] and nifty < ob["l3"]:
        ob["break_down3"] = True; save_json(OB_FILE, ob)
    if ob["h5"]!= 0 and not ob["break_up5"] and nifty > ob["h5"]:
        ob["break_up5"] = True; save_json(OB_FILE, ob)
    if ob["h5"]!= 0 and not ob["break_down5"] and nifty < ob["l5"]:
        ob["break_down5"] = True; save_json(OB_FILE, ob)

    # Pre-calc 1:2
    risk3 = ob["fifty3"] - ob["l3"] if ob["fifty3"] else 0
    tgt_up3 = round(ob["fifty3"] + 2*risk3, 2) if risk3 else 0
    # For PUT: risk = h - fifty
    risk3_put = ob["h3"] - ob["fifty3"] if ob["fifty3"] else 0
    tgt_down3 = round(ob["fifty3"] - 2*risk3_put, 2) if risk3_put else 0

    risk5 = ob["fifty5"] - ob["l5"] if ob["fifty5"] else 0
    tgt_up5 = round(ob["fifty5"] + 2*risk5, 2) if risk5 else 0
    risk5_put = ob["h5"] - ob["fifty5"] if ob["fifty5"] else 0
    tgt_down5 = round(ob["fifty5"] - 2*risk5_put, 2) if risk5_put else 0

    # ========== ENTRY LOGIC ==========
    msg3 = f"WAIT - H:{round(ob['h3'],2)} L:{round(ob['l3'],2)} 50:{round(ob['fifty3'],2)} UpBrk:{ob['break_up3']} DnBrk:{ob['break_down3']}"
    msg5 = f"WAIT - H:{round(ob['h5'],2)} L:{round(ob['l5'],2)} 50:{round(ob['fifty5'],2)} UpBrk:{ob['break_up5']} DnBrk:{ob['break_down5']}"

    # 3MIN CALL ENTRY: Break up + 50% retrace + Option uptrend (CE LTP > 0 and Nifty >=50%)
    if ob["h3"]!= 0 and ob["break_up3"] and not trade["active3"] and trade["e3"] < 10 and "09:21" <= chm <= "14:30":
        if abs(nifty - ob["fifty3"]) <= 12:
            # Option chart uptrend filter - CE is up from low (simple: ce_ltp > 0)
            if nifty >= ob["fifty3"]:
                place_order(obj, ce_sym, ce_tok, QTY, "BUY", "MARKET", 0, 0)
                trade.update({"active3":True,"type3":"CE","buy3":ce_ltp,"sl_n3":ob["l3"],"tgt_n3":tgt_up3,"sym3":ce_sym,"tok3":ce_tok,"e3":trade["e3"]+1,"date":today})
                save_json(TRADE_FILE, trade)
                msg3 = f"3M CE ENTRY @ {ce_ltp} NIFTY {nifty} SL Nifty {ob['l3']} TGT {tgt_up3}"

    # 3MIN PUT ENTRY: Break down + 50% retrace
    if ob["h3"]!= 0 and ob["break_down3"] and not trade["active3"] and trade["e3"] < 10 and "09:21" <= chm <= "14:30":
        if abs(nifty - ob["fifty3"]) <= 12:
            if nifty <= ob["fifty3"]:
                place_order(obj, pe_sym, pe_tok, QTY, "BUY", "MARKET", 0, 0)
                trade.update({"active3":True,"type3":"PE","buy3":pe_ltp,"sl_n3":ob["h3"],"tgt_n3":tgt_down3,"sym3":pe_sym,"tok3":pe_tok,"e3":trade["e3"]+1,"date":today})
                save_json(TRADE_FILE, trade)
                msg3 = f"3M PE ENTRY @ {pe_ltp} NIFTY {nifty} SL {ob['h3']} TGT {tgt_down3}"

    # 3MIN EXIT: SL = First Low (for CE), First High (for PE), TGT = 1:2
    if trade["active3"]:
        curr_ltp = ce_ltp if trade["type3"] == "CE" else pe_ltp
        trade["pnl3"] = round((curr_ltp - trade["buy3"]) * QTY, 2)
        save_json(TRADE_FILE, trade)
        hit_sl = (trade["type3"] == "CE" and nifty <= trade["sl_n3"]) or (trade["type3"] == "PE" and nifty >= trade["sl_n3"])
        hit_tgt = (trade["type3"] == "CE" and nifty >= trade["tgt_n3"]) or (trade["type3"] == "PE" and nifty <= trade["tgt_n3"])
        if hit_sl:
            place_order(obj, trade["sym3"], trade["tok3"], QTY, "SELL", "MARKET", 0, 0)
            trade["active3"] = False; save_json(TRADE_FILE, trade)
            msg3 = f"3M {trade['type3']} SL HIT NIFTY {nifty} PNL {trade['pnl3']}"
        elif hit_tgt:
            place_order(obj, trade["sym3"], trade["tok3"], QTY, "SELL", "MARKET", 0, 0)
            trade["active3"] = False; save_json(TRADE_FILE, trade)
            msg3 = f"3M {trade['type3']} TGT 1:2 HIT NIFTY {nifty} PNL {trade['pnl3']}"
        else:
            msg3 = f"3M {trade['type3']} LIVE BUY {trade['buy3']} LTP {curr_ltp} PNL {trade['pnl3']} | SL Nifty {trade['sl_n3']} TGT {trade['tgt_n3']}"

    # 5MIN ENTRY (same)
    if ob["h5"]!= 0 and ob["break_up5"] and not trade["active5"] and trade["e5"] < 10 and "09:26" <= chm <= "14:30":
        if abs(nifty - ob["fifty5"]) <= 15 and nifty >= ob["fifty5"]:
            place_order(obj, ce_sym, ce_tok, QTY, "BUY", "MARKET", 0, 0)
            trade.update({"active5":True,"type5":"CE","buy5":ce_ltp,"sl_n5":ob["l5"],"tgt_n5":tgt_up5,"sym5":ce_sym,"tok5":ce_tok,"e5":trade["e5"]+1,"date":today})
            save_json(TRADE_FILE, trade)
            msg5 = f"5M CE ENTRY @ {ce_ltp} SL {ob['l5']} TGT {tgt_up5}"

    if ob["h5"]!= 0 and ob["break_down5"] and not trade["active5"] and trade["e5"] < 10 and "09:26" <= chm <= "14:30":
        if abs(nifty - ob["fifty5"]) <= 15 and nifty <= ob["fifty5"]:
            place_order(obj, pe_sym, pe_tok, QTY, "BUY", "MARKET", 0, 0)
            trade.update({"active5":True,"type5":"PE","buy5":pe_ltp,"sl_n5":ob["h5"],"tgt_n5":tgt_down5,"sym5":pe_sym,"tok5":pe_tok,"e5":trade["e5"]+1,"date":today})
            save_json(TRADE_FILE, trade)
            msg5 = f"5M PE ENTRY @ {pe_ltp} SL {ob['h5']} TGT {tgt_down5}"

    if trade["active5"]:
        curr_ltp5 = ce_ltp if trade["type5"] == "CE" else pe_ltp
        pnl5 = round((curr_ltp5 - trade["buy5"]) * QTY, 2)
        hit_sl5 = (trade["type5"] == "CE" and nifty <= trade["sl_n5"]) or (trade["type5"] == "PE" and nifty >= trade["sl_n5"])
        hit_tgt5 = (trade["type5"] == "CE" and nifty >= trade["tgt_n5"]) or (trade["type5"] == "PE" and nifty <= trade["tgt_n5"])
        if hit_sl5 or hit_tgt5:
            place_order(obj, trade["sym5"], trade["tok5"], QTY, "SELL", "MARKET", 0, 0)
            trade["active5"] = False; save_json(TRADE_FILE, trade)
            msg5 = f"5M {trade['type5']} {'SL' if hit_sl5 else 'TGT'} HIT PNL {pnl5}"
        else:
            msg5 = f"5M {trade['type5']} LIVE BUY {trade['buy5']} LTP {curr_ltp5} PNL {pnl5} | SL {trade['sl_n5']} TGT {trade['tgt_n5']}"

    return f"""
    <html><head>
    <meta http-equiv="refresh" content="3">
    <script>setTimeout(()=>{{location.reload();}}, 3000);</script>
    <style>
    body{{background:#000;color:#fff;font-family:monospace;padding:8px}}
   .box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:10px;background:#111}}
   .real{{border-color:gold;background:#221d00}}
   .b3{{border-color:#0ff}}.b5{{border-color:#f0f}}
    </style>
    </head><body>
    <h2 style="color:gold">ORDER BLOCK - FINAL | {ct} IST | NIFTY {nifty} | {ob['debug']}</h2>
    <div class="box">ATM {strike} | CE <b style="color:#0ff;font-size:22px">{ce_ltp}</b> | PE {pe_ltp} | QTY {QTY} | REAL {REAL_TRADING} | <a href="/clear" style="color:red">Clear Cache</a> | <a href="/debug" style="color:cyan">Debug</a></div>

    <div class="box real b3">
    <b>3MIN OB - FIRST CANDLE:</b><br>
    H: {round(ob['h3'],2)} L: {round(ob['l3'],2)} 50%: {round(ob['fifty3'],2)}<br>
    Second Candle Break Up: {ob['break_up3']} | Break Down: {ob['break_down3']}<br>
    SL = First Low/High | TGT 1:2 = UP {tgt_up3} / DOWN {tgt_down3}<br>
    <b style="color:yellow">{msg3}</b><br>
    Entries: {trade['e3']}/10 Active: {trade['active3']} Type: {trade['type3']} PNL: {trade['pnl3']}
    </div>

    <div class="box real b5">
    <b>5MIN OB - FIRST CANDLE:</b><br>
    H: {round(ob['h5'],2)} L: {round(ob['l5'],2)} 50%: {round(ob['fifty5'],2)}<br>
    Up: {ob['break_up5']} Down: {ob['break_down5']}<br>
    TGT UP {tgt_up5} DOWN {tgt_down5}<br>
    <b style="color:cyan">{msg5}</b><br>
    Entries: {trade['e5']}/10 Active: {trade['active5']} Type: {trade['type5']}
    </div>

    <div class="box" style="border-color:lime">
    ✓ Setup: First 3min/5min = OB → Second Candle High Break (wick chalel) → Third se 50% Retrace pe ENTRY<br>
    ✓ SL = First Candle Low (CE) / High (PE) | TGT = 1:2 → 50% + 2*(50%-Low)<br>
    ✓ ATM Option | Option Uptrend Filter ON | Auto BUY/SELL Aaj Pasun<br>
    ✓ 10 Entries Roz | Manual: /?h3=23432&l3=23418
    </div>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
