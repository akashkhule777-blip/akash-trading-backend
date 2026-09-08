def get_ltp():
    # 1. Angel One LTP
    try:
        if smart:
            d=smart.ltpData("NSE","Nifty 50","99926000")
            if d and d.get('data'):
                p=d['data'].get('ltp')
                if p and float(p)>1000:
                    v=float(p)
                    state["msg"]=f"Angel LTP {v}"
                    return v
            d=smart.ltpData("NSE","Nifty 50","26000")
            if d and d.get('data'):
                p=d['data'].get('ltp')
                if p and float(p)>1000:
                    v=float(p)
                    state["msg"]=f"Angel 26000 LTP {v}"
                    return v
    except Exception as e:
        state["msg"]=f"A-Err {str(e)[:50]}"

    # 2. NSE with Session - bypass block
    try:
        sess=requests.Session()
        sess.headers.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0", "Accept":"*/*"})
        sess.get("https://www.nseindia.com", timeout=8)
        r=sess.get("https://www.nseindia.com/api/allIndices", timeout=8)
        if r.status_code==200:
            for idx in r.json().get('data',[]):
                if idx.get('index')=='NIFTY 50':
                    v=float(idx.get('last',0))
                    if v>1000:
                        state["msg"]=f"NSE LTP {v}"
                        return v
        r=sess.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", timeout=8)
        if r.status_code==200:
            v=float(r.json()['records']['underlyingValue'])
            if v>1000:
                state["msg"]=f"NSE-OC LTP {v}"
                return v
    except Exception as e:
        state["msg"]=f"NSE-Err {str(e)[:50]}"

    # 3. Yahoo Finance - most stable for US server
    try:
        h={"User-Agent":"Mozilla/5.0"}
        r=requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m", headers=h, timeout=8)
        j=r.json()
        v=float(j['chart']['result'][0]['meta']['regularMarketPrice'])
        if v>1000:
            state["msg"]=f"Yahoo LTP {v}"
            return v
    except Exception as e:
        state["msg"]=f"Y-Err {str(e)[:50]}"

    # 4. MoneyControl backup
    try:
        r=requests.get("https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/NIFTY", headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
        j=r.json()
        v=float(j['data']['pricecurrent'])
        if v>1000:
            state["msg"]=f"MC LTP {v}"
            return v
    except Exception as e:
        state["msg"]=f"Final Err {e} | Trying..."
    return 0
