from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)
FILE = "/tmp/ob_fullauto.json"
QTY = 65

def load():
    if os.path.exists(FILE):
        try:
            with open(FILE,'r') as f: return json.load(f)
        except: pass
    return {"nifty":0,"atm":0,"action":"Starting FULL AUTO 1:2","ce_50":0,"ce_sl":0,"ce_tgt":0,"ce_h":0,"ce_l":0,"pe_50":0,"pe_sl":0,"pe_tgt":0,"pe_h":0,"pe_l":0,"ce_sym":"","pe_sym":"","exp":"","time_str":"","log":"","pos":"NO POS"}

def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_tue():
    d=ist_now().date()
    off=(1-d.weekday())%7
    if off==0 and ist_now().hour>=15: off=7
    return d+timedelta(days=off)

def find_ob(c):
    if not c or len(c)<20: return None
    box=c[-16:-2]
    h=max(float(x[2]) for x in box)
    l=min(float(x[3]) for x in box)
    fifty=(h+l)/2
    risk=fifty-l
    tgt=fifty + (risk*2) # 1:2 RR
    return {"high":h,"low":l,"50":fifty,"risk":risk,"tgt":tgt}

def get_candles(smart, token):
    for interval in ["ONE_MINUTE","THREE_MINUTE","FIVE_MINUTE"]:
        try:
            frm=(ist_now()-timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
            to=ist_now().strftime("%Y-%m-%d %H:%M")
            res=smart.getCandleData({"exchange":"NFO","symboltoken":str(token),"interval":interval,"fromdate":frm,"todate":to})
            if res and res.get('data') and len(res['data'])>10:
                return res['data'],interval
        except: pass
    return [],"NO DATA"

def parse_search(res):
    try:
        if isinstance(res,str):
            import json as js; res=js.loads(res)
        if res.get('data') and len(res['data'])>0:
            return res['data'][0]
    except: pass
    return None

def run():
    try:
        smart=SmartConnect(api_key=os.environ.get("ANGEL_API_KEY"))
        smart.generateSession(os.environ.get("ANGEL_CLIENT_ID"),os.environ.get("ANGEL_PASSWORD"),pyotp.TOTP(os.environ.get("ANGEL_TOTP_SECRET")).now())
    except Exception as e:
        d=load();d["action"]=f"LOGIN FAIL {e}";save(d);return

    ce_tok=pe_tok=ce_trad=pe_trad=None;last_exp=None
    state="SEARCH" # SEARCH, WAITING_ENTRY, HOLDING_CE, HOLDING_PE
    entry_price=0

    while True:
        try:
            now=ist_now();d=load();exp=get_tue()
            ltp=smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
            atm=int(round(ltp/50)*50)
            d["nifty"]=ltp;d["atm"]=atm;d["exp"]=str(exp);d["time_str"]=now.strftime("%H:%M:%S")

            if last_exp!=exp or not ce_tok:
                try:
                    r1=smart.searchScrip("NFO",f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE");time.sleep(1)
                    r2=smart.searchScrip("NFO",f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}PE")
                    p1=parse_search(r1);p2=parse_search(r2)
                    if p1: ce_tok=p1['symboltoken'];ce_trad=p1['tradingsymbol'];d["ce_sym"]=ce_trad
                    if p2: pe_tok=p2['symboltoken'];pe_trad=p2['tradingsymbol'];d["pe_sym"]=pe_trad
                    last_exp=exp;state="SEARCH"
                except: time.sleep(20);continue

            ce_data,_=get_candles(smart,ce_tok) if ce_tok else ([],"")
            time.sleep(0.6)
            pe_data,_=get_candles(smart,pe_tok) if pe_tok else ([],"")

            ce_ob=find_ob(ce_data); pe_ob=find_ob(pe_data)
            if ce_ob:
                d["ce_h"]=round(ce_ob["high"],2);d["ce_l"]=round(ce_ob["low"],2);d["ce_50"]=round(ce_ob["50"],2);d["ce_sl"]=round(ce_ob["low"],2);d["ce_tgt"]=round(ce_ob["tgt"],2)
            if pe_ob:
                d["pe_h"]=round(pe_ob["high"],2);d["pe_l"]=round(pe_ob["low"],2);d["pe_50"]=round(pe_ob["50"],2);d["pe_sl"]=round(pe_ob["low"],2);d["pe_tgt"]=round(pe_ob["tgt"],2)

            # CHECK POSITION
            try:
                pos_data=smart.position()
                # simple check if any NFO position exists
                has_pos=False
                if pos_data and pos_data.get('data'):
                    for p in pos_data['data']:
                        if float(p.get('netqty',0))>0 and 'NIFTY' in p.get('tradingsymbol',''):
                            has_pos=True; d["pos"]=f"HOLDING {p['tradingsymbol']} QTY {p['netqty']} P&L {p.get('pnl','0')}"
                            break
                if not has_pos: d["pos"]="NO POS - READY FOR ENTRY"
            except: d["pos"]="POS CHECK ERR"

            # STRATEGY
            if "NO POS" in d["pos"]:
                state="SEARCH"
                if ce_ob and len(ce_data)>2 and float(ce_data[-1][4])>ce_ob["high"]:
                    try:
                        # 1. ENTRY LIMIT 50%
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":float(d["ce_50"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(2)
                        # 2. SL LIMIT
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT","price":float(d["ce_sl"]),"triggerprice":float(d["ce_sl"])+0.5,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(1)
                        # 3. TARGET LIMIT 1:2
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"LIMIT","price":float(d["ce_tgt"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        d["action"]=f"CE FULL AUTO PADLA ENTRY {d['ce_50']} SL {d['ce_sl']} TGT {d['ce_tgt']} 1:2"
                    except Exception as e: d["action"]=f"CE ORDER ERR {e}"

                elif pe_ob and len(pe_data)>2 and float(pe_data[-1][4])>pe_ob["high"]:
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":float(d["pe_50"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(2)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT","price":float(d["pe_sl"]),"triggerprice":float(d["pe_sl"])+0.5,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(1)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"LIMIT","price":float(d["pe_tgt"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        d["action"]=f"PE FULL AUTO PADLA ENTRY {d['pe_50']} SL {d['pe_sl']} TGT {d['pe_tgt']} 1:2"
                    except Exception as e: d["action"]=f"PE ORDER ERR {e}"
                else:
                    d["action"]=f"WAIT BREAKOUT | CE {d['ce_l']}-{d['ce_h']} | PE {d['pe_l']}-{d['pe_h']}"
            else:
                d["action"]=f"HOLDING - {d['pos']} - SL {d['ce_sl'] if 'CE' in d['pos'] else d['pe_sl']} TGT {d['ce_tgt'] if 'CE' in d['pos'] else d['pe_tgt']} 1:2 AUTO"

            d["log"]=f"RR 1:2 | QTY {QTY} | AUTO SL TGT"
            save(d);time.sleep(30)
        except Exception as e:
            d=load();d["action"]=f"LOOP ERR {e}";save(d);time.sleep(30)

threading.Thread(target=run,daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='10'><meta name='viewport' content='width=device-width'><style>body{{background:#111;color:#fff;font-family:Arial;padding:10px}}.g{{color:#0f0;font-size:20px}}.y{{color:#ffeb3b}}.b{{border:1px solid #333;padding:10px;border-radius:10px;margin:8px 0;background:#1c1c1c}}.t{{color:#0ff}}</style></head><body><h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2><div class=b>CE {d['ce_sym']}<br>BOX {d['ce_l']}-{d['ce_h']}<br>ENTRY 50% {d['ce_50']} | SL {d['ce_sl']}<br><b class=t>TGT 1:2 {d['ce_tgt']}</b></div><div class=b>PE {d['pe_sym']}<br>BOX {d['pe_l']}-{d['pe_h']}<br>ENTRY 50% {d['pe_50']} | SL {d['pe_sl']}<br><b class=t>TGT 1:2 {d['pe_tgt']}</b></div><div class=b>POS: {d['pos']}<br>{d['log']}<br>{d['exp']}</div><h3 class=y>{d['action']}</h3><p>{d['time_str']} | FULL AUTO 1:2 | 65 REAL</p></body></html>"

if __name__=='__main__':
    app.run(host='0.0.0.0',port=10000)
