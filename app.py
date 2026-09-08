from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "BOT LIVE - 3Min 0/10 | 5Min 0/10 | Total 0/20 | LOT 65"

@app.route('/check')
def check():
    return "Check OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
