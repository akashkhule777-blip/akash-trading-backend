def get_atm_ce(obj, nifty):
    try:
        strike = round(nifty/50)*50
        res = obj.searchScrip("NFO", f"NIFTY {strike} CE")
        if not res or 'data' not in res or not res['data']:
            return None, None, 0, strike
        # data list asel tarach ghe
        first = res['data'][0]
        if isinstance(first, dict):
            sym = first.get('symbol'); tok = first.get('symboltoken')
            try:
                ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
            except:
                ltp = 100 # market band sathi dummy
            return sym, tok, ltp, strike
        return None, None, 0, strike
    except Exception as e:
        print(f"CE Fetch Fail {e}")
        return None, None, 0, round(nifty/50)*50

# --- ENTRY Logic madhe he add kar ---
# if ke adhi check tak
        status_text = f"Waiting 50% {OB['fifty']:.1f}"

        if ce_sym is None:
            status_text = f"Market Closed - ATM Token Nahi (OB Active {OB['fifty']:.1f}) - Real BUY Market Hours Madhech Hoil"
        elif OB["active"] and not POS["active"] and abs(nifty - OB["fifty"]) < 6 and OB["fifty"]!=0:
            #... tujha BUY code
