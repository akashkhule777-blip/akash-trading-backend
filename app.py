from flask import Flask
from flask_cors import CORS
import os, json
from datetime import datetime, timedelta, timezone
app=Flask(__name__); CORS(app)

API_KEY=os.getenv("ANGEL_API_KEY"); CLIENT_ID=os.getenv("ANGEL_CLIENT_ID")
PASSWORD=os.getenv("ANGEL_PASSWORD"); TOTP_SECRET=os.getenv("ANGEL_TOTP_SECRET")
IST=timezone(timedelta(hours=5,minutes=30)); QTY=65
OB_FILE="/tmp/ob3.json"; STATE_FILE="/tmp/state3.json"

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

@app.route('/clear')
def clear():
    for f in [OB_FILE,STATE_FILE]:
        try: os.remove(f)
        except: pass
    return "CLEARED <a href='/'>HOME</a>"

def find_tokens(sc, strike):
    ce_sym=ce_tok=pe_sym=pe_tok="";
    try:
        r=sc.searchScrip("NFO","NIFTY15SEP"); data=r.get('data',[]) if r else []
        for x in data:
            ts=x.get('tradingsymbol','')
            if str(strike) in ts:
                if ts.endswith('CE') and not ce_tok: ce_sym=ts; ce_tok=x.get('symboltoken','')
                if ts.endswith('PE') and not pe_tok: pe_sym=ts; pe_tok=x.get('symboltoken','')
    except: pass
    return ce_sym,ce_tok,pe_sym,pe_tok

def place_order(sc, sym, tok, side, otype, qty, trig="0", price="0", variety="NORMAL"):
    try:
        p={"variety":variety,"tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":otype,"producttype":"INTRADAY","duration":"DAY","quantity":str(qty),"price":str(price),"triggerprice":str(trig)}
        o=sc.placeOrder(p)
        if isinstance(o,dict):
            if o.get('status')==False: return f"REJ {o.get('message','')[:60]}"
            d=o.get('data'); return str(d.get('orderid',d) if isinstance(d,dict) else d)[:20]
        return str(o)[:20]
    except Exception as e: return f"ERR {str(e)[:60]}"

def get_3m_ob_and_2nd(sc, tok, today):
    ob_h=ob_l=ob_mid=c2_h=0
    try:
        d=sc.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 09:18"})
        if d and d.get('data') and len(d['data'])>=1:
            c=d['data'][0]; ob_h=float(c[2]); ob_l=float(c[3]); ob_mid=round((ob_h+ob_l)/2,2)
    except: pass
    try:
        d=sc.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":f"{today} 09:18","todate":f"{today} 09:21"})
        if d and d.get('data') and len(d['data'])>=1:
            c2_h=float(d['data'][0][2])
    except: pass
    return ob_h,ob_l,ob_mid,c2_h

