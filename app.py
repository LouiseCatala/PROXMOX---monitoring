import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import psutil
from flask import Flask, jsonify
from waitress import serve

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(status="ok", node=socket.gethostname())


@app.get("/api/metrics")
def metrics():
    disk_path = Path.home().anchor
    return jsonify(
        node=socket.gethostname(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        cpu=psutil.cpu_percent(interval=1),
        ram=psutil.virtual_memory().percent,
        disk=psutil.disk_usage(disk_path).percent,
    )


@app.get("/")
def dashboard():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Monitoring Dashboard</title>
<style>
body { background:#111827; color:white; font-family:Arial;
       max-width:800px; margin:60px auto; padding:20px; }
.cards { display:flex; gap:20px; flex-wrap:wrap; }
.card { background:#1f2937; padding:25px; border-radius:12px;
        min-width:150px; }
.value { font-size:36px; font-weight:bold; }
#status { color:#cbd5e1; }
</style>
</head>
<body>
<h1>Monitoring Dashboard</h1>
<p id="node">Connecting...</p>
<div class="cards">
  <div class="card">CPU<p class="value" id="cpu">—</p></div>
  <div class="card">RAM<p class="value" id="ram">—</p></div>
  <div class="card">Disk<p class="value" id="disk">—</p></div>
</div>
<p id="status"></p>
<script>
function color(value, limits) {
  if (value >= limits[2]) return "#f87171";
  if (value >= limits[1]) return "#fb923c";
  if (value >= limits[0]) return "#facc15";
  return "#4ade80";
}
async function refresh() {
  try {
    const response = await fetch("/api/metrics", {
      cache: "no-store",
      signal: AbortSignal.timeout(10000)
    });
    if (!response.ok) throw new Error("Request failed");
    const data = await response.json();
    document.getElementById("node").textContent = data.node;
    for (const name of ["cpu", "ram", "disk"]) {
      const element = document.getElementById(name);
      element.textContent = data[name].toFixed(1) + "%";
      element.style.color = color(
        data[name], name === "disk" ? [60,75,90] : [60,70,85]
      );
    }
    document.getElementById("status").textContent =
      "Updated: " + new Date(data.timestamp).toLocaleTimeString();
  } catch (error) {
    document.getElementById("status").textContent =
      "Connection failed. Displayed values may be outdated.";
  } finally {
    setTimeout(refresh, 5000);
  }
}
refresh();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print("Open http://127.0.0.1:5123", flush=True)
    serve(app, host="127.0.0.1", port=5123)