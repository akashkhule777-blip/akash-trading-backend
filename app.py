from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT=65
state={"ist":"","ltp":0,"c3":"Wait OB","call3":"Scanning...","put3":"Scanning...","atm":"Wait","cnt3":0,"msg":"DIRECT API FIX"}
smart=None
jwt_token=None
api_key=os.getenv("ANGEL_API_KEY")

try:
 smart=SmartConnect(api_key=api_key)
 data=smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now())
 jwt_token=data['data']['jwtToken']
 state["msg"]=f"Login OK - Direct Quote ON"
except Exception as e:
 state["msg"]=f"Login Fail {e}"

def get_spot_direct():
 global jwt_token
 # METHOD 1: Direct Angel Quote API - Most Reliable
 try:
  if jwt_token:
   headers={"Authorization": f"Bearer {jwt_token}","Content-Type":"application/json","Accept":"application/json","X-UserType":"USER","X-SourceID":"WEB","X-ClientLocalIP":"127.0.0.1","X-ClientPublicIP":"127.0.0.1","X-MACAddress":"00:00:00:00:00:00","X-PrivateKey": api_key}
   body={"mode":"LTP","exchangeTokens":{"NSE":["99926000","26000","99926009"]}}
   r=requests.post("https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/",headers=headers,json=body,timeout=5)
   if r.status_code==200:
    js=r.json()
    # log
    state["msg"]=f"Quote API {str(js)[:150]}"
    if js.get('data'):
     fetched=js['data'].get('fetched',[]) or js['data'].get('unfetched',[])
     for item in js['data'].get('fetched',[]):
      if item.get('symbolToken') in ['99926000','26000']:
       ltp=item.get('ltp',0)
       if ltp>1000:
        return float(ltp)
   else:
    state["msg"]=f"Quote API Fail {r.status_code} {r.text[:100]}"
 except Exception as e:
  state["msg"]=f"Direct Err {e}"

 # METHOD 2: Angel ltpData
 try:
  if smart:
   d=smart.ltpData("NSE","Nifty 50","99926000")
   if d and d.get('data') and d['data'].get('ltp'):
    lv=float(d['data']['ltp'])
    if lv>1000:
     return lv
 except: pass

 # METHOD 3: Angel Candle
 try:
  if smart:
   ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
   fromdate=ist.strftime("%Y-%m-%d 09:15")
   todate=ist.strftime("%Y-%m-%d %H:%M")
   params={"exchange":"NSE","symboltoken":"99926000","interval":"ONE_MINUTE","fromdate":fromdate,"todate":todate}
   data=smart.getCandleData(params)
   if data and data.get('data') and len(data['data'])>0:
    return float(data['data'][-1][4])
 except: pass

 return 0

def get_atm_details(spot):
 try:
  sess=requests.Session()
  sess.headers.update({"User-Agent":"Mozilla/5.0"})
  sess.get("https://www.nseindia.com",timeout=3)
  r=sess.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",timeout=5)
  if r.status_code==200:
   js=r.json()
   strike=int(round(spot/50)*50)
   exp=js['records']['expiryDates'][0]
   ce=pe=0
   for i in js['records']['data']:
    if i.get('strikePrice')==strike and i.get('expiryDate')==exp:
     ce=i.get('CE',{}).get('lastPrice',0); pe=i.get('PE',{}).get('lastPrice',0); break
   state["atm"]=f"ATM {strike} {exp} CE:{ce} PE:{pe}"
   return ce,pe,strike,exp
 except: pass
 return 0,0,int(round(spot/50)*50) if spot>0 else 0,""

def place_angel_order(strike,opt_type,qty=65):
 try:
  if not smart: return None
  res=smart.searchScrip("NFO", f"{strike}{opt_type}")
  token=tsym=None
  if res and 'data' in res:
   for item in res['data']:
    if str(strike) in item['tradingsymbol'] and opt_type in item['tradingsymbol'] and 'NIFTY' in item['tradingsymbol']:
     token=item['token']; tsym=item['tradingsymbol']; break
  if not token: return None
  orderparams={"variety":"NORMAL","tradingsymbol":tsym,"symboltoken":token,"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":qty}
  oid=smart.placeOrder(orderparams)
  state["msg"]=f"ORDER OK {tsym} ID:{oid}"
  return oid
 except Exception as e:
  state["msg"]=f"ORDER FAIL {e}"; return None

