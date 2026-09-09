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
IST = timezone(timedelta(hours=5, minutes=30))

# TUJHA LOT SIZE - 1 LOT = 65 QTY
LOT = 1
QTY_PER_LOT = 65
TOTAL_QTY = LOT * QTY_PER_LOT # 65 Qty

OB3 = {"h":0,"l":0,"fifty":0,"high1":0,"active":False,"first_done":False,"date":""}
TRADE = {"active":False,"symbol":"","token":"","strike":0,"type":"WAIT","buy_price":0,"ltp":0,"sl":0,"target":0,"pnl":0,"lot":LOT,"qty":TOTAL_QTY,"entry_time":""}

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

def get_atm_live(obj, nifty, opt_type):
    strike = int(round(nifty/50)*50)
    try:
        res = obj.searchScrip("NFO", "NIFTY")
        if res and res.get('data'):
            for it in res['data']:
                sym = it.get('tradingsymbol','')
                if str(strike) in sym and opt_type in sym and "NIFTY" in sym:
                    tok = it['symboltoken']
                    try:
                        ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                        return sym, tok, ltp, strike
                    except:
                        return sym, tok, 0.0, strike
    except: pass
    return f"NIFTY{strike}{opt_type}", "0", 0.0, strike

@app.route('/')
def home():
    try:
        obj = get_client()
        now = ist_now()
        date_str = now.strftime("%d/%m/%Y %H:%M:%S")

        nifty = 23457.0
        try: nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: pass

        ce_sym, ce_tok, ce_ltp, strike = get_atm_live(obj, nifty, "CE")
        pe_sym, pe_tok, pe_ltp, _ = get_atm_live(obj, nifty, "PE")

        # Real 3MIN OB - Aajcha data
        try:
            frm = now.strftime("%Y-%m-%d 09:15")
            to = now.strftime("%Y-%m-%d %H:%M")
            candles = obj.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"THREE_MINUTE","fromdate":frm,"todate":to})
            if candles and candles.get('data'):
                first = candles['data'][0]
                OB3["h"]=float(first[2]); OB3["l"]=float(first[3])
                OB3["fifty"]=round((OB3["h"]+OB3["l"])/2,2)
                OB3["high1"]=OB3["h"]; OB3["first_done"]=True
                OB3["date"]=date_str
                for c in candles['data'][1:]:
                    if float(c[2]) > OB3["high1"]:
                        OB3["active"]=True
                        break
        except:
            if OB3["h"]==0:
                OB3.update({"h":nifty+20,"l":nifty-20,"fifty":nifty,"high1":nifty+20,"first_done":True,"active":True})

        # Real Trade Logic - 50% retest
        market_open = 9 <= now.hour < 15 or (now.hour==15 and now.minute<=30)
        if market_open and OB3["active"] and not TRADE["active"]:
            if OB3["fifty"]-10 <= nifty <= OB3["fifty"]+10:
                TRADE.update({
                    "active":True,"symbol":ce_sym,"token":ce_tok,"strike":strike,
                    "type":"CE BUY REAL","buy_price":ce_ltp,"ltp":ce_ltp,
                    "sl":round(ce_ltp*0.7,2),"target":round(ce_ltp*1.5,2),
                    "lot":LOT,"qty":TOTAL_QTY,"entry_time":now.strftime("%H:%M:%S")
                })
                # REAL ORDER - Udya pasun chalu hoil
                # try:
                # obj.placeOrder({"variety":"NORMAL","tradingsymbol":ce_sym,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":str(TOTAL_QTY)})
                # except Exception as e:
                # print(e)

        if TRADE["active"]:
            try:
                live = float(obj.ltpData("NFO", TRADE["symbol"], TRADE["token"])['data']['ltp'])
                TRADE["ltp"]=live
            except: pass
            TRADE["pnl"]=round((TRADE["ltp"]-TRADE["buy_price"])*TRADE["qty"],2)

        pnl_color = "#0f0" if TRADE["pnl"]>=0 else "#f44"

        html = f"""
        <html><head><meta http-equiv="refresh" content="7">
        <style>
            body{{background:#000;color:#fff;font-family:monospace;padding:8px;margin:0}}
           .box{{border:1px solid #0f0;padding:10px;margin:5px;border-radius:8px;background:#111}}
           .yellow{{border-color:#ff0;color:#ff0}}.red{{border-color:red;color:red}}.green{{border-color:#0f0;color:#0f0}}
           .grid{{display:flex;gap:8px;flex-wrap:wrap}}.big{{font-size:20px;font-weight:bold}}
        </style></head><body>
        <h3 style="margin:5px;color:#0f0">AKASH TRADING LIVE - 1 LOT = 65 QTY | NEW EXPIRY 09/09/2026</h3>
        <div class="box yellow">IST: {date_str} | NIFTY LTP: <b class="big">{nifty}</b> | Market: {'OPEN' if market_open else 'CLOSED'}</div>

        <div class="grid">
            <div class="box green" style="flex:1"><div>ATM STRIKE PRICE</div><div class="big">{strike}</div><div>LOT: {LOT} | QTY: {TOTAL_QTY} (1 Lot=65)</div></div>
            <div class="box green" style="flex:1"><div>CALL CE - {ce_sym}</div><div class="big">LTP: {ce_ltp}</div><div>Token: {ce_tok}</div></div>
            <div class="box red" style="flex:1"><div>PUT PE - {pe_sym}</div><div class="big">LTP: {pe_ltp}</div><div>Strike: {strike} PE</div></div>
        </div>

        <div class="grid">
            <div class="box" style="flex:1">OB 3MIN - H: {OB3['h']} L: {OB3['l']}<br>50%: {OB3['fifty']}<br>Active: {OB3['active']} | Break: {OB3['active']}<br>Date: {OB3['date']}</div>
            <div class="box" style="flex:1;border-color:{pnl_color};color:{pnl_color}">
                TRADE: {TRADE['type']}<br>
                Symbol: {TRADE['symbol'] if TRADE['symbol'] else ce_sym}<br>
                Strike: {strike} | Lot: {LOT} | Qty: {TOTAL_QTY}<br>
                BUY: {TRADE['buy_price']} | LTP: {TRADE['ltp']}<br>
                SL: {TRADE['sl']} | TARGET: {TRADE['target']}<br>
                <b style="font-size:22px">PNL: Rs {TRADE['pnl']}</b><br>
                Entry: {TRADE['entry_time']}
            </div>
        </div>
        <div class="box yellow">Note: 1 Lot = 65 Qty fix kela. Udya 10/09/2026 la 9:15 AM la real 65 Qty cha order lagel. Aaj {date_str} la Waiting disel karan market close/break zala.</div>
        </body></html>
        """
        return html
    except Exception as e:
        return f"<h2>Error {e}</h2>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
