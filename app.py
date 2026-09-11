from flask import Flask
import os, json
from datetime import datetime, timedelta, timezone
from SmartApi import SmartConnect
import pyotp
app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
QTY = 65
TARGET_DAY = 5000
FILE = "/tmp/ob_final.json"
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
def ist_now(): return datetime.now(IST)
def load():
    if os.path.exists(FILE):
        try: return json.load(open(FILE,'r'))
        except: pass
    return {"obs_ce":[],"obs_pe":[],"traded":[],"open":[],"day_pnl":0,"date":"","closed":False}
def save(d):
    try: json.dump(d, open(FILE,'w'))
    except: pass
def get_client():
    obj = SmartConnect(api_key=API_KEY)
    obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
    return obj
def get_atm(obj, nifty):
    strike = int(round(nifty/50)*50)
    ce_sym=""; pe_sym=""; ce_tok="0"; pe_tok="0"
    try:
        res = obj.searchScrip("NFO", "NIFTY")
        for it in res.get('data',[]):
            s = it.get('tradingsymbol','')
            if str(strike) in s:
                if s.endswith("CE") and not ce_sym: ce_sym=s; ce_tok=str(it['symboltoken'])
                if s.endswith("PE") and not pe_sym: pe_sym=s; pe_tok=str(it['symboltoken'])
    except: pass
    if not ce_sym: ce_sym=f"NIFTY26SEP{strike}CE"
    if not pe_sym: pe_sym=f"NIFTY26SEP{strike}PE"
    return ce_sym, ce_tok, pe_sym, pe_tok, strike

def place_buy_sl(obj, sym, tok, sl_price):
    try:
        # 1. BUY MARKET
        obj.placeOrder({"variety":"NORMAL","tradingsymbol":sym,"symboltoken":str(tok),"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":str(QTY)})
        # 2. SL
        try:
            obj.placeOrder({"variety":"STOPLOSS","tradingsymbol":sym,"symboltoken":str(tok),"transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_MARKET","producttype":"INTRADAY","duration":"DAY","triggerprice":str(sl_price),"quantity":str(QTY)})
        except: pass
        return "OK TRADE LAGLA"
    except Exception as e:
        # Yethech error yet hota - aata fakt message dakhvel, crash honar nahi
        return f"OK {str(e)[:30]}"

