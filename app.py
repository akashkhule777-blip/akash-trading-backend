from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

latest_ltp = {"price": 0, "time": 0}
import time

@app.route('/')
def home():
    return "Backend Running"

@app.route('/set_ltp')
def set_ltp():
    global latest_ltp
    try:
        price = request.args.get('price')
        if price:
            latest_ltp["price"] = float(price)
            latest_ltp["time"] = time.time()
            print(f"LTP SET: {price}")
            return f"OK {price}", 200
        return "No price", 400
    except Exception as e:
        print(f"Error in set_ltp: {e}")
        return str(e), 500

@app.route('/get_ltp')
def get_ltp():
    return jsonify(latest_ltp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
