from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now():
    return datetime.now(timezone.utc).astimezone(IST)

FILE = "/tmp/ob.json"
QTY = 65

API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID")
MPIN = os.environ.get("ANGEL_PASSWORD")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET")

def load():
    if os.path.exists(FILE):
        try:
            with open(FILE,'r') as f:
                return json.load(f)
        except: pass
    return {"nifty":0,"atm":0,"action":"Starting...","ce_50":0,"ce_sl":0,"pe_50":0,"pe_sl":0,"ce_sym":"","pe_sym":"","exp":"","time_str":""}

def save(d):
    with open(FILE,'w') as f:
        json.dump(d,f)

def get_tue():
    d = ist_now().date()
    off = (1 - d.weekday()) % 7
    if off == 0 and ist_now().hour >= 15:
        off = 7
    return d + timedelta(days=off)

def find_ob(candles):
    try:
        if not candles or len(candles) < 15:
            return None
        # Tumcha box - shevatche 10 candle
        box = candles[-12:-2]
        h = max(float(x[2]) for x in box)
        l = min(float(x[3]) for x in box)
        return {"high": h, "low": l, "50": (h + l) / 2.0}
    except:
        return None

def get_candles(smart, token):
    try:
        frm = (ist_now() - timedelta(days=4)).strftime("%Y-%m-%d %H:%M")
        to = ist_now().strftime("%Y-%m-%d %H:%M")
        res = smart.getCandleData({
            "exchange": "NFO",
            "symboltoken": token,
            "interval": "THREE_MINUTE",
            "fromdate": frm,
            "todate": to
        })
        if isinstance(res, dict):
            data = res.get('data')
            if isinstance(data, list) and len(data) > 0:
                return data
        return []
    except Exception as e:
        print(f"Candle error {e}")
        return []

