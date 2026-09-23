from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect
app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def now(): return datetime.now(timezone.utc).astimezone(IST)
FILE="/tmp/ob.json"
QTY=65
A=os.environ.get("ANGEL_API_KEY")
C=os.environ.get("ANGEL_CLIENT_ID")
M=os.environ.get("ANGEL_PASSWORD")
T=os.environ.get("ANGEL_TOTP_SECRET")
def load():
 try:
  with open(FILE,'r') as f: return json.load(f)
 except: return {"nifty":0,"atm":0,"action":"Start","ob_50":0,"ob_low":0,"symbol":""}
def save(d):
 with open(FILE,'w') as f: json.dump(d,f)
def tue():
 d=now().date()
 o=(1-d.weekday())%7
 if o==0 and now().hour>=15: o=7
 return d+timedelta(days=o)
def ob_find(c):
 for i in range(len(c)-4,1,-1):
  p=c[i]; c1=c[i+1]; c2=c[i+2]
  if p[1]>p[4] and c1[4]>c1[1] and c2[4]>p[2]: return p[2],p[3]
 return None
def run():
 try:
  s=SmartConnect(api_key=A)
  s.generateSession(C,M,pyotp.TOTP(T).now())
 except: return
 tok=None; trad=None; le=None; lh=0
 while True:
  try:
   n=now()
   if n.hour<9 or (n.hour==9 and n.minute<15):
    d=load(); d["action"]=f"Market Band {n.strftime('%H:%M')}"; save(d); time.sleep(90); continue
   d=load(); ex=tue()
   if le!=ex or not tok:
    ltp=s.ltpData("NSE","NIFTY","26000")['data']['ltp']
    atm=int(round(ltp/50)*50)
    d["nifty"]=ltp; d["atm"]=atm
    sym=f"NIFTY{ex.strftime('%d%b%y').upper()}{atm}CE"
    r=s.searchScrip("NFO",sym)
    if r and r.get('data'): tok=r['data'][0]['symboltoken']; trad=r['data'][0]['tradingsymbol']; le=ex; d["symbol"]=trad
   if not tok: time.sleep(90); continue
   frm=(now()-timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
   to=now().strftime("%Y-%m-%d %H:%M")
   try:
    res=s.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":frm,"todate":to})
    data=res.get('data') if isinstance(res,dict) else []
   except:
    time.sleep(180); continue
   if len(data)<10: time.sleep(90); continue
   o=ob_find(data)
   if o:
    h,l=o; mid=(h+l)/2
    d["ob_50"]=round(mid,2); d["ob_low"]=round(l,2)
    if data[-2][2]>h and h!=lh:
     lp=int(mid)
     try:
      s.placeOrder({"variety":"NORMAL","tradingsymbol":trad,"symboltoken":tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":lp,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
      lh=h; d["action"]=f"PENDING DONE {trad} @ {lp}"
     except Exception as e: d["action"]=f"Fail {e}"
    else: d["action"]=f"OB OK ATM {d['atm']} 50% {mid:.1f} SL {l:.1f}"
   else: d["action"]=f"OB shodhtoy ATM {d['atm']}"
   save(d); time.sleep(90)
  except: time.sleep(90)
threading.Thread(target=run, daemon=True).start()
@app.route('/')
def home():
 d=load()
 return f"<h2>NIFTY {d['nifty']} ATM {d['atm']}</h2><h3>{d['action']}</h3><p>{d['symbol']} 50% {d['ob_50']} SL {d['ob_low']}</p><meta http-equiv='refresh' content='90'>"
if __name__=='__main__': app.run(host='0.0.0.0',port=10000)
