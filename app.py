from flask import Flask, jsonify
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel = None
OB = {"h":0,"l":0,"fifty":0,"active":False}
POS = {"active":False, "buy_price":0, "symbol":"", "token":""}
QTY = "65" # Tujhya pramane 65 Lot

def get_client():
    global angel
    if angel: return angel
    from SmartApi import SmartConnect
    import pyotp
    obj = SmartConnect(api_key=API_KEY)
    obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
    angel = obj
    return obj

def place_order(obj, symbol, token, ttype):
    params = {"variety":"NORMAL","tradingsymbol":symbol,"symboltoken":token,
              "transactiontype":ttype,"exchange":"NFO","ordertype":"MARKET",
              "producttype":"INTRADAY","duration":"DAY","quantity":QTY}
    return obj.placeOrder(params)

def check():
    global OB, POS
    obj = get_client()
    nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
    strike = round(nifty/50)*50
    ce = obj.searchScrip("NFO", f"NIFTY {strike} CE")['data'][0]
    ce_sym, ce_tok = ce['symbol'], ce['symboltoken']
    ce_ltp = float(obj.ltpData("NFO", ce_sym, ce_tok)['data']['ltp'])

    if OB["h"]==0:
        OB["h"]=nifty+15; OB["l"]=nifty-15; OB["fifty"]=(OB["h"]+OB["l"])/2; OB["active"]=True
        OB["sl"]=OB["l"]; OB["risk"]=OB["h"]-OB["l"]

    status = f"LOT:{QTY} | 50%:{OB['fifty']:.1f} NIFTY:{nifty:.1f}"

    if OB["active"] and not POS["active"] and abs(nifty - OB["fifty"]) < 6:
        oid = place_order(obj, ce_sym, ce_tok, "BUY")
        POS.update({"active":True,"buy_price":ce_ltp,"symbol":ce_sym,"token":ce_tok})
        OB["tgt"]=ce_ltp + (OB["risk"]*2); OB["sl_price"]=ce_ltp - OB["risk"]
        status = f"REAL BUY {ce_sym} QTY {QTY} @ {ce_ltp} ID:{oid}"

    if POS["active"]:
        if ce_ltp <= OB["sl_price"] or ce_ltp >= OB["tgt"]:
            oid = place_order(obj, POS["symbol"], POS["token"], "SELL")
            status = f"SELL {POS['symbol']} @ {ce_ltp} ID:{oid} P/L:{ce_ltp-POS['buy_price']:.1f}"
            POS["active"]=False

    return {"price":nifty,"qty":QTY,"status":status,"pos":POS}

@app.route('/')
def home(): return check()["status"]
@app.route('/get_ltp')
def ltp(): return jsonify(check())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
