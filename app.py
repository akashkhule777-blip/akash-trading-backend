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
    return "BOTH CLEARED <a href='/'>HOME</a>",200

def find_tokens(sc, strike):
    """15SEP cha token barobar shodh"""
    ce_sym=ce_tok=pe_sym=pe_tok=""
    try:
        # 15SEP ne search - strike ne nahi
        r = sc.searchScrip("NFO", "NIFTY15SEP")
        data = r.get('data',[]) if r else []
        # Filter
        for x in data:
            ts = x.get('tradingsymbol','')
            if str(strike) in ts:
                if ts.endswith('CE') and not ce_tok:
                    ce_sym=ts; ce_tok=x.get('symboltoken','')
                if ts.endswith('PE') and not pe_tok:
                    pe_sym=ts; pe_tok=x.get('symboltoken','')
        # dusra try - fakt NIFTY
        if not ce_tok or not pe_tok:
            r2 = sc.searchScrip("NFO", f"NIFTY {strike}")
            data2 = r2.get('data',[]) if r2 else []
            for x in data2:
                ts=x.get('tradingsymbol','')
                if '15SEP' in ts.upper() and str(strike) in ts:
                    if ts.endswith('CE') and not ce_tok: ce_sym=ts; ce_tok=x.get('symboltoken','')
                    if ts.endswith('PE') and not pe_tok: pe_sym=ts; pe_tok=x.get('symboltoken','')
    except: pass
    return ce_sym,ce_tok,pe_sym,pe_tok

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
        except: nifty=23424.1
        strike=int(round(nifty/50)*50)

        ce_sym,ce_tok,pe_sym,pe_tok=find_tokens(sc, strike)
        ce_ltp=pe_ltp=0
        try:
            if ce_tok: ce_ltp=float(sc.ltpData("NFO",ce_sym,ce_tok)['data']['ltp'])
        except: ce_ltp=110.0
        try:
            if pe_tok: pe_ltp=float(sc.ltpData("NFO",pe_sym,pe_tok)['data']['ltp'])
        except: pe_ltp=98.0

        # OPTION OB - NFO token varun
        def get_ob(tok):
            if not tok: return 0,0,0
            try:
                d=sc.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:20"})
                if d and d.get('data') and len(d['data'])>=3:
                    c=d['data']
                    h=max(float(c[i][2]) for i in range(3)); l=min(float(c[i][3]) for i in range(3))
                    return h,l,round((h+l)/2,2)
            except: pass
            return 0,0,0

        ob=load(OB_FILE,{})
        if ob.get("strike")!=strike or ob.get("ce_sym")!=ce_sym: ob={}

        ce_h=ob.get("ce_h",0); ce_l=ob.get("ce_l",0); ce_f=ob.get("ce_f",0)
        pe_h=ob.get("pe_h",0); pe_l=ob.get("pe_l",0); pe_f=ob.get("pe_f",0)

        if ce_h==0: ce_h,ce_l,ce_f=get_ob(ce_tok)
        if pe_h==0: pe_h,pe_l,pe_f=get_ob(pe_tok)

        if ce_h!=0 or pe_h!=0:
            save(OB_FILE,{"strike":strike,"ce_sym":ce_sym,"pe_sym":pe_sym,"ce_h":ce_h,"ce_l":ce_l,"ce_f":ce_f,"pe_h":pe_h,"pe_l":pe_l,"pe_f":pe_f})

        state=load(STATE_FILE,{"ce_on":False,"pe_on":False,"ce_buy":0,"pe_buy":0,"e":0,"date":today})
        if state.get("date")!=today: state={"ce_on":False,"pe_on":False,"ce_buy":0,"pe_buy":0,"e":0,"date":today}

        msg=[]
        if ce_tok=="" and pe_tok=="": msg.append(f"TOKEN SEARCH FAIL strike {strike} - Retrying...")
        else:
            if ce_f!=0 and abs(ce_ltp-ce_f)<=3 and not state["ce_on"] and "09:21" <= now().strftime("%H:%M") <= "14:30":
                state["ce_on"]=True; state["ce_buy"]=ce_ltp; state["e"]+=1; save(STATE_FILE,state)
                msg.append(f"🔥 CE BUY {ce_sym} @{ce_ltp} 50% {ce_f}")
            if pe_f!=0 and abs(pe_ltp-pe_f)<=3 and not state["pe_on"] and "09:21" <= now().strftime("%H:%M") <= "14:30":
                state["pe_on"]=True; state["pe_buy"]=pe_ltp; state["e"]+=1; save(STATE_FILE,state)
                msg.append(f"🔥 PE BUY {pe_sym} @{pe_ltp} 50% {pe_f}")
        if not msg: msg.append(f"WAIT | CE {ce_ltp} near {ce_f} | PE {pe_ltp} near {pe_f}")

        live=""
        if state["ce_on"]: live+=f"CE LIVE P:{round((ce_ltp-state['ce_buy'])*QTY,1)} | "
        if state["pe_on"]: live+=f"PE LIVE P:{round((pe_ltp-state['pe_buy'])*QTY,1)} | "

        return f"<html><head><meta http-equiv='refresh' content='2'></head><body style='background:#000;color:#0f0;font-family:monospace;padding:10px'><h3 style='color:gold'>NIFTY {nifty} ATM {strike}</h3><div style='border:1px solid cyan;padding:6px'>CE: {ce_sym} @{ce_ltp} | OB H:{ce_h} L:{ce_l} 50%:{ce_f} Tok:{ce_tok[-4:] if ce_tok else 'NO'}</div><div style='border:1px solid orange;padding:6px;margin-top:4px'>PE: {pe_sym} @{pe_ltp} | OB H:{pe_h} L:{pe_l} 50%:{pe_f} Tok:{pe_tok[-4:] if pe_tok else 'NO'}</div><div style='border:2px solid lime;padding:8px;margin-top:6px;background:#111'>{'<br>'.join(msg)}<br><b>{live}</b></div><div style='margin-top:6px'>E:{state['e']}/10 QTY:{QTY} <a href='/clear' style='color:red'>/clear</a></div></body></html>"
    except Exception as e:
        return f"<html><head><meta http-equiv='refresh' content='3'></head><body style='background:#000;color:yellow'>RETRY {e}</body></html>",200

if __name__=='__main__': app.run(host='0.0.0.0',port=10000)
