from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "Akash Trading Backend LIVE Ahe!"

@app.route('/api/status')
def status():
    return {"status": "LIVE", "user": "Akash Khule"}

if __name__ == '__main__':
    app.run()