@app.route('/')
def home():
    try:
        from SmartApi import SmartConnect; import pyotp
        try:
            sc=SmartConnect(api_key=API_KEY); sc.generateSession(CLIENT_ID,PASSWORD,pyotp.TOTP(TOTP_SECRET.strip()).now())
        except Exception as e: return f"Login {e}",200

        n=now(); today=n.strftime("%Y-%m-%d"); hm=n.strftime("%H:%M")
        try: nifty=float(sc.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: nifty=24500
        strike=int(round(nifty/50)*50)
        ce_sym,ce_tok,pe_sym,pe_tok=find_tokens(sc, strike)

        ob=load(OB_FILE,{})
        if ob.get("date")!=today or ob.get("strike")!=strike: ob={"date":today,"strike":strike}
        ce_h=ob.get("ce_h",0); ce_l=ob.get("ce_l",0); ce_mid=ob.get("ce_mid",0); ce_c2h=ob.get("ce_c2h",0)
        pe_h=ob.get("pe_h",0); pe_l=ob.get("pe_l",0); pe_mid=ob.get("pe_mid",0); pe_c2h=ob.get("pe_c2h",0)
        if ce_h==0:
            ch,cl,cm,c2h=get_3m_ob_and_2nd(sc, ce_tok, today)
            if ch!=0: ce_h,ce_l,ce_mid,ce_c2h=ch,cl,cm,c2h
        if pe_h==0:
            ch,cl,cm,c2h=get_3m_ob_and_2nd(sc, pe_tok, today)
            if ch!=0: pe_h,pe_l,pe_mid,pe_c2h=ch,cl,cm,c2h
        if ce_h or pe_h:
            ob.update({"ce_h":ce_h,"ce_l":ce_l,"ce_mid":ce_mid,"ce_c2h":ce_c2h,"pe_h":pe_h,"pe_l":pe_l,"pe_mid":pe_mid,"pe_c2h":pe_c2h,"ce_sym":ce_sym,"pe_sym":pe_sym,"strike":strike,"date":today}); save(OB_FILE, ob)

        state=load(STATE_FILE,{"date":today,"ce_on":False,"pe_on":False,"ce_buy":0,"pe_buy":0,"ce_oid":"","pe_oid":"","ce_sl_oid":"","pe_sl_oid":"","ce_tgt":0,"pe_tgt":0,"e":0,"ce_broken":False,"pe_broken":False})
        if state.get("date")!=today: state={"date":today,"ce_on":False,"pe_on":False,"ce_buy":0,"pe_buy":0,"ce_oid":"","pe_oid":"","ce_sl_oid":"","pe_sl_oid":"","ce_tgt":0,"pe_tgt":0,"e":0,"ce_broken":False,"pe_broken":False}

        ce_ltp=pe_ltp=0
        try:
            if ce_tok: ce_ltp=float(sc.ltpData("NFO",ce_sym,ce_tok)['data']['ltp'])
        except: pass
        try:
            if pe_tok: pe_ltp=float(sc.ltpData("NFO",pe_sym,pe_tok)['data']['ltp'])
        except: pass

        if ce_c2h>ce_h and ce_h!=0: state["ce_broken"]=True
        if pe_c2h>pe_h and pe_h!=0: state["pe_broken"]=True

        msgs=[]; time_ok="09:21" <= hm <= "14:30"

        # === ENTRY 50% + SL = OB Low + 1:2 RR ===
        if time_ok and state["ce_broken"] and not state["ce_on"] and ce_mid!=0 and abs(ce_ltp-ce_mid)<=5 and ce_tok:
            risk=ce_mid-ce_l; tgt=round(ce_mid + 2*risk,2) # 1:2 RR
            oid=place_order(sc, ce_sym, ce_tok, "BUY", "MARKET", QTY)
            sl_oid=place_order(sc, ce_sym, ce_tok, "SELL", "STOPLOSS_MARKET", QTY, trig=str(ce_l), variety="STOPLOSS")
            state.update({"ce_on":True,"ce_buy":ce_ltp,"ce_oid":oid,"ce_sl_oid":sl_oid,"ce_tgt":tgt,"e":state["e"]+1})
            msgs.append(f"🔥 CE BUY {ce_ltp} | 50%:{ce_mid} SL:{ce_l} TGT:{tgt} 1:2 OID:{oid} SL:{sl_oid}")

        if time_ok and state["pe_broken"] and not state["pe_on"] and pe_mid!=0 and abs(pe_ltp-pe_mid)<=5 and pe_tok:
            risk=pe_mid-pe_l; tgt=round(pe_mid + 2*risk,2)
            oid=place_order(sc, pe_sym, pe_tok, "BUY", "MARKET", QTY)
            sl_oid=place_order(sc, pe_sym, pe_tok, "SELL", "STOPLOSS_MARKET", QTY, trig=str(pe_l), variety="STOPLOSS")
            state.update({"pe_on":True,"pe_buy":pe_ltp,"pe_oid":oid,"pe_sl_oid":sl_oid,"pe_tgt":tgt,"e":state["e"]+1})
            msgs.append(f"🔥 PE BUY {pe_ltp} | 50%:{pe_mid} SL:{pe_l} TGT:{tgt} 1:2 OID:{oid} SL:{sl_oid}")

        # === LIVE - SL/ TGT CHECK ===
        live=""
        if state["ce_on"]:
            # SL hit
            if ce_ltp <= ce_l and ce_l!=0:
                place_order(sc, ce_sym, ce_tok, "SELL", "MARKET", QTY); state["ce_on"]=False; msgs.append(f"CE SL HIT {ce_l}")
            elif ce_ltp >= state["ce_tgt"] and state["ce_tgt"]!=0: # 1:2 TGT hit
                place_order(sc, ce_sym, ce_tok, "SELL", "MARKET", QTY); state["ce_on"]=False; msgs.append(f"✅ CE TGT 1:2 HIT {state['ce_tgt']}")
            else: live+=f"CE LIVE B:{state['ce_buy']} LTP:{ce_ltp} SL:{ce_l} TGT:{state['ce_tgt']} | "

        if state["pe_on"]:
            if pe_ltp <= pe_l and pe_l!=0:
                place_order(sc, pe_sym, pe_tok, "SELL", "MARKET", QTY); state["pe_on"]=False; msgs.append(f"PE SL HIT {pe_l}")
            elif pe_ltp >= state["pe_tgt"] and state["pe_tgt"]!=0:
                place_order(sc, pe_sym, pe_tok, "SELL", "MARKET", QTY); state["pe_on"]=False; msgs.append(f"✅ PE TGT 1:2 HIT {state['pe_tgt']}")
            else: live+=f"PE LIVE B:{state['pe_buy']} LTP:{pe_ltp} SL:{pe_l} TGT:{state['pe_tgt']} | "

        if not msgs: msgs.append(f"WAIT IST {hm} | CE H:{ce_h} 50:{ce_mid} L:{ce_l} C2:{ce_c2h} Brk:{state['ce_broken']} LTP:{ce_ltp} | PE H:{pe_h} 50:{pe_mid} L:{pe_l} C2:{pe_c2h} Brk:{state['pe_broken']} LTP:{pe_ltp}")

        save(STATE_FILE, state)
        return f"<html><head><meta http-equiv='refresh' content='2'></head><body style='background:#000;color:#0f0;font-family:monospace;padding:8px'><h3 style='color:gold'>NIFTY {nifty} ATM {strike} | 3M OB 1:2 RR {today} IST</h3><div>CE OB H:{ce_h} 50:{ce_mid} SL(L):{ce_l} C2H:{ce_c2h}</div><div>PE OB H:{pe_h} 50:{pe_mid} SL(L):{pe_l} C2H:{pe_c2h}</div><div style='border:2px solid lime;padding:6px;margin-top:6px'>{'<br>'.join(msgs)}<br><b>{live}</b><br>E:{state['e']} QTY:{QTY}</div></body></html>"
    except Exception as e: return f"RETRY {e}",200

if __name__=='__main__': app.run(host='0.0.0.0',port=10000)