def ema(arr,p=20):
 if len(arr)<p: return None
 k=2/(p+1); e=arr[0]
 for x in arr[1:]: e=x*k+e*(1-k)
 return e

live3=None; first3=None; phase3=0; b3up=False; b3dn=False
spot3_q=deque(maxlen=30); ce_q=deque(maxlen=30); pe_q=deque(maxlen=30)

def worker():
 global live3, first3, phase3, b3up, b3dn
 while True:
  try:
   ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
   state["ist"]=ist.strftime("%H:%M:%S IST")
   spot=get_spot_direct()
   if spot>1000:
    state["ltp"]=spot
   else:
    time.sleep(2); continue
   ce_ltp,pe_ltp,strike,exp=get_atm_details(spot)
   if ce_ltp>0: ce_q.append(ce_ltp)
   if pe_ltp>0: pe_q.append(pe_ltp)
   mod=ist.hour*60+ist.minute
   s3=(mod//3)*3
   if live3 is None or live3[4]!=s3:
    if live3 is not None:
     spot3_q.append(live3[3])
     if phase3==0:
      first3=live3; phase3=1
      state["c3"]=f"3MIN 1st H:{first3[1]:.0f} L:{first3[2]:.0f} 50%={int(first3[2]+(first3[1]-first3[2])*0.5)}"
     elif phase3==1:
      sec=live3
      if sec[1]>first3[1] or sec[3]>first3[1]:
       b3up=True; b3dn=False; phase3=2; state["call3"]=f"BREAK UP {sec[1]:.0f}>{first3[1]:.0f} | 50% wait"
      elif sec[2]<first3[2] or sec[3]<first3[2]:
       b3dn=True; b3up=False; phase3=2; state["put3"]=f"BREAK DN {sec[2]:.0f}<{first3[2]:.0f} | 50% wait"
      else: first3=sec
    live3=[spot,spot,spot,spot,s3]
   else:
    live3[1]=max(live3[1],spot); live3[2]=min(live3[2],spot); live3[3]=spot
   if phase3==2 and first3:
    fifty=int(first3[2]+(first3[1]-first3[2])*0.5)
    if abs(spot-fifty)<=15:
     _,ce,pe,strike,exp=get_atm_details(spot)
     ema3=ema(list(spot3_q),20); ce_ema=ema(list(ce_q),20); pe_ema=ema(list(pe_q),20)
     if b3up and (ema3 is None or spot>ema3) and (ce_ema is None or ce>ce_ema):
      state["cnt3"]+=1; sl=first3[2]; tgt=fifty+(fifty-sl)*2
      oid=place_angel_order(strike,"CE",LOT)
      state["call3"]=f"#{state['cnt3']} CALL BOUGHT! 50%={fifty} {strike}CE {ce} SL {sl:.0f} TGT {int(tgt)} ID:{oid}"
      phase3=0; first3=None; b3up=False; b3dn=False
     elif b3dn and (pe_ema is None or pe>pe_ema):
      state["cnt3"]+=1; sl=first3[1]; tgt=fifty-(sl-fifty)*2
      oid=place_angel_order(strike,"PE",LOT)
      state["put3"]=f"#{state['cnt3']} PUT BOUGHT! 50%={fifty} {strike}PE {pe} SL {sl:.0f} TGT {int(tgt)} ID:{oid}"
      phase3=0; first3=None; b3up=False; b3dn=False
   time.sleep(1)
  except Exception as e:
   state["msg"]=str(e); time.sleep(2)

threading.Thread(target=worker,daemon=True).start()

@app.route('/')
def home():
 return f"<h1 style='background:green;color:white;padding:8px'>AUTO ORDER ON - DIRECT API</h1><h2>NIFTY {state['ltp']} | {state['atm']} | {state['ist']}</h2><h3>3MIN {state['c3']} Cnt {state['cnt3']}</h3><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h4>{state['msg']}</h4>"

@app.route('/check')
def check(): return jsonify(state)
@app.route('/orders')
def orders():
 try:
  if smart: return jsonify(smart.orderBook())
 except Exception as e:
  return jsonify({"error":str(e)})
 return jsonify({})

if __name__=="__main__":
 app.run(host='0.0.0.0',port=10000)
