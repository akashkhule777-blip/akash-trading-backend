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
    return "BOTH CE PE CLEARED <a href='/'>HOME</a>",200

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
        except: nifty=23435.0
        strike=int(round(nifty/50)*50)

        # CE PE Token
        ce_sym=pe_sym=""; ce_tok=pe_tok=""; ce_ltp=pe_ltp=0
        try:
            r=sc.searchScrip("NFO",f"NIFTY {strike}")
            data=r.get('data',[]) if r else []
            ce_cands=[x for x in data if str(strike) in x['tradingsymbol'] and x['tradingsymbol'].endswith('CE')]
            pe_cands=[x for x in data if str(strike) in x['tradingsymbol'] and x['tradingsymbol'].endswith('PE')]
            ce_pick=next((x for x in ce_cands if '15SEP' in x['tradingsymbol'].upper()), ce_cands[0] if ce_cands else None)
            pe_pick=next((x for x in pe_cands if '15SEP' in x['tradingsymbol'].upper()), pe_cands[0] if pe_cands else None)
            if ce_pick:
                ce_sym=ce_pick['tradingsymbol']; ce_tok=ce_pick['symboltoken']
                ce_ltp=float(sc.ltpData("NFO",ce_sym,ce_tok)['data']['ltp'])
            if pe_pick:
                pe_sym=pe_pick['tradingsymbol']; pe_tok=pe_pick['symboltoken']
                pe_ltp=float(sc.ltpData("NFO",pe_sym,pe_tok)['data']['ltp'])
        except: pass

        # OPTION OB BOTH
        ob=load(OB_FILE,{})
        if ob.get("strike")!=strike: ob={}
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

        ce_h=ob.get("ce_h",0); ce_l=ob.get("ce_l",0); ce_f=ob.get("ce_f",0)
        pe_h=ob.get("pe_h",0); pe_l=ob.get("pe_l",0); pe_f=ob.get("pe_f",0)

        if ce_h==0 and ce_tok:
            ce_h,ce_l,ce_f=get_ob(ce_tok)
        if pe_h==0 and pe_tok:
            pe_h,pe_l,pe_f=get_ob(pe_tok)

        if ce_h!=0 or pe_h!=0:
            save(OB_FILE,{"strike":strike,"ce_h":ce_h,"ce_l":ce_l,"ce_f":ce_f,"pe_h":pe_h,"pe_l":pe_l,"pe_f":pe_f,"ce_sym":ce_sym,"pe_sym":pe_sym})

        state=load(STATE_FILE,{"ce_buy":0,"pe_buy":0,"ce_on":False,"pe_on":False,"e":0,"date":today})
        if state.get("date")!=today: state={"ce_buy":0,"pe_buy":0,"ce_on":False,"pe_on":False,"e":0,"date":today}

        time_ok = "09:21" <= now().strftime("%H:%M") <= "14:30"
        msgs=[]

        # CE ENTRY - Option cha 50%
        if not state["ce_on"] and time_ok and ce_f!=0 and abs(ce_ltp-ce_f)<=3 and ce_tok!="":
            state["ce_on"]=True; state["ce_buy"]=ce_ltp; state["e"]+=1; save(STATE_FILE,state)
            msgs.append(f"🔥 CE BUY {ce_sym} @ {ce_ltp} 50% {ce_f} SL {ce_l}")
        # PE ENTRY
        if not state["pe_on"] and time_ok and pe_f!=0 and abs(pe_ltp-pe_f)<=3 and pe_tok!="":
            state["pe_on"]=True; state["pe_buy"]=pe_ltp; state["e"]+=1; save(STATE_FILE,state)
            msgs.append(f"🔥 PE BUY {pe_sym} @ {pe_ltp} 50% {pe_f} SL {pe_l}")

        if not msgs:
            msgs.append(f"WAIT | CE {ce_ltp} near {ce_f} | PE {pe_ltp} near {pe_f}")

        # LIVE PNL
        live=""
        if state["ce_on"]:
            pnl=round((ce_ltp-state["ce_buy"])*QTY,2)
            if ce_ltp <= ce_l or ce_ltp >= ce_f+(ce_h-ce_l):
                state["ce_on"]=False; save(STATE_FILE,state); live+=f"CE EXIT PNL {pnl} | "
            else: live+=f"CE LIVE Buy {state['ce_buy']} LTP {ce_ltp} PNL {pnl} | "
        if state["pe_on"]:
            pnl=round((pe_ltp-state["pe_buy"])*QTY,2)
            if pe_ltp <= pe_l or pe_ltp >= pe_f+(pe_h-pe_l):
                state["pe_on"]=False; save(STATE_FILE,state); live+=f"PE EXIT PNL {pnl} | "
            else: live+=f"PE LIVE Buy {state['pe_buy']} LTP {pe_ltp} PNL {pnl} | "

        return f"<html><head><meta http-equiv='refresh' content='2'></head><body style='background:#000;color:#0f0;font-family:monospace;padding:10px'><h3 style='color:gold'>NIFTY {nifty} ATM {strike}</h3><div style='border:1px solid cyan;padding:8px'>CE: {ce_sym} @ {ce_ltp} | OB H:{ce_h} L:{ce_l} 50%:{ce_f}</div><div style='border:1px solid orange;padding:8px;margin-top:5px'>PE: {pe_sym} @ {pe_ltp} | OB H:{pe_h} L:{pe_l} 50%:{pe_f}</div><div style='border:2px solid lime;padding:10px;margin-top:8px;background:#111'>{'<br>'.join(msgs)}<br><b>{live}</b></div><div style='margin-top:8px'>Entries {state['e']}/10 QTY {QTY} <a href='/clear' style='color:red'>/clear BOTH</a> <a href='/health' style='color:cyan'>/health</a></div></body></html>"
    except Exception as e:
        return f"<html><head><meta http-equiv='refresh' content='3'></head><body style='background:#000;color:yellow'>RETRY {e}</body></html>",200

if __name__=='__main__': app.run(host='0.0.0.0',port=10000)
