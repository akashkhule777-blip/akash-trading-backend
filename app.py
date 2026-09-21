from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)

FILE = "/tmp/ob_final.json"
QTY = 65

# तुझ्या Render फोटो प्रमाणे नाव
API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID")
MPIN = os.environ.get("ANGEL_PASSWORD")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET")

def load():
    if os.path.exists(FILE):
        try:
            with open(FILE,'r') as f: return json.load(f)
        except: pass
    return {"nifty":0,"atm":0,"action":"WAIT - Option 3min OB शोधतोय","ob_high":0,"ob_low":0,"ob_50":0,"type":"NONE","time_str":"","symbol":"","exp":""}

def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_next_tuesday():
    now = ist_now().date()
    days_ahead = 1 - now.weekday()
    if days_ahead < 0: days_ahead += 7
    if days_ahead==0 and ist_now().hour>=15 and ist_now().minute>30: days_ahead=7
    return now + timedelta(days=days_ahead)

def get_token(smart, symbol):
    try:
        res = smart.searchScrip("NFO", symbol)
        if res and res.get('data'):
            return res['data'][0]['symboltoken'], res['data'][0]['tradingsymbol']
    except: pass
    return None, None

def find_ob(candles):
    for i in range(len(candles)-4, 1, -1):
        prev=candles[i]; c1=candles[i+1]; c2=candles[i+2]
        if prev[4]<prev[1] and c1[4]>c1[1] and c2[4]>c2[1] and c2[2]>prev[2]:
            return {"high":prev[2],"low":prev[3],"50":(prev[2]+prev[3])/2,"type":"BULLISH"}
        if prev[4]>prev[1] and c1[4]<c1[1] and c2[4]<c2[1] and c2[3]<prev[3]:
            return {"high":prev[2],"low":prev[3],"50":(prev[2]+prev[3])/2,"type":"BEARISH"}
    return None

def run():
    smart=None
    try:
        smart=SmartConnect(api_key=API_KEY)
        smart.generateSession(CLIENT_ID, MPIN, pyotp.TOTP(TOTP_SECRET).now())
        print("Login OK")
    except Exception as e:
        print(f"Login Fail {e}")
        return

    entered=False
    while True:
        try:
            now=ist_now()
            d=load()
            d["time_str"]=now.strftime("%H:%M:%S")

            try:
                ltp = smart.ltpData("NSE","NIFTY","99926000")['data']['ltp']
            except Exception as e:
                if "exceeding" in str(e).lower():
                    d["action"]="Rate Limit - 1 मिनिट थांबलोय..."
                    save(d)
                    time.sleep(60)
                    continue
                time.sleep(10)
                continue

            atm = int(round(ltp/50)*50)
            d["nifty"]=ltp; d["atm"]=atm
            exp_date=get_next_tuesday()
            exp_str=exp_date.strftime("%d%b%y").upper()
            d["exp"]=str(exp_date)
            ce_sym=f"NIFTY{exp_str}{atm}CE"
            d["symbol"]=ce_sym

            ce_token, ce_trading = get_token(smart, ce_sym)
            if not ce_token:
                d["action"]=f"Token शोधतोय {ce_sym}"
                save(d); time.sleep(5); continue

            params={"exchange":"NFO","symboltoken":ce_token,"interval":"THREE_MINUTE","fromdate":(now-timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),"todate":now.strftime("%Y-%m-%d %H:%M")}
            candles=smart.getCandleData(params)
            if not candles or 'data' not in candles or len(candles['data'])<10:
                time.sleep(5); continue
            data_c=candles['data']

            ob=find_ob(data_c)
            if ob and not entered:
                d["ob_high"]=ob["high"]; d["ob_low"]=ob["low"]; d["ob_50"]=ob["50"]; d["type"]=ob["type"]
                second_break=data_c[-1][2] > data_c[-2][2]
                touch_50=data_c[-1][3] <= ob["50"] <= data_c[-1][2]
                if second_break and touch_50:
                    sl=ob["low"]; entry=ob["50"]; tgt=entry + (entry - sl)*2
                    d["action"]=f"REAL ENTRY {ce_trading} @ {entry:.1f} SL {sl:.1f} TGT {tgt:.1f} QTY {QTY}"
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trading,"symboltoken":ce_token,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":round(entry,1),"producttype":"INTRADAY","duration":"DAY","quantity":str(QTY)})
                        entered=True
                    except Exception as e: d["action"]+=f" Fail {e}"
                else:
                    d["action"]=f"WAIT - ATM AUTO {atm} OB {ob['type']} 50% {ob['50']:.1f} | 2ndBreak:{second_break}"
            else:
                d["action"]=f"OB शोधतोय ATM {atm} {ce_sym} Tuesday {exp_date}"
            save(d)

        except Exception as e:
            err_str = str(e).lower()
            d=load()
            if "exceeding" in err_str or "access denied" in err_str:
                d["action"]="Rate Limit आला - 1 मिनिट थांबलोय..."
                save(d)
                time.sleep(60)
            else:
                d["action"]=f"Err {e}"
                save(d)
                time.sleep(5)
        time.sleep(5)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"""
    <html><head>
    <meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body style="background:#0e0e0e;color:white;font-family:Arial;padding:10px;">
    <h2 style="color:#00ff88;">NIFTY {d['nifty']} | ATM AUTO {d['atm']} | {d['time_str']} IST</h2>
    <p>SYMBOL AUTO: {d['symbol']} | EXP: {d['exp']}</p>
    <p>OB {d['type']} | 50%: {d['ob_50']} | SL: {d['ob_low']} | QTY: 65 | 1:2</p>
    <h3 style="color:yellow;">{d['action']}</h3>
    <p style="color:#aaa;">Auto Refresh 3 Sec | ATM Auto | Rate Limit Fixed</p>
    </body></html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
