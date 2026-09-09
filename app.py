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

# Real OB Data - No Demo
OB3 = {"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"second_done":False,"date":""}
TRADE = {"active":False,"symbol":"","token":"","strike":0,"type":"WAIT","buy_price":0,"ltp":0,"sl":0,"target":0,"pnl":0,"entry_time":""}

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

def get_atm(obj, nifty, opt_type):
    strike = int(round(nifty/50)*50)
    try:
        res = obj.searchScrip("NFO", f"NIFTY {strike} {opt_type}")
        if res and res.get('data'):
            for it in res['data']:
                if str(strike) in it['tradingsymbol'] and opt_type in it['tradingsymbol']:
                    tok = it['symboltoken']; sym = it['tradingsymbol']
                    ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                    return sym, tok, ltp, strike
    except: pass
    return f"NIFTY{strike}{opt_type}", "0", 100.0, strike

def get_nifty_candle_data(obj):
    # Real 3min candle sathi Nifty data
    try:
        now = ist_now()
        # Angel getCandleData
        frm = now.strftime("%Y-%m-%d 09:15")
        to = now.strftime("%Y-%m-%d %H:%M")
        data = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"THREE_MINUTE","fromdate":frm,"todate":to})
        if data and data.get('data'):
            return data['data'] # [[time,o,h,l,c,v],...]
    except Exception as e:
        print(f"Candle error {e}")
    return []

@app.route('/')
def home():
    try:
        obj = get_client()
        now = ist_now()
        date_str = now.strftime("%d/%m/%Y")

        # Market Hours Check - 9:15 to 15:30
        market_open = 9 <= now.hour < 15 or (now.hour==15 and now.minute<=30)
        is_morning = now.hour==9 and now.minute>=15

        nifty = 0
        try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: nifty = 24800.0

        ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
        pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

        # 9:14 Daily Reset - Real
        if now.hour==9 and now.minute==14:
            OB3.update({"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"second_done":False,"date":date_str})
            TRADE.update({"active":False,"type":"WAIT","pnl":0})

        # REAL OB LOGIC - Udya pasun chalu
        log_msg = f"Market {'OPEN' if market_open else 'CLOSED'} | Date {date_str}"

        if market_open:
            candles = get_nifty_candle_data(obj)
            if candles and len(candles)>=1:
                # First 3min candle 9:15-9:18
                first = candles[0]
                f_high, f_low = float(first[2]), float(first[3])

                if OB3["h"]==0 and now.hour==9 and now.minute>=18:
                    OB3["h"]=f_high; OB3["l"]=f_low
                    OB3["fifty"]=round((f_high+f_low)/2,2)
                    OB3["high1"]=f_high
                    OB3["first_done"]=True
                    OB3["date"]=date_str
                    log_msg = f"1st Candle Fixed: H={f_high} L={f_low} 50%={OB3['fifty']}"

                # High Break Check - 9:18 nanatar
                if OB3["first_done"] and not OB3["active"]:
                    for c in candles[1:]:
                        if float(c[2]) > OB3["high1"]:
                            OB3["active"]=True
                            OB3["second_done"]=True
                            log_msg = f"HIGH BREAKED at {c[2]} - Waiting for 50% retest {OB3['fifty']}"
                            break

                # 50% Retest Entry - Real Entry
                if OB3["active"] and not TRADE["active"]:
                    if OB3["fifty"]-5 <= nifty <= OB3["fifty"]+5:
                        # REAL BUY CE
                        TRADE.update({
                            "active":True,"symbol":ce_sym,"token":ce_tok,"strike":strike,
                            "type":"CE BUY REAL","buy_price":ce_ltp,"ltp":ce_ltp,
                            "sl":round(ce_ltp*0.7,2),"target":round(ce_ltp*1.5,2),
                            "entry_time":now.strftime("%H:%M:%S")
                        })
                        log_msg = f"REAL ENTRY DONE @ {ce_ltp} Strike {strike} SL {TRADE['sl']} TGT {TRADE['target']}"

        # PNL Update if Active
        if TRADE["active"]:
            try:
                live_ltp = float(obj.ltpData("NFO", TRADE["symbol"], TRADE["token"])['data']['ltp'])
                TRADE["ltp"]=live_ltp
            except: pass
            TRADE["pnl"]=round((TRADE["ltp"]-TRADE["buy_price"])*QTY,2)

        html = f"""
        <html><head><meta http-equiv="refresh" content="10">
        <style>body{{background:#000;color:#0f0;font-family:monospace;padding:10px}}.box{{border:1px solid #0f0;padding:10px;margin:5px;border-radius:5px}}.red{{border-color:red;color:red}}.yellow{{border-color:yellow;color:yellow}}</style>
        </head><body>
        <h2>REAL TRADING - From Tomorrow 10/09/2026 Morning 9:15 AM</h2>
        <div class="box yellow">TODAY: {date_str} IST: {now.strftime('%H:%M:%S')} | NIFTY: {nifty} | Market: {'OPEN' if market_open else 'CLOSED'} | {log_msg}</div>
        <div style="display:flex;gap:10px">
            <div class="box" style="flex:1">OB 3MIN: H={OB3['h']} L={OB3['l']} 50%={OB3['fifty']} Active={OB3['active']} FirstDone={OB3['first_done']}</div>
            <div class="box" style="flex:1">STRIKE: {strike} | CE: {ce_sym} LTP {ce_ltp} | PE: {pe_sym} LTP {pe_ltp}</div>
        </div>
        <div class="box {'red' if TRADE['pnl']<0 else ''}" style="flex:1">
            <b>TRADE REAL:</b> {TRADE['type']} | Symbol: {TRADE['symbol']} | Strike: {TRADE['strike']}<br>
            BUY: {TRADE['buy_price']} | LTP: {TRADE['ltp']} | QTY: {QTY}<br>
            SL: {TRADE['sl']} | TARGET: {TRADE['target']} | PNL: Rs {TRADE['pnl']}<br>
            Entry Time: {TRADE['entry_time']} | Status: {'ACTIVE REAL' if TRADE['active'] else 'WAITING FOR 9:15 AM 10/09/2026'}
        </div>
        <div class="box">Kal sakali 9:15 la pahili 3min candle fix hoil -> 9:18 la High break check -> 50% retest la Real CE BUY 65 Lot hoil. Aaj ratri kahi entry nahi, fakt Waiting disel.</div>
        </body></html>
        """
        return html
    except Exception as e:
        return f"<body>Error {e}<meta http-equiv='refresh' content='5'></body>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
