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
    return {"nifty":0,"atm":0,"action":"Starting...","ce_50":0,"ce_sl":0,"ce_tgt":0,"ce_h":0,"ce_l":0,"pe_50":0,"pe_sl":0,"pe_tgt":0,"pe_h":0,"pe_l":0,"ce_sym":"","pe_sym":"","exp":"","time_str":"","log":"","pos":"NO POS"}

def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_tue():
    # 29 Sep Tue
    return datetime(2026,9,29).date()

def find_ob(c):
    if not c or len(c)<15: return None
    try:
        box=c[-15:-1] if len(c)>15 else c
        h=max(float(x[2]) for x in box)
        l=min(float(x[3]) for x in box)
        if h==0 or l==0 or h==l: return None
        fifty=(h+l)/2
        risk=fifty-l
        tgt=fifty + (risk*2)
        return {"high":h,"low":l,"50":fifty,"risk":risk,"tgt":tgt,"cnt":len(c)}
    except: return None

def get_candles_strong(smart, token, sym_name):
    # CE sathi jast retry
    for attempt in range(5):
        for interval in ["ONE_MINUTE","FIVE_MINUTE","THREE_MINUTE","FIFTEEN_MINUTE"]:
            try:
                frm=(ist_now()-timedelta(days=6)).strftime("%Y-%m-%d %H:%M")
                to=ist_now().strftime("%Y-%m-%d %H:%M")
                res=smart.getCandleData({"exchange":"NFO","symboltoken":str(token),"interval":interval,"fromdate":frm,"todate":to})
                if res and res.get('data') and len(res['data'])>=10:
                    return res['data'],interval
            except: time.sleep(1)
        time.sleep(2)
    return [],f"FAIL {sym_name}"

