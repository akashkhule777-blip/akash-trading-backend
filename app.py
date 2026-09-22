from flask import Flask, jsonify
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)

FILE = "/tmp/ob_final.json"
QTY = 65

API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID")
MPIN = os.environ.get("ANGEL_PASSWORD")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET")

def load():
    if os.path.exists(FILE):
        try:
            with open(FILE,'r') as f: return json.load(f)
        except: pass
    return {"nifty":0,"atm":0,"action":"WAIT - OB Shodhtoy","ob_high":0,"ob_low":0,"ob_50":0,"type":"","symbol":"","exp":"","time_str":""}

def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_next_tuesday():
    now = ist_now().date()
    days_ahead = 1 - now.weekday()
    if days_ahead < 0: days_ahead += 7
    if days_ahead==0 and ist_now().hour>=15 and ist_now().minute>=30: days_ahead=7
    return now + timedelta(days=days_ahead)

def get_token(smart, symbol):
    try:
        res = smart.searchScrip("NFO", symbol)
        if res and res.get('data'):
            return res['data'][0]['symboltoken'], res['data'][0]['tradingsymbol']
    except: pass
    return None, None

def find_bullish_ob(candles):
    for i in range(len(candles)-4, 1, -1):
        prev=candles[i]; c1=candles[i+1]; c2=candles[i+2]
        try:
            if prev[1] > prev[4] and c1[4] > c1[1] and c2[4] > prev[2]:
                return {"high":prev[2],"low":prev[3],"50":(prev[2]+prev[3])/2,"type":"BULLISH"}
        except: continue
    return None

def run():
    try:
        smart=SmartConnect(api_key=API_KEY)
        smart.generateSession(CLIENT_ID, MPIN, pyotp.TOTP(TOTP_SECRET).now())
        print("Login OK - Real Trading Ready")
    except Exception as e:
        print(f"Login Fail {e}"); return

    last_ce_high = 0
    last_pe_high = 0

    while True:
        try:
            now=ist_now()
            d=load()
            d["time_str"]=now.strftime("%H:%M:%S")

            try:
                ltp = smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
            except Exception as e:
                if "exceeding" in str(e).lower():
                    d["action"]="Rate Limit 60s Wait..."; save(d); time.sleep(60); continue
                time.sleep(5); continue

            atm = int(round(ltp/50)*50)
            d["nifty"]=ltp; d["atm"]=atm
            exp_date=get_next_tuesday()
            exp_str=exp_date.strftime("%d%b%y").upper()
            d["exp"]=str(exp_date)

            ce_sym=f"NIFTY{exp_str}{atm}CE"
            pe_sym=f"NIFTY{exp_str}{atm}PE"
            ce_tok, ce_trad = get_token(smart, ce_sym)
            pe_tok, pe_trad = get_token(smart, pe_sym)
            if not ce_tok or not pe_tok:
                d["action"]=f"Token Wait ATM {atm}"; save(d); time.sleep(5); continue

            fromdate=(ist_now()-timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
            todate=ist_now().strftime("%Y-%m-%d %H:%M")

            try:
                ce_res=smart.getCandleData({"exchange":"NFO","symboltoken":ce_tok,"interval":"THREE_MINUTE","fromdate":fromdate,"todate":todate})
                pe_res=smart.getCandleData({"exchange":"NFO","symboltoken":pe_tok,"interval":"THREE_MINUTE","fromdate":fromdate,"todate":todate})
                ce_data=ce_res['data'] if ce_res and 'data' in ce_res else []
                pe_data=pe_res['data'] if pe_res and 'data' in pe_res else []
                if len(ce_data)<10 or len(pe_data)<10: time.sleep(5); continue
            except: time.sleep(5); continue

            ce_ob=find_bullish_ob(ce_data)
            pe_ob=find_bullish_ob(pe_data)

            # CE BULLISH SETUP
            if ce_ob and ce_ob["high"]!=last_ce_high:
                brk = ce_data[-2][2] > ce_ob["high"]
                tch = ce_data[-1][3] <= ce_ob["50"] <= ce_data[-1][2]
                d["symbol"]=ce_trad; d["ob_high"]=ce_ob["high"]; d["ob_low"]=ce_ob["low"]; d["ob_50"]=ce_ob["50"]; d["type"]=f"CE BULLISH ATM {atm}"
                d["action"]=f"CE WAIT ATM {atm} 50% {ce_ob['50']:.1f} Break:{brk} Touch:{tch}"
                if brk and tch:
                    sl=ce_ob["low"]; tgt=ce_ob["50"]+abs(ce_ob["50"]-sl)*2
                    d["action"]=f"REAL CE BUY {ce_trad} SL {sl:.1f} TGT {tgt:.1f} QTY 65"; save(d)
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"CARRYFORWARD","duration":"DAY","quantity":QTY})
                        time.sleep(1)
                        smart.placeOrder({"variety":"STOPLOSS","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT","price":str(int(sl)),"triggerprice":str(int(sl)),"producttype":"CARRYFORWARD","duration":"DAY","quantity":QTY})
                        time.sleep(1)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"LIMIT","price":str(int(tgt)),"producttype":"CARRYFORWARD","duration":"DAY","quantity":QTY})
                        last_ce_high=ce_ob["high"]; d["action"]=f"DONE CE {ce_trad} REAL 65 | NEXT OB"
                    except Exception as e: d["action"]=f"CE Fail {e}"

            # PE BULLISH SETUP
            if pe_ob and pe_ob["high"]!=last_pe_high:
                brk = pe_data[-2][2] > pe_ob["high"]
                tch = pe_data[-1][3] <= pe_ob["50"] <= pe_data[-1][2]
                if brk and tch:
                    sl=pe_ob["low"]; tgt=pe_ob["50"]+abs(pe_ob["50"]-sl)*2
                    d["action"]=f"REAL PE BUY {pe_trad} SL {sl:.1f} TGT {tgt:.1f} QTY 65"; save(d)
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"CARRYFORWARD","duration":"DAY","quantity":QTY})
                        time.sleep(1)
                        smart.placeOrder({"variety":"STOPLOSS","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT","price":str(int(sl)),"triggerprice":str(int(sl)),"producttype":"CARRYFORWARD","duration":"DAY","quantity":QTY})
                        time.sleep(1)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"LIMIT","price":str(int(tgt)),"producttype":"CARRYFORWARD","duration":"DAY","quantity":QTY})
                        last_pe_high=pe_ob["high"]; d["action"]=f"DONE PE {pe_trad} REAL 65 | NEXT OB"
                    except Exception as e: d["action"]=f"PE Fail {e}"

            save(d); time.sleep(5)
        except Exception as e:
            d=load(); d["action"]=f"Err {e}"; save(d); time.sleep(5)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"""
    <html><head><meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{background:#0e0e0e;color:#fff;font-family:Arial;padding:12px}}.g{{color:#00ff88}}.y{{color:#ffeb3b}}.b{{border:1px solid #333;padding:10px;border-radius:10px}}</style>
    </head><body>
    <h2 class="g">NIFTY {d['nifty']} | ATM AUTO {d['atm']} | {d['time_str']} IST</h2>
    <div class="b">SYMBOL: {d['symbol']} | EXP: {d['exp']}<br>{d['type']} | 50%: {d['ob_50']} | SL: {d['ob_low']} | QTY 65 RR 1:2</div>
    <h3 class="y">{d['action']}</h3>
    <p style="color:#888">ATM Auto 5 Sec | Page Refresh 3 Sec | CE+PE Bullish OB | Multiple Entry | Real Angel Order</p>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
