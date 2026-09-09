# ... varcha sagla same, fakt get_atm_ce ha navin tak

def get_atm_ce(obj, nifty_price):
    strike = int(round(nifty_price/50)*50)
    try:
        for q in [f"NIFTY {strike} CE", f"NIFTY", f"{strike}CE"]:
            try:
                res = obj.searchScrip("NFO", q)
                if res and res.get('data'):
                    for it in res['data']:
                        ts = it.get('tradingsymbol','')
                        if 'CE' in ts and str(strike) in ts and 'NIFTY' in ts:
                            try:
                                sym = it['tradingsymbol']; tok = it['symboltoken']
                                ltp = float(obj.ltpData("NFO", sym, tok)['data']['ltp'])
                                if ltp>2:
                                    return sym, tok, ltp, strike
                            except: continue
            except: continue
        return None, None, 0, strike
    except:
        return None, None, 0, strike
