from flask import Flask, jsonify
from flask_cors import CORS
import os
from datetime import datetime, timedelta, timezone, date

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel = None
QTY = 65
IST = timezone(timedelta(hours=5, minutes=30))

# Doni Setup
OB3 = {"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0}
OB5 = {"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0}
TRADE = {"call_cnt":0,"put_cnt":0,"active":False,"buy_price":0,"symbol":"","token":"","sl":0,"tgt":0,"type":""}

def ist_now(): return datetime.now(IST)

def get_client():
    global angel
    if angel: return angel
    from SmartApi import SmartConnect
    import pyotp
    obj = SmartConnect(api_key=API_KEY)
    obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
    angel = obj
    return obj

def get_atm(obj, nifty, opt_type): # opt_type CE/PE
    strike = int(round(nifty/50)*50)
    for q in [f"NIFTY {strike} {opt_type}", f"NIFTY {strike}", f"NIFTY"]:
        try:
            res = obj.searchScrip("NFO", q)
            if res and res.get('data'):
                for it in res['data']:
                    ts = it.get('tradingsymbol','')
                    if opt_type in ts and str(strike) in ts and 'NIFTY' in ts:
                        try:
                            sym=it['tradingsymbol']; tok=it['symboltoken']
                            ltp=float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                            if ltp>2: return sym,tok,ltp,strike
                        except: continue
        except: continue
    return None,None,0,strike

def place_order(obj, sym, tok, side):
    params={"variety":"NORMAL","tradingsymbol":sym,"symboltoken":tok,"transactiontype":side,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":QTY}
    return obj.placeOrder(params)

@app.route('/')
def home():
    try:
        obj=get_client()
        now=ist_now()
        nifty=23554.0
        try: nifty=float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: pass

        ce_sym,ce_tok,ce_ltp,_=get_atm(obj,nifty,"CE")
        pe_sym,pe_tok,pe_ltp,_=get_atm(obj,nifty,"PE")

        # --- DAILY RESET 09/09/2026 ---
        if now.hour==9 and now.minute==14:
            OB3.update({"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0})
            OB5.update({"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0})
            TRADE["call_cnt"]=0; TRADE["put_cnt"]=0

        # --- 3 MIN SETUP ---
        if now.hour==9 and now.minute>=15 and now.minute<18 and not OB3["first_done"]:
            if OB3["h"]==0: OB3["h"]=nifty; OB3["l"]=nifty
            else: OB3["h"]=max(OB3["h"],nifty); OB3["l"]=min(OB3["l"],nifty)
        if now.hour==9 and now.minute==18 and not OB3["first_done"] and OB3["h"]!=0:
            OB3["fifty"]=(OB3["h"]+OB3["l"])/2; OB3["high1"]=OB3["h"]; OB3["first_done"]=True
        if OB3["first_done"] and not OB3["second_done"]:
            if now.hour==9 and now.minute>=18 and now.minute<21 and nifty>OB3["high1"]:
                OB3["active"]=True
            if now.hour==9 and now.minute>=21: OB3["second_done"]=True

        # --- 5 MIN SETUP ---
        if now.hour==9 and now.minute>=15 and now.minute<20 and not OB5["first_done"]:
            if OB5["h"]==0: OB5["h"]=nifty; OB5["l"]=nifty
            else: OB5["h"]=max(OB5["h"],nifty); OB5["l"]=min(OB5["l"],nifty)
        if now.hour==9 and now.minute==20 and not OB5["first_done"] and OB5["h"]!=0:
            OB5["fifty"]=(OB5["h"]+OB5["l"])/2; OB5["high1"]=OB5["h"]; OB5["first_done"]=True
        if OB5["first_done"] and not OB5["second_done"]:
            if now.hour==9 and now.minute>=20 and now.minute<25 and nifty>OB5["high1"]:
                OB5["active"]=True
            if now.hour==9 and now.minute>=25: OB5["second_done"]=True

        # Testing - aaj 09/09/2026 sathi
        if OB3["h"]==0:
            OB3.update({"h":nifty+10,"l":nifty-20,"fifty":nifty-5,"active":True,"first_done":True,"second_done":True,"high1":nifty+10})
            OB5.update({"h":nifty+12,"l":nifty-18,"fifty":nifty-3,"active":True,"first_done":True,"second_done":True,"high1":nifty+12})

        status="Waiting 50% Retest"
        entry_ob = None
        if OB3["active"]: entry_ob=OB3; status=f"3MIN Active 50%={OB3['fifty']:.1f}"
        elif OB5["active"]: entry_ob=OB5; status=f"5MIN Active 50%={OB5['fifty']:.1f}"

        # --- ENTRY LOGIC - ATM OPTION CHART UPTREND CHECK ---
        if entry_ob and not TRADE["active"]:
            is_retest = abs(nifty - entry_ob["fifty"]) < 5
            is_uptrend = ce_ltp > 100 # option chart uptrend (simple check) - CE vadhatoy
            # CALL ENTRY
            if is_retest and is_uptrend and TRADE["call_cnt"]<10 and ce_sym:
                try:
                    oid=place_order(obj, ce_sym, ce_tok, "BUY")
                    risk = entry_ob["h"]-entry_ob["l"]
                    TRADE.update({"active":True,"buy_price":ce_ltp,"symbol":ce_sym,"token":ce_tok,"sl":ce_ltp-risk,"tgt":ce_ltp+risk*2,"type":"CALL","call_cnt":TRADE["call_cnt"]+1})
                    status=f"CALL BUY {ce_sym} @ {ce_ltp} ID:{oid}"
                except Exception as e: status=f"BUY Fail {e}"
            # PUT ENTRY (downtrend asel tar)
            elif is_retest and not is_uptrend and TRADE["put_cnt"]<10 and pe_sym:
                try:
                    oid=place_order(obj, pe_sym, pe_tok, "BUY")
                    risk = entry_ob["h"]-entry_ob["l"]
                    TRADE.update({"active":True,"buy_price":pe_ltp,"symbol":pe_sym,"token":pe_tok,"sl":pe_ltp-risk,"tgt":pe_ltp+risk*2,"type":"PUT","put_cnt":TRADE["put_cnt"]+1})
                    status=f"PUT BUY {pe_sym} @ {pe_ltp} ID:{oid}"
                except Exception as e: status=f"BUY Fail {e}"

        # --- EXIT 1:2 ---
        if TRADE["active"]:
            cur_ltp = ce_ltp if TRADE["type"]=="CALL" else pe_ltp
            if cur_ltp<=TRADE["sl"] or cur_ltp>=TRADE["tgt"]:
                try:
                    oid=place_order(obj, TRADE["symbol"], TRADE["token"], "SELL")
                    reason="TGT 1:2 HIT" if cur_ltp>=TRADE["tgt"] else "SL HIT"
                    status=f"{reason} {TRADE['type']} SELL @ {cur_ltp} ID:{oid}"
                    TRADE["active"]=False
                    OB3["active"]=False; OB5["active"]=False
                except Exception as e: status=f"SELL Fail {e}"
            else:
                status=f"LIVE {TRADE['type']} {TRADE['symbol']} BUY:{TRADE['buy_price']} LTP:{cur_ltp} SL:{TRADE['sl']:.1f} TGT:{TRADE['tgt']:.1f} P/L:{cur_ltp-TRADE['buy_price']:.1f} | CALL:{TRADE['call_cnt']}/10 PUT:{TRADE['put_cnt']}/10"

        return f"""<html><head><meta http-equiv="refresh" content="3"><style>body{{background:#000;color:#0f0;font-family:monospace;padding:10px;font-size:13px}}b{{color:#ff0}}</style></head><body>
        ✅ Backend OK | IST:{now.strftime('%d-%m-%Y %H:%M:%S')} | NIFTY:{nifty:.2f} | LOT:{QTY}<br>
        ATM CE: {ce_sym} @ {ce_ltp} | PE: {pe_sym} @ {pe_ltp}<br><br>
        3MIN OB: H={OB3['h']:.1f} L={OB3['l']:.1f} 50%={OB3['fifty']:.1f} Active={OB3['active']} High1={OB3['high1']:.1f}<br>
        5MIN OB: H={OB5['h']:.1f} L={OB5['l']:.1f} 50%={OB5['fifty']:.1f} Active={OB5['active']} High1={OB5['high1']:.1f}<br>
        TRADE: {TRADE}<br><br>
        <b>Status: {status}</b><br><br>
        Setup: 1st 3/5min High var 2nd Close + 50% Retest + 1:2 TGT + SL Low | Roz 10 CALL + 10 PUT<br>
        Tarikh: 09/09/2026 | Expire: Kal Zali - Navin Expiry Auto
        </body></html>"""
    except Exception as e:
        return f"<html><head><meta http-equiv='refresh' content='3'></head><body>Error {e}<br>{ist_now()}</body></html>"

if __name__=='__main__':
    app.run(host='0.0.0.0',port=10000)
