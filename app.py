# app.py
# Kripto API (Flask + Flasgger v2 UI + Binance Futures USDT pariteleri)
# Stabil güvenlik akışı ve doğru Swagger host/basePath. Statikler/Docs whitelisti eksiksiz.

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

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "securityDefinitions": {
        "APIKeyHeader": {"type": "apiKey", "name": "X-API-KEY", "in": "header"}
    }
}

# DİKKAT: Buradaki host/basePath/schemes spec içine girer; UI artık placeholder göstermez.
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Kripto API",
        "description": "Gerçek zamanlı kripto API (Binance Futures USDT pariteleri, health ve CSV export)",
        "version": "1.1.1"
    },
    "host": "kripto-api-v2.onrender.com",
    "basePath": "/",
    "schemes": ["https"],
    "securityDefinitions": {
        "APIKeyHeader": {
            "type": "apiKey",
            "name": "X-API-KEY",
            "in": "header",
            "description": "API anahtarınızı bu alana girin (varsayılan: onur123)."
        }
    },
    "security": [{"APIKeyHeader": []}],
    "tags": [
        {"name": "Sistem", "description": "Health ve durum"},
        {"name": "Veri", "description": "Canlı fiyatlar ve export"}
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# ----------------------------- Security whitelist -----------------------------
API_KEY = os.getenv("API_KEY", "onur123")

# Whitelist kümeleri (tam ve prefix bazlı)
DOC_EXACT = ("/apidocs", "/apispec.json")
DOC_PREFIX = ("/apidocs/", "/flasgger_static/")
STATIC_PREFIX = ("/static/",)  # Flask'ın kendi static yolu
PUBLIC_EXACT = ("/", "/health")

@app.before_request
def check_api_key():
    path = request.path or "/"

    # Statikler 200
    if any(path.startswith(p) for p in STATIC_PREFIX):
        return

    # Flasgger statikleri ve doküman yolları 200
    if (path in DOC_EXACT) or any(path.startswith(p) for p in DOC_PREFIX):
        return

    # Public endpointler 200
    if path in PUBLIC_EXACT:
        return

    # Diğer tüm yollar API key ister
    key = request.headers.get("X-API-KEY")
    if key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

# ----------------------------- Health (public) -----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": int(time.time() * 1000)})

# ----------------------------- Binance helpers -----------------------------
BINANCE_FAPI_24HR = "https://fapi.binance.com/fapi/v1/ticker/24hr"

def fetch_binance_24hr(symbol: str, timeout: float = 6.0, retries: int = 2) -> Dict:
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(BINANCE_FAPI_24HR, params={"symbol": symbol}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            logger.warning(f"Binance fetch error for {symbol} (attempt {attempt+1}): {e}")
            time.sleep(0.2)
    return {"error": str(last_err) if last_err else "unknown error"}

def collect_binance_usdt_prices(symbols: List[str]) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for sym in symbols:
        data = fetch_binance_24hr(sym)
        if "lastPrice" in data:
            out[sym] = {
                "usdt.p": data["lastPrice"],
                "ts": data.get("closeTime") or data.get("openTime")
            }
        else:
            out[sym] = {"error": data.get("error", "no lastPrice"), "usdt.p": None}
    return out

# ----------------------------- Live prices (protected) -----------------------------
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

@app.route("/live/prices", methods=["GET"])
def live_prices():
    q = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in q.split(",") if s.strip()] if q.strip() else list(DEFAULT_SYMBOLS)
    prices = collect_binance_usdt_prices(symbols)
    if all(v.get("usdt.p") is None for v in prices.values()):
        return jsonify({"error": "Binance data unavailable", "details": prices}), 502
    return jsonify(prices), 200

# ----------------------------- CSV export (protected) -----------------------------
@app.route("/export/csv", methods=["GET"])
def export_csv():
    q = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in q.split(",") if s.strip()] if q.strip() else list(DEFAULT_SYMBOLS)
    prices = collect_binance_usdt_prices(symbols)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["symbol", "usdt.p", "ts"])
    for sym in symbols:
        row = prices.get(sym, {})
        writer.writerow([sym, row.get("usdt.p"), row.get("ts")])
    csv_data = buf.getvalue()
    buf.close()
    return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=prices.csv"})

# ----------------------------- Index (public) -----------------------------
@app.route("/", methods=["GET"])
def index():
    return jsonify({"name": "Kripto API", "docs": "/apidocs/", "live_prices": "/live/prices", "export_csv": "/export/csv"})

# ----------------------------- Run -----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
