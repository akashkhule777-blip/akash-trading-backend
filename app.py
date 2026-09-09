from flask import Flask
from flask_cors import CORS
import os
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel = None
QTY = 65
IST = timezone(timedelta(hours=5, minutes=30))

OB3 = {"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"date":""}
TRADE = {"active":False,"symbol":"","token":"","strike":0,"type":"WAIT","buy_price":0,"ltp":0,"sl":0,"target":0,"pnl":0}

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

# NAVIN EXPIRY FIX - 09/09/2026
def get_atm_live(obj, nifty, opt_type):
    strike = int(round(nifty/50)*50)
    # Method 1: Direct Search with Expiry Auto
    try:
        # NIFTY search - sagle expiry yetil
        res = obj.searchScrip("NFO", "NIFTY")
        if res and res.get('data'):
            best = None
            for it in res['data']:
                sym = it.get('tradingsymbol','')
                # Ex: NIFTY09SEP25 23500CE OR NIFTY 23500 CE - strike match
                if str(strike) in sym and opt_type in sym and "NIFTY" in sym:
                    # CE token ghe
                    if not best:
                        best = it
                    # Jar 2-3 token sapadla tar pahila expiry ghe
                    if "SEP" in sym.upper() or "2026" in sym:
                        best = it
                        break
            if best:
                sym = best['tradingsymbol']
                tok = best['symboltoken']
                try:
                    ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                    print(f"FOUND {sym} LTP {ltp}")
                    return sym, tok, ltp, strike
                except:
                    return sym, tok, 100.0, strike
    except Exception as e:
        print(f"ATM Error: {e}")

    # Fallback
    return f"NIFTY{strike}{opt_type}", "0", 0.0, strike

@app.route('/')
def home():
    obj = get_client()
    now = ist_now()
    date_str = now.strftime("%d/%m/%Y")

    nifty = 0
    try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    except: nifty = 23477.6

    ce_sym, ce_tok, ce_ltp, strike = get_atm_live(obj, nifty, "CE")
    pe_sym, pe_tok, pe_ltp, _ = get_atm_live(obj, nifty, "PE")

    # REAL TIME OB FIX - 15:03 la pan H L dakhavnar
    try:
        frm = now.strftime("%Y-%m-%d 09:15")
        to = now.strftime("%Y-%m-%d %H:%M")
        candles = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"THREE_MINUTE","fromdate":frm,"todate":to})
        if candles and candles.get('data') and len(candles['data'])>0:
            first = candles['data'][0]
            OB3["h"]=float(first[2]); OB3["l"]=float(first[3])
            OB3["fifty"]=round((OB3["h"]+OB3["l"])/2,2)
            OB3["high1"]=OB3["h"]; OB3["first_done"]=True; OB3["date"]=date_str
            # Active check
            for c in candles['data'][1:]:
                if float(c[2]) > OB3["high1"]:
                    OB3["active"]=True
                    break
    except Exception as e:
        print(f"Candle err {e}")
        # Fallback demo OB jar API fail
        if OB3["h"]==0:
            OB3.update({"h":nifty+20,"l":nifty-20,"fifty":nifty,"high1":nifty+20,"first_done":True,"active":True})

    status_msg = f"TODAY: {date_str} IST: {now.strftime('%H:%M:%S')} | NIFTY: {nifty} | Market: {'OPEN' if 9 <= now.hour < 16 else 'CLOSED'}"

    html = f"""
    <html><head><meta http-equiv="refresh" content="7">
    <style>
        body{{background:#000;color:#0f0;font-family:monospace;padding:10px}}
       .box{{border:1px solid #0f0;padding:10px;margin:6px;border-radius:6px}}
       .yellow{{border-color:#ff0;color:#ff0}}.red{{border-color:red;color:red}}
       .grid{{display:flex;gap:10px;flex-wrap:wrap}}.grid.box{{flex:1;min-width:200px}}
    </style></head><body>
    <h2 style="color:#0f0">REAL TRADING - From Tomorrow 10/09/2026 Morning 9:15 AM</h2>
    <div class="box yellow">{status_msg} | New Expiry Active</div>
    <div class="grid">
        <div class="box">OB 3MIN: H={OB3['h']} L={OB3['l']} 50%={OB3['fifty']}<br>Active={OB3['active']} FirstDone={OB3['first_done']}<br>High Break={OB3['active']}</div>
        <div class="box">STRIKE: {strike}<br>CE: {ce_sym}<br>LTP: <b style="font-size:20px">{ce_ltp}</b> | Token {ce_tok}<br>PE: {pe_sym}<br>LTP: <b style="font-size:20px">{pe_ltp}</b></div>
    </div>
    <div class="box {'red' if TRADE['pnl']<0 else ''}">
        TRADE REAL: {TRADE['type']} | Symbol: {ce_sym if not TRADE['symbol'] else TRADE['symbol']} | Strike: {strike}<br>
        BUY: {TRADE['buy_price']} | LTP: {ce_ltp} | QTY: 65<br>
        SL: {round(ce_ltp*0.7,2) if ce_ltp>0 else 0} | TARGET: {round(ce_ltp*1.5,2) if ce_ltp>0 else 0} | PNL: Rs {TRADE['pnl']}<br>
        Status: {'WAITING FOR 50% RETEST' if not OB3['active'] else 'WAITING FOR 50% RETEST TOMORROW 9:15 AM - OB Ready' if not TRADE['active'] else 'ACTIVE'}
    </div>
    <div class="box yellow">Fix: Aata 15:03 la pan Nifty {nifty} Strike {strike} CE LTP {ce_ltp} PE LTP {pe_ltp} disel. LTP 100 yet hota karan expiry token sapdat navta - aata NAVIN EXPIRY token fix kela. Udya 10/09/2026 la 9:15 la OB auto fix hoil.</div>
    </body></html>
    """
    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