def run():
    try:
        smart = SmartConnect(api_key=API_KEY)
        smart.generateSession(CLIENT_ID, MPIN, pyotp.TOTP(TOTP_SECRET).now())
    except Exception as e:
        d = load()
        d["action"] = f"LOGIN FAIL {e}"
        save(d)
        return

    ce_tok = None
    pe_tok = None
    ce_trad = None
    pe_trad = None
    last_exp = None
    ce_h = 0
    pe_h = 0

    while True:
        try:
            now = ist_now()
            d = load()
            d["time_str"] = now.strftime("%H:%M:%S")
            exp = get_tue()
            d["exp"] = str(exp)

            # Token fakt ekdach shodhaycha
            if last_exp!= exp or not ce_tok:
                try:
                    ltp = smart.ltpData("NSE", "NIFTY", "26000")['data']['ltp']
                    atm = int(round(ltp / 50) * 50)
                    d["nifty"] = ltp
                    d["atm"] = atm

                    ce_name = f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE"
                    pe_name = f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}PE"

                    s1 = smart.searchScrip("NFO", ce_name)
                    time.sleep(2)
                    s2 = smart.searchScrip("NFO", pe_name)

                    if s1 and isinstance(s1, dict) and s1.get('data'):
                        ce_tok = str(s1['data'][0]['symboltoken'])
                        ce_trad = s1['data'][0]['tradingsymbol']
                        d["ce_sym"] = ce_trad
                    if s2 and isinstance(s2, dict) and s2.get('data'):
                        pe_tok = str(s2['data'][0]['symboltoken'])
                        pe_trad = s2['data'][0]['tradingsymbol']
                        d["pe_sym"] = pe_trad

                    last_exp = exp
                    d["action"] = f"Token OK ATM {atm}"
                    save(d)
                    time.sleep(10)
                except Exception as e:
                    if "Access denied" in str(e):
                        d["action"] = f"Angel Block 10 min wait {now.strftime('%H:%M:%S')}"
                        save(d)
                        time.sleep(600)
                        continue
                    d["action"] = f"Token wait {e}"
                    save(d)
                    time.sleep(60)
                    continue

            if not ce_tok or not pe_tok:
                time.sleep(60)
                continue

            ce_data = get_candles(smart, ce_tok)
            time.sleep(5)
            pe_data = get_candles(smart, pe_tok)

            if len(ce_data) == 0 or len(pe_data) == 0:
                if "Access denied" in str(ce_data):
                    d["action"] = f"Block 10 min {now.strftime('%H:%M:%S')}"
                    save(d)
                    time.sleep(600)
                    continue
                d["action"] = "Candle wait..."
                save(d)
                time.sleep(120)
                continue

            ce_ob = find_ob(ce_data)
            pe_ob = find_ob(pe_data)

            if ce_ob:
                d["ce_50"] = round(ce_ob["50"], 2)
                d["ce_sl"] = round(ce_ob["low"], 2)
            if pe_ob:
                d["pe_50"] = round(pe_ob["50"], 2)
                d["pe_sl"] = round(pe_ob["low"], 2)

            msgs = []
            # CE Trade
            if ce_ob and ce_data:
                try:
                    last_high = float(ce_data[-2][2])
                    if last_high > float(ce_ob["high"]) and float(ce_ob["high"])!= ce_h:
                        lp = int(round(ce_ob["50"]))
                        smart.placeOrder({
                            "variety": "NORMAL",
                            "tradingsymbol": ce_trad,
                            "symboltoken": ce_tok,
                            "transactiontype": "BUY",
                            "exchange": "NFO",
                            "ordertype": "LIMIT",
                            "price": lp,
                            "producttype": "INTRADAY",
                            "duration": "DAY",
                            "quantity": QTY
                        })
                        ce_h = float(ce_ob["high"])
                        msgs.append(f"CE BUY {lp} PENDING")
                    else:
                        msgs.append(f"CE OB {d['ce_50']} SL {d['ce_sl']}")
                except Exception as e:
                    msgs.append(f"CE Wait {e}")

            # PE Trade
            if pe_ob and pe_data:
                try:
                    last_high = float(pe_data[-2][2])
                    if last_high > float(pe_ob["high"]) and float(pe_ob["high"])!= pe_h:
                        lp = int(round(pe_ob["50"]))
                        smart.placeOrder({
                            "variety": "NORMAL",
                            "tradingsymbol": pe_trad,
                            "symboltoken": pe_tok,
                            "transactiontype": "BUY",
                            "exchange": "NFO",
                            "ordertype": "LIMIT",
                            "price": lp,
                            "producttype": "INTRADAY",
                            "duration": "DAY",
                            "quantity": QTY
                        })
                        pe_h = float(pe_ob["high"])
                        msgs.append(f"PE BUY {lp} PENDING")
                    else:
                        msgs.append(f"PE OB {d['pe_50']} SL {d['pe_sl']}")
                except Exception as e:
                    msgs.append(f"PE Wait {e}")

            d["action"] = " | ".join(msgs) if msgs else f"OB shodhtoy ATM {d['atm']}"
            save(d)
            time.sleep(240) # 4 min gap - Block yenar nahi

        except Exception as e:
            d = load()
            d["action"] = f"Loop Err {e}"
            save(d)
            time.sleep(300)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d = load()
    return f"""
    <html><head>
    <meta http-equiv='refresh' content='30'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <style>
        body{{background:#111;color:#fff;font-family:Arial;padding:12px}}
       .g{{color:#00ff88;font-size:22px}}
       .y{{color:#ffeb3b;font-size:15px}}
       .b{{border:1px solid #333;padding:10px;border-radius:10px;margin-bottom:8px;background:#1a1a1a}}
    </style>
    </head><body>
    <h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2>
    <div class=b>CE: {d['ce_sym']}<br>50% {d['ce_50']} SL {d['ce_sl']}</div>
    <div class=b>PE: {d['pe_sym']}<br>50% {d['pe_50']} SL {d['pe_sl']}</div>
    <div class=b>EXP: {d['exp']}</div>
    <h3 class=y>{d['action']}</h3>
    <p>{d['time_str']} | CE+PE Donhi ON | 4 min Gap Fix</p>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
