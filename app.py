from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect
app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)
FILE="/tmp/ob.json"
QTY=65
API_KEY=os.environ.get("ANGEL_API_KEY")
CLIENT_ID=os.environ.get("ANGEL_CLIENT_ID")
MPIN=os.environ.get("ANGEL_PASSWORD")
TOTP_SECRET=os.environ.get("ANGEL_TOTP_SECRET")
def load():
 try:
  with open(FILE,'r') as f: return json.load(f)
 except: return {"nifty":0,"atm":0,"action":"Start...","ob_50":0,"ob_low":0,"symbol":"","exp":"","time_str":""}
def save(d):
 with open(FILE,'w') as f: json.dump(d,f)
def get_tue():
 d=ist_now().date()
 o=(1-d.weekday())%7
 if o==0 and ist_now().hour>=15: o=7
 return d+timedelta(days=o)
def find_ob(c):
 for i in range(len(c)-5,1,-1):
  try:
   p=c[i]
   if p[4]>p[1]: return {"high":p[2],"low":p[3],"50":(p[2]+p[3])/2}
  except: continue
 return None
def run():
 try:
  smart=SmartConnect(api_key=API_KEY)
  smart.generateSession(CLIENT_ID, MPIN, pyotp.TOTP(TOTP_SECRET).now())
 except Exception as e:
  d=load(); d["action"]=f"LOGIN FAIL {e}"; save(d); return
 tok=None; trad=None; last_exp=None; last_h=0
 while True:
  try:
   now=ist_now(); d=load(); d["time_str"]=now.strftime("%H:%M:%S")
   exp=get_tue()
   if last_exp!=exp or not tok:
    try:
     ltp=smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
     atm=int(round(ltp/50)*50)
     d["nifty"]=ltp; d["atm"]=atm
     sym=f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE"
     s=smart.searchScrip("NFO", sym)
     if s and s.get('data'):
      tok=s['data'][0]['symboltoken']; trad=s['data'][0]['tradingsymbol']
      last_exp=exp; d["symbol"]=trad; d["exp"]=str(exp)
    except Exception as e:
     d["action"]=f"Token {e}"; save(d); time.sleep(90); continue
   if not tok: time.sleep(90); continue
   try:
    frm=(ist_now()-timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    to=ist_now().strftime("%Y-%m-%d %H:%M")
    res=smart.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":frm,"todate":to})
    data=res.get('data') if isinstance(res, dict) else []
   except Exception as e:
    if "Access denied" in str(e): d["action"]=f"Angel Block wait {now.strftime('%H:%M:%S')}"; save(d); time.sleep(180); continue
    d["action"]=f"Wait {e}"; save(d); time.sleep(90); continue
   if len(data)<10: time.sleep(90); continue
   ob=find_ob(data)
   if ob:
    d["ob_50"]=round(ob["50"],2); d["ob_low"]=round(ob["low"],2)
    if data[-2][2]>ob["high"] and ob["high"]!=last_h:
     lp=int(round(ob["50"]))
     try:
      smart.placeOrder({"variety":"NORMAL","tradingsymbol":trad,"symboltoken":tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":lp,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
      last_h=ob["high"]; d["action"]=f"PENDING DONE {trad} @ {lp}"
     except Exception as e: d["action"]=f"Order Fail {e}"
    else: d["action"]=f"OB milala 50% {d['ob_50']} SL {d['ob_low']}"
   else: d["action"]=f"OB shodhtoy ATM {d['atm']}"
   save(d); time.sleep(90)
  except Exception as e:
   d=load(); d["action"]=f"Err {e}"; save(d); time.sleep(90)
threading.Thread(target=run, daemon=True).start()
@app.route('/')
def home():
 d=load()
 return f"<html><head><meta http-equiv='refresh' content='10'></head><body style='background:#111;color:#fff;font-family:Arial;padding:15px'><h2 style='color:#00ff88'>NIFTY {d['nifty']} ATM {d['atm']}</h2><div style='border:1px solid #333;padding:10px;border-radius:10px'>{d['symbol']}<br>{d['exp']}<br>50% {d['ob_50']} SL {d['ob_low']}</div><h3 style='color:#ffeb3b'>{d['action']}</h3><p>{d['time_str']} | 90s Fix ON</p></body></html>"
if __name__ == '__main__':
 app.run(host='0.0.0.0', port=10000)
