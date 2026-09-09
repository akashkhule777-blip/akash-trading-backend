from flask import Flask, request, jsonify
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

latest_data = {"price": 25100.0, "time": time.time()}

@app.route('/')
def home():
    return "Backend Live - Akash Trading"

@app.route('/set_ltp')
def set_ltp():
    price = request.args.get('price')
    if not price:
        return "No price", 400
    try:
        latest_data["price"] = float(price)
        latest_data["time"] = time.time()
        print(f"LTP Updated: {price}")
        return f"OK {price}", 200
    except Exception as e:
        return str(e), 500

@app.route('/get_ltp')
def get_ltp():
    return jsonify(latest_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
