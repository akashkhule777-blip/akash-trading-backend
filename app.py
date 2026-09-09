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
OB3 = {"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0}
OB5 = {"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0}
TRADE = {"active":False,"buy_price":0,"symbol":"","token":"","sl":0,"tgt":0,"type":"","call_cnt":0,"put_cnt":0,"last_action":""}

def ist_now():
    return datetime.now(IST)

def get_client():
    global angel
    if angel:
        return angel
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
                if opt_type in it['tradingsymbol'] and str(strike) in it['tradingsymbol']:
                    sym = it['tradingsymbol']; tok = it['symboltoken']
                    ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                    if ltp > 1:
                        return sym, tok, ltp, strike
    except:
        pass
    return f"NIFTY{strike}{opt_type}", "0", 100.0, strike

@app.route('/')
def home():
    try:
        obj = get_client()
        now = ist_now()
        nifty = 23554.0
        try:
            nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except:
            pass

        ce_sym, ce_tok, ce_ltp, strike = get_atm(obj, nifty, "CE")
        pe_sym, pe_tok, pe_ltp, _ = get_atm(obj, nifty, "PE")

        # Reset 9:14
        if now.hour==9 and now.minute==14:
            OB3.update({"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0})
            OB5.update({"h":0,"l":0,"fifty":0,"active":False,"first_done":False,"second_done":False,"high1":0})

        # Demo OB - 09/09/2026
        if OB3["h"]==0:
            OB3.update({"h":nifty+10,"l":nifty-20,"fifty":nifty-5,"active":True,"first_done":True,"second_done":True,"high1":nifty+10})
            OB5.update({"h":nifty+12,"l":nifty-18,"fifty":nifty-3,"active":True,"first_done":True,"second_done":True,"high1":nifty+12})

        status = f"3MIN Active={OB3['active']} 50%={OB3['fifty']:.1f} | CE:{ce_ltp} PE:{pe_ltp} | Strike:{strike} | Date:09/09/2026 IST:{now.strftime('%H:%M:%S')}"
        
        html = """
        <html><head><meta http-equiv="refresh" content="5">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>body{background:#000;color:#0f0;font-family:monospace;padding:10px}</style>
        </head><body>
        <h3>STATUS: """ + status + """</h3>
        <div>TRADE: """ + str(TRADE) + """</div>
        <div style="display:flex;gap:10px;margin-top:15px">
            <div style="flex:1;background:#111;border:1px solid #0f0;padding:5px"><b>CE CHART - Order Lagli ki DOT</b><canvas id="ce"></canvas></div>
            <div style="flex:1;background:#111;border:1px solid red;padding:5px"><b>PE CHART - Order Lagli ki DOT</b><canvas id="pe"></canvas></div>
        </div>
        <script>
            let ce=JSON.parse(localStorage.getItem('ce')||'[]'); let pe=JSON.parse(localStorage.getItem('pe')||'[]');
            ce.push(""" + str(ce_ltp) + """); pe.push(""" + str(pe_ltp) + """);
            if(ce.length>30)ce.shift(); if(pe.length>30)pe.shift();
            localStorage.setItem('ce',JSON.stringify(ce)); localStorage.setItem('pe',JSON.stringify(pe));
            new Chart(document.getElementById('ce'),{type:'line',data:{labels:ce.map((_,i)=>i),datasets:[{data:ce,borderColor:'#0f0'}]},options:{animation:false}});
            new Chart(document.getElementById('pe'),{type:'line',data:{labels:pe.map((_,i)=>i),datasets:[{data:pe,borderColor:'#f00'}]},options:{animation:false}});
        </script>
        </body></html>
        """
        return html
    except Exception as e:
        return f"<html><body>Error: {e} <br> Time: {ist_now()} <meta http-equiv='refresh' content='3'></body></html>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
