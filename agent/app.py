"""Actual Ubuntu VM agent. No simulated readings are generated here."""
import socket
from datetime import datetime, timezone
import psutil
from flask import Flask, jsonify
from waitress import serve

app = Flask(__name__)

@app.get('/health')
def health():
    response = jsonify(status='ok', node=socket.gethostname(),
                       checked=datetime.now(timezone.utc).isoformat())
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/api/metrics')
def metrics():
    cpu = psutil.cpu_percent(interval=1)
    response = jsonify(node=socket.gethostname(),
        checked=datetime.now(timezone.utc).isoformat(), cpu=cpu,
        ram=psutil.virtual_memory().percent,
        disk=psutil.disk_usage('/').percent)
    response.headers['Cache-Control'] = 'no-store'
    return response

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=5123, threads=4)