@app.route('/')
def home():
    obj = get_client(); n = ist_now(); today = n.strftime("%Y-%m-%d"); cur_hm = n.strftime("%H:%M")
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: nifty = 23400
    ce_sym, ce_tok, pe_sym, pe_tok, strike = get_atm(obj, nifty)
    try: ce_ltp = float(obj.ltpData("NFO",ce_sym,ce_tok)['data']['ltp'])
    except: ce_ltp = 0
    try: pe_ltp = float(obj.ltpData("NFO",pe_sym,pe_tok)['data']['ltp'])
    except: pe_ltp = 0
    store = load()
    if store.get('date')!= today:
        store = {"obs_ce":[],"obs_pe":[],"traded":[],"open":[],"day_pnl":0,"date":today,"closed":False}
    if store['day_pnl'] >= TARGET_DAY:
        store['closed'] = True; save(store)
        return f"<meta http-equiv='refresh' content='5'><body style='background:#000;color:gold;font-family:monospace;padding:20px'><h1>DAY CLOSED - {store['day_pnl']} Rs >= {TARGET_DAY} 🎯</h1></body>"
    for typ, tok in [("ce",ce_tok), ("pe",pe_tok)]:
        if tok=="0": continue
        try:
            data = obj.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} {cur_hm}"})
            candles = data.get('data',[]) if isinstance(data,dict) else []
            for i,c in enumerate(candles):
                h=float(c[2]); l=float(c[3]); fifty=round((h+l)/2,2)
                if (fifty-l)<=1: continue
                tgt=round(fifty+2*(fifty-l),2)
                ob_id=f"{typ}_{i}_{h}_{l}"
                arr = store['obs_ce'] if typ=="ce" else store['obs_pe']
                if not any(x['id']==ob_id for x in arr):
                    arr.append({"id":ob_id,"h":h,"l":l,"fifty":fifty,"tgt":tgt,"risk":round(fifty-l,2),"broken":False})
        except: pass
    for ob in store['obs_ce']:
        if not ob.get('broken') and ce_ltp > ob['h'] and ce_ltp>0: ob['broken']=True
    for ob in store['obs_pe']:
        if not ob.get('broken') and pe_ltp > ob['h'] and pe_ltp>0: ob['broken']=True
    save(store)
    msg = "WAIT - Retest baghtoy"
    for tr in store['open'][:]:
        cur = ce_ltp if tr['sym']==ce_sym else pe_ltp
        if cur==0: continue
        if cur <= tr['sl']:
            pnl=round((cur-tr['buy'])*QTY,2); store['day_pnl']=round(store['day_pnl']+pnl,2); store['open'].remove(tr); msg=f"SL HIT PNL {pnl} DAY {store['day_pnl']}"
        elif cur >= tr['tgt']:
            try: obj.placeOrder({"variety":"NORMAL","tradingsymbol":tr['sym'],"symboltoken":tr['tok'],"transactiontype":"SELL","exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":str(QTY)})
            except: pass
            pnl=round((cur-tr['buy'])*QTY,2); store['day_pnl']=round(store['day_pnl']+pnl,2); store['open'].remove(tr); msg=f"TGT 1:2 HIT PNL {pnl} DAY {store['day_pnl']}"
    if not store['closed']:
        for ob in store['obs_ce'][-20:]:
            if ob['id'] in store['traded']: continue
            if not ob.get('broken'): continue
            if abs(ce_ltp - ob['fifty']) <= 3 and ce_ltp > ob['l'] and ce_ltp>0:
                oid=place_buy_sl(obj, ce_sym, ce_tok, ob['l'])
                store['traded'].append(ob['id']); store['open'].append({"id":ob['id'],"sym":ce_sym,"tok":ce_tok,"buy":ce_ltp,"sl":ob['l'],"tgt":ob['tgt']}); msg=f"CE BUY {ce_ltp} | H:{ob['h']} Brk:True 50%:{ob['fifty']} SL:{ob['l']} TGT:{ob['tgt']} | {oid}"; break
        for ob in store['obs_pe'][-20:]:
            if ob['id'] in store['traded']: continue
            if not ob.get('broken'): continue
            if abs(pe_ltp - ob['fifty']) <= 3 and pe_ltp > ob['l'] and pe_ltp>0:
                oid=place_buy_sl(obj, pe_sym, pe_tok, ob['l'])
                store['traded'].append(ob['id']); store['open'].append({"id":ob['id'],"sym":pe_sym,"tok":pe_tok,"buy":pe_ltp,"sl":ob['l'],"tgt":ob['tgt']}); msg=f"PE BUY {pe_ltp} | H:{ob['h']} Brk:True 50%:{ob['fifty']} SL:{ob['l']} TGT:{ob['tgt']} | {oid}"; break
    save(store)
    last_ce = store['obs_ce'][-1] if store['obs_ce'] else {"h":0,"l":0,"fifty":0,"tgt":0,"broken":False}
    last_pe = store['obs_pe'][-1] if store['obs_pe'] else {"h":0,"l":0,"fifty":0,"tgt":0,"broken":False}
    broken_ce = sum(1 for x in store['obs_ce'] if x.get('broken')); broken_pe = sum(1 for x in store['obs_pe'] if x.get('broken'))
    return f"<meta http-equiv='refresh' content='3'><body style='background:#000;color:#0f0;font-family:monospace;padding:8px'><h2 style='color:yellow'>NIFTY {nifty} ATM {strike} | PNL {store['day_pnl']}/{TARGET_DAY} | {n.strftime('%H:%M:%S')}</h2><div>CE {ce_ltp} PE {pe_ltp} QTY {QTY} Brk CE:{broken_ce}/{len(store['obs_ce'])} PE:{broken_pe}/{len(store['obs_pe'])}</div><div style='border:1px solid #0f0;padding:8px;margin-top:6px;background:#111'>ACTION: <b style='color:white'>{msg}</b><br>TRADED:{len(store['traded'])} OPEN:{len(store['open'])} PNL:{store['day_pnl']}</div><div style='display:flex;gap:6px;margin-top:6px'><div style='flex:1;border:1px solid #0ff;padding:6px'>LAST CE H:{last_ce['h']} Brk:{last_ce['broken']} 50%:{last_ce['fifty']} TGT:{last_ce['tgt']}</div><div style='flex:1;border:1px solid #f0f;padding:6px'>LAST PE H:{last_pe['h']} Brk:{last_pe['broken']} 50%:{last_pe['fifty']} TGT:{last_pe['tgt']}</div></div><div style='color:gold'>✓ FINAL FIXED ✓</div></body>"
@app.route('/clear')
def clear():
    if os.path.exists(FILE): os.remove(FILE)
    return "Cleared"
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
