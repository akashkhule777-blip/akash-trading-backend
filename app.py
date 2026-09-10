from flask import Flask
from flask_cors import CORS
import os, json
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
CORS(app)

API_KEY=os.getenv("ANGEL_API_KEY"); CLIENT_ID=os.getenv("ANGEL_CLIENT_ID")
PASSWORD=os.getenv("ANGEL_PASSWORD"); TOTP_SECRET=os.getenv("ANGEL_TOTP_SECRET")
IST=timezone(timedelta(hours=5, minutes=30))
QTY=65
OB_FILE="/tmp/ob_both.json"
STATE_FILE="/tmp/state_both.json"

def now(): return datetime.now(IST)
def load(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f: return json.load(f)
    except: pass
    return d
def save(p,d):
    try:
        with open(p,'w') as f: json.dump(d,f)
    except: pass

@app.route('/health')
def health(): return "OK",200
@app.route('/clear')
def clear():
    for f in [OB_FILE,STATE_FILE]:
        try: os.remove(f)
        except: pass
    return "REAL CLEARED <a href='/'>HOME</a>",200

def find_tokens(sc, strike):
    ce_sym=ce_tok=pe_sym=pe_tok=""
    try:
        r=sc.searchScrip("NFO","NIFTY15SEP")
        data=r.get('data',[]) if r else []
        for x in data:
            ts=x.get('tradingsymbol','')
            if str(strike) in ts:
                if ts.endswith('CE') and not ce_tok: ce_sym=ts; ce_tok=x.get('symboltoken','')
                if ts.endswith('PE') and not pe_tok: pe_sym=ts; pe_tok=x.get('symboltoken','')
    except: pass
    return ce_sym,ce_tok,pe_sym,pe_tok

def place_real_order(sc, sym, tok, qty, side="BUY"):
    try:
        o = sc.placeOrder({
            "variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,
            "transactiontype":side,"exchange":"NFO","ordertype":"MARKET",
            "producttype":"INTRADAY","duration":"DAY","quantity":str(qty)
        })
        return str(o)
    except Exception as e:
        return f"ERR {e}"

@app.route('/')
def home():
    try:
        from SmartApi import SmartConnect
        import pyotp
        try:
            sc=SmartConnect(api_key=API_KEY)
            sc.generateSession(CLIENT_ID,PASSWORD,pyotp.TOTP(TOTP_SECRET.strip()).now())
        except Exception as e:
            return f"<body style='background:#000;color:yellow'>Login Retry {e}</body>",200

        today=now().strftime("%Y-%m-%d")
        try: nifty=float(sc.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: nifty=23419.7
        strike=int(round(nifty/50)*50)

        ce_sym,ce_tok,pe_sym,pe_tok=find_tokens(sc, strike)
        ce_ltp=pe_ltp=0
        try:
            if ce_tok: ce_ltp=float(sc.ltpData("NFO",ce_sym,ce_tok)['data']['ltp'])
        except: pass
        try:
            if pe_tok: pe_ltp=float(sc.ltpData("NFO",pe_sym,pe_tok)['data']['ltp'])
        except: pass

        def get_body_ob(tok):
            if not tok: return 0,0,0
            try:
                d=sc.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:20"})
                if d and d.get('data') and len(d['data'])>=3:
                    c=d['data']
                    # BODY fakt - wick nako
                    bodies=[]
                    for i in range(3):
                        o=float(c[i][1]); cl=float(c[i][4])
                        bodies.append((max(o,cl), min(o,cl))) # (body_high, body_low)
                    h=max(b[0] for b in bodies)
                    l=min(b[1] for b in bodies)
                    f=round((h+l)/2,2)
                    return h,l,f
            except: pass
            return 0,0,0

        ob=load(OB_FILE,{})
        if ob.get("strike")!=strike: ob={}

        ce_h=ob.get("ce_h",0); ce_l=ob.get("ce_l",0); ce_f=ob.get("ce_f",0)
        pe_h=ob.get("pe_h",0); pe_l=ob.get("pe_l",0); pe_f=ob.get("pe_f",0)

        if ce_h==0: ce_h,ce_l,ce_f=get_body_ob(ce_tok)
        if pe_h==0: pe_h,pe_l,pe_f=get_body_ob(pe_tok)

        if ce_h!=0 or pe_h!=0:
            save(OB_FILE,{"strike":strike,"ce_sym":ce_sym,"pe_sym":pe_sym,"ce_h":ce_h,"ce_l":ce_l,"ce_f":ce_f,"pe_h":pe_h,"pe_l":pe_l,"pe_f":pe_f})

        state=load(STATE_FILE,{"ce_on":False,"pe_on":False,"ce_buy":0,"pe_buy":0,"ce_order":"","pe_order":"","e":0,"date":today})
        if state.get("date")!=today: state={"ce_on":False,"pe_on":False,"ce_buy":0,"pe_buy":0,"ce_order":"","pe_order":"","e":0,"date":today}

        msgs=[]
        time_ok = "09:21" <= now().strftime("%H:%M") <= "14:30"

        if time_ok and ce_f!=0 and not state["ce_on"] and abs(ce_ltp-ce_f)<=3 and ce_tok!="":
            oid=place_real_order(sc, ce_sym, ce_tok, QTY, "BUY")
            state["ce_on"]=True; state["ce_buy"]=ce_ltp; state["ce_order"]=oid; state["e"]+=1; save(STATE_FILE,state)
            msgs.append(f"🔥 REAL CE BUY {ce_sym} @{ce_ltp} 50% {ce_f} OID:{oid}")
        if time_ok and pe_f!=0 and not state["pe_on"] and abs(pe_ltp-pe_f)<=3 and pe_tok!="":
            oid=place_real_order(sc, pe_sym, pe_tok, QTY, "BUY")
            state["pe_on"]=True; state["pe_buy"]=pe_ltp; state["pe_order"]=oid; state["e"]+=1; save(STATE_FILE,state)
            msgs.append(f"🔥 REAL PE BUY {pe_sym} @{pe_ltp} 50% {pe_f} OID:{oid}")

        if not msgs: msgs.append(f"WAIT | CE {ce_ltp} near {ce_f} (Body OB) | PE {pe_ltp} near {pe_f}")

        live=""
        if state["ce_on"]:
            pnl=round((ce_ltp-state["ce_buy"])*QTY,2)
            live+=f"CE LIVE Buy:{state['ce_buy']} LTP:{ce_ltp} PNL:{pnl} OID:{state['ce_order'][:8]} | "
            if ce_ltp <= ce_l: # SL = Body Low
                place_real_order(sc, ce_sym, ce_tok, QTY, "SELL"); state["ce_on"]=False; save(STATE_FILE,state)
        if state["pe_on"]:
            pnl=round((pe_ltp-state["pe_buy"])*QTY,2)
            live+=f"PE LIVE Buy:{state['pe_buy']} LTP:{pe_ltp} PNL:{pnl} OID:{state['pe_order'][:8]} | "
            if pe_ltp <= pe_l:
                place_real_order(sc, pe_sym, pe_tok, QTY, "SELL"); state["pe_on"]=False; save(STATE_FILE,state)

        return f"<html><head><meta http-equiv='refresh' content='2'></head><body style='background:#000;color:#0f0;font-family:monospace;padding:10px'><h3 style='color:gold'>NIFTY {nifty} ATM {strike} | BODY OB</h3><div style='border:1px solid cyan;padding:6px'>CE: {ce_sym} @{ce_ltp} | Body OB H:{ce_h} L:{ce_l} 50%:{ce_f}</div><div style='border:1px solid orange;padding:6px;margin-top:4px'>PE: {pe_sym} @{pe_ltp} | Body OB H:{pe_h} L:{pe_l} 50%:{pe_f}</div><div style='border:2px solid lime;padding:8px;margin-top:6px;background:#111'>{'<br>'.join(msgs)}<br><b>{live}</b></div><div style='margin-top:6px'>E:{state['e']}/10 QTY:{QTY} <a href='/clear' style='color:red'>/clear</a> /health</div></body></html>"
    except Exception as e:
        return f"<html><head><meta http-equiv='refresh' content='3'></head><body style='background:#000;color:yellow'>RETRY {e}</body></html>",200

if __name__=='__main__': app.run(host='0.0.0.0',port=10000)