def run():
    try:
        smart=SmartConnect(api_key=os.environ.get("ANGEL_API_KEY"))
        smart.generateSession(os.environ.get("ANGEL_CLIENT_ID"),os.environ.get("ANGEL_PASSWORD"),pyotp.TOTP(os.environ.get("ANGEL_TOTP_SECRET")).now())
    except Exception as e:
        d=load();d["action"]=f"LOGIN FAIL {e}";save(d);return

    ce_tok=pe_tok=ce_trad=pe_trad=None

    while True:
        try:
            now=ist_now();d=load();exp=get_tue()
            try: ltp=smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
            except: ltp=d.get("nifty",23432)
            atm=int(round(ltp/50)*50)
            d["nifty"]=ltp;d["atm"]=atm;d["exp"]=str(exp);d["time_str"]=now.strftime("%H:%M:%S")

            if not ce_tok or d["ce_sym"]=="":
                try:
                    exp_str=exp.strftime("%d%b%y").upper() # 29SEP26
                    # search
                    s1=smart.searchScrip("NFO",f"NIFTY{exp_str}{atm}CE")
                    time.sleep(0.8)
                    s2=smart.searchScrip("NFO",f"NIFTY{exp_str}{atm}PE")
                    import json as js
                    def parse(r):
                        if isinstance(r,str): r=js.loads(r)
                        return r['data'][0] if r.get('data') else None
                    p1=parse(s1);p2=parse(s2)
                    if p1: ce_tok=p1['symboltoken'];ce_trad=p1['tradingsymbol'];d["ce_sym"]=ce_trad
                    if p2: pe_tok=p2['symboltoken'];pe_trad=p2['tradingsymbol'];d["pe_sym"]=pe_trad
                except Exception as e: d["log"]=f"SEARCH ERR {e}"

            ce_data,ce_info=get_candles_strong(smart,ce_tok,"CE") if ce_tok else ([],"NO TOK")
            time.sleep(0.5)
            pe_data,pe_info=get_candles_strong(smart,pe_tok,"PE") if pe_tok else ([],"NO TOK")

            ce_ob=find_ob(ce_data); pe_ob=find_ob(pe_data)

            if ce_ob:
                d["ce_h"]=round(ce_ob["high"],2);d["ce_l"]=round(ce_ob["low"],2);d["ce_50"]=round(ce_ob["50"],2);d["ce_sl"]=round(ce_ob["low"],2);d["ce_tgt"]=round(ce_ob["tgt"],2)
            else:
                d["log"]=f"CE FAIL {ce_info} candles {len(ce_data)}"

            if pe_ob:
                d["pe_h"]=round(pe_ob["high"],2);d["pe_l"]=round(pe_ob["low"],2);d["pe_50"]=round(pe_ob["50"],2);d["pe_sl"]=round(pe_ob["low"],2);d["pe_tgt"]=round(pe_ob["tgt"],2)

            # POS check
            try:
                pos=smart.position()
                has=False
                if pos and pos.get('data'):
                    for p in pos['data']:
                        if float(p.get('netqty',0))!=0 and 'NIFTY' in p.get('tradingsymbol',''):
                            has=True; d["pos"]=f"HOLD {p['tradingsymbol']} {p['netqty']} P&L {p.get('pnl','0')}";break
                if not has: d["pos"]="NO POS - READY FOR ENTRY"
            except: d["pos"]="NO POS"

            if "NO POS" in d["pos"]:
                # CE ENTRY
                if ce_ob and len(ce_data)>1 and float(ce_data[-1][4])>ce_ob["high"]:
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":float(d["ce_50"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(1.5)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT","price":float(d["ce_sl"]),"triggerprice":float(d["ce_sl"])+0.3,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(0.8)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"LIMIT","price":float(d["ce_tgt"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        d["action"]=f"CE ENTRY DONE {d['ce_50']} SL {d['ce_sl']} TGT {d['ce_tgt']}"
                    except Exception as e: d["action"]=f"CE ERR {e}"
                # PE ENTRY
                elif pe_ob and len(pe_data)>1 and float(pe_data[-1][4])>pe_ob["high"]:
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":float(d["pe_50"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(1.5)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT","price":float(d["pe_sl"]),"triggerprice":float(d["pe_sl"])+0.3,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        time.sleep(0.8)
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"SELL","exchange":"NFO","ordertype":"LIMIT","price":float(d["pe_tgt"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        d["action"]=f"PE ENTRY DONE {d['pe_50']} SL {d['pe_sl']} TGT {d['pe_tgt']}"
                    except Exception as e: d["action"]=f"PE ERR {e}"
                else:
                    d["action"]=f"WAIT BREAKOUT | CE {d['ce_l']}-{d['ce_h']} | PE {d['pe_l']}-{d['pe_h']}"
            else:
                d["action"]=f"HOLDING {d['pos']}"

            d["log"]=f"CE:{ce_info} {len(ce_data)}c | PE:{pe_info} {len(pe_data)}c | RR 1:2 QTY {QTY}"
            save(d);time.sleep(25)
        except Exception as e:
            d=load();d["action"]=f"LOOP ERR {e}";save(d);time.sleep(25)

threading.Thread(target=run,daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='10'><meta name='viewport' content='width=device-width'><style>body{{background:#111;color:#fff;font-family:Arial;padding:10px}}.g{{color:#0f0}}.y{{color:#ffeb3b}}.b{{border:1px solid #333;padding:10px;border-radius:10px;margin:8px 0;background:#1a1a1a}}.t{{color:#0ff}}</style></head><body><h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2><div class=b>CE {d['ce_sym']}<br>BOX {d['ce_l']}-{d['ce_h']}<br>ENTRY 50% {d['ce_50']} | SL {d['ce_sl']}<br><b class=t>TGT 1:2 {d['ce_tgt']}</b></div><div class=b>PE {d['pe_sym']}<br>BOX {d['pe_l']}-{d['pe_h']}<br>ENTRY 50% {d['pe_50']} | SL {d['pe_sl']}<br><b class=t>TGT 1:2 {d['pe_tgt']}</b></div><div class=b>POS: {d['pos']}<br>{d['log']}<br>{d['exp']}</div><h3 class=y>{d['action']}</h3><p>{d['time_str']} | FULL AUTO 1:2 | 65 REAL</p></body></html>"

if __name__=='__main__':
    app.run(host='0.0.0.0',port=10000)
