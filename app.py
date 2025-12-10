# app.py
# Kripto API (Flask + Flasgger v2 UI + Binance Futures USDT pariteleri)

import os
import csv
import io
import time
import logging
from typing import Dict, List, Optional

import requests
from flask import Flask, jsonify, request, Response
from flasgger import Swagger

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kripto-api")

# ----------------------------- Swagger config -----------------------------
app.config["SWAGGER"] = {
    "title": "Kripto API",
    "uiversion": 2,
    "specs_route": "/apidocs/"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Kripto API",
        "description": "Gerçek zamanlı kripto API (Binance Futures USDT pariteleri, health ve CSV export)",
        "version": "1.1.5"
    },
    # Yerelde çalıştırıyorsan burası localhost:10000
    # Render’da deploy ettiğinde host'u kripto-api-v2.onrender.com yapmalısın
    "host": "127.0.0.1:10000",
    "basePath": "/",
    "schemes": ["http"],
    "tags": [
        {"name": "Sistem", "description": "Health ve durum"},
        {"name": "Veri", "description": "Canlı fiyatlar ve export"}
    ]
}

swagger = Swagger(app, template=swagger_template)

# ----------------------------- Security whitelist -----------------------------
API_KEY = os.getenv("API_KEY", "onur123")

@app.before_request
def check_api_key():
    path = request.path or "/"
    if path in ("/", "/health", "/apidocs", "/apispec.json") or path.startswith("/apidocs/"):
        return
    key = request.headers.get("X-API-KEY")
    if key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

# ----------------------------- Health (public) -----------------------------
@app.route("/health", methods=["GET"])
def health():
    """
    Sistem durumu
    ---
    tags:
      - Sistem
    responses:
      200:
        description: Sağlık durumu
    """
    return jsonify({"status": "ok", "time": int(time.time() * 1000)})

# ----------------------------- Binance helpers -----------------------------
BINANCE_FAPI_24HR = "https://fapi.binance.com/fapi/v1/ticker/24hr"

def fetch_binance_24hr(symbol: str) -> Dict:
    try:
        r = requests.get(BINANCE_FAPI_24HR, params={"symbol": symbol}, timeout=6)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def collect_binance_usdt_prices(symbols: List[str]) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for sym in symbols:
        data = fetch_binance_24hr(sym)
        if "lastPrice" in data:
            out[sym] = {"usdt.p": data["lastPrice"], "ts": data.get("closeTime")}
        else:
            out[sym] = {"error": data.get("error", "no lastPrice"), "usdt.p": None}
    return out

# ----------------------------- Live prices (protected) -----------------------------
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

@app.route("/live/prices", methods=["GET"])
def live_prices():
    """
    Canlı fiyatları getirir
    ---
    tags:
      - Veri
    parameters:
      - name: symbols
        in: query
        type: string
        required: false
        description: Virgülle ayrılmış semboller (örn: BTCUSDT,ETHUSDT)
    responses:
      200:
        description: Başarılı yanıt
    """
    q = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in q.split(",") if s.strip()] if q.strip() else DEFAULT_SYMBOLS
    prices = collect_binance_usdt_prices(symbols)
    return jsonify(prices), 200

# ----------------------------- CSV export (protected) -----------------------------
@app.route("/export/csv", methods=["GET"])
def export_csv():
    """
    Fiyatları CSV olarak dışa aktarır
    ---
    tags:
      - Veri
    parameters:
      - name: symbols
        in: query
        type: string
        required: false
        description: Virgülle ayrılmış semboller
    responses:
      200:
        description: CSV dosyası
    """
    q = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in q.split(",") if s.strip()] if q.strip() else DEFAULT_SYMBOLS
    prices = collect_binance_usdt_prices(symbols)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["symbol", "usdt.p", "ts"])
    for sym in symbols:
        row = prices.get(sym, {})
        writer.writerow([sym, row.get("usdt.p"), row.get("ts")])
    csv_data = buf.getvalue()
    buf.close()
    return Response(csv_data, mimetype="text/csv")

# ----------------------------- Index (public) -----------------------------
@app.route("/", methods=["GET"])
def index():
    """
    Ana sayfa
    ---
    tags:
      - Sistem
    responses:
      200:
        description: API hakkında bilgi
    """
    return jsonify({"name": "Kripto API", "docs": "/apidocs/", "live_prices": "/live/prices", "export_csv": "/export/csv"})

# ----------------------------- Run -----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
