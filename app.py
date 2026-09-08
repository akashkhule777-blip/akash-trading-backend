from flask import Flask, jsonify, request
from SmartApi import SmartConnect
import pyotp, os, time, threading
from datetime import datetime

app = Flask(__name__)

# ===== TUJHE SETUP =====
LOT = 65
MAX_3MIN = 10
MAX_5MIN = 10
count_3min = 0
count_5min = 0

# Angel Creds - Render > Environment madhe takayche aahet
API_KEY = os.getenv("API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
PASSWORD = os.getenv("PASSWORD")
TOTP_SECRET = os.getenv("TOTP_SECRET")

def get_ema(candles, period=20):
    if len(candles) < period: return candles[-1]['close']
    k = 2/(period+1)
    ema = candles[0]['close']
    for c in candles[1:]:
        ema = c['close']*k + ema*(1-k)
    return ema

def check_logic(candles):
    # C1 GREEN + C2 GREEN + Close > EMA20
    if len(candles) < 25: return False
    c1, c2 = candles[-2], candles[-1]
    ema20 = get_ema(candles[-25:], 20)
    if c1['close'] <= c1['open']: return False # C1 green pahije
    if c2['close'] <= c1['close']: return False # C2 ne C1 chya upar close
    if c2['close'] <= ema20: return False # EMA20 filter
    # 50% Retest logic
    c1_mid = (c1['high'] + c1['low']) / 2
    return True, c1_mid, c1['low'] # Entry, SL

@app.route('/')
def home():
    total = count_3min + count_5min
    return f"BOT LIVE | 3Min: {count_3min}/{MAX_3MIN} | 5Min: {count_5min}/{MAX_5MIN} | Total {total}/20 | Angel API: {'Connected' if API_KEY else 'ENV Missing'} | Logic: Option ATM 50% Retest + EMA20"

@app.route('/check')
def check_status():
    return jsonify({"3min":count_3min,"5min":count_5min,"total":count_3min+count_5min,"api_key_set":bool(API_KEY)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
