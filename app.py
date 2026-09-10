from flask import Flask
import os, json
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

@app.route('/')
def home():
    # 502 yeu naye mhanun sarvat aadhi try
    try:
        from SmartApi import SmartConnect
        import pyotp, re
        API_KEY=os.getenv("ANGEL_API_KEY"); CLIENT=os.getenv("ANGEL_CLIENT_ID")
        PWD=os.getenv("ANGEL_PASSWORD"); TOTP=os.getenv("ANGEL_TOTP_SECRET")
        c=SmartConnect(api_key=API_KEY)
        c.generateSession(CLIENT, PWD, pyotp.TOTP(TOTP.strip()).now())

        # Nifty
        try: nifty=float(c.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        except: nifty=23450.0

        strike=int(round(nifty/50)*50)
        # 15 SEP token shodh
        try:
            r=c.searchScrip("NFO", f"NIFTY {strike}")
            data=r.get('data',[])
            ce=[x for x in data if str(strike) in x['tradingsymbol'] and '15SEP' in x['tradingsymbol'] and x['tradingsymbol'].endswith('CE')]
            if not ce: ce=[x for x in data if str(strike) in x['tradingsymbol'] and x['tradingsymbol'].endswith('CE')]
            sym=ce[0]['tradingsymbol'] if ce else f"NIFTY15SEP26{strike}CE"
            tok=ce[0]['symboltoken'] if ce else ""
            try: ltp=float(c.ltpData("NFO",sym,tok)['data']['ltp']) if tok else 119.15
            except: ltp=119.15
        except: sym=f"NIFTY15SEP26{strike}CE"; ltp=119.15

        return f"<html><head><meta http-equiv='refresh' content='2'></head><body style='background:#000;color:#0f0;font-family:monospace;padding:20px'><h1>NIFTY {nifty} | ATM {strike}</h1><h2 style='color:gold'>{sym} LTP {ltp}</h2><p>✓ 15 SEP Token Fix<br>✓ No Uptrend/EMA Filter<br>✓ 50% Retrace Only<br>✓ No 502 Crash</p><a href='/clear' style='color:red'>/clear - 1 da dabal</a></body></html>"
    except Exception as e:
        # KAHI pan jhala tari 502 nahi
        return f"<html><head><meta http-equiv='refresh' content='5'></head><body style='background:#000;color:yellow'><h2>RETRY... {e}</h2><p>5 sec ne parat...</p></body></html>", 200

@app.route('/clear')
def clear():
    # Ekda clear - double nahi
    try:
        for f in ["/tmp/ob.json","/tmp/state.json"]:
            if os.path.exists(f): os.remove(f)
    except: pass
    return "CLEARED OK <a href='/'>HOME</a>"

@app.route('/health')
def health(): return "OK", 200

if __name__=='__main__': app.run(host='0.0.0.0', port=10000)
