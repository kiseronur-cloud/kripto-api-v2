# app.py
# Kripto API (Flask + Flasgger v2 UI + Binance Futures USDT pariteleri)
# Stabil güvenlik akışı: static & docs whitelisti, public endpointler serbest, diğerleri API key ile korumalı.

import os
import csv
import io
import time
import logging
from typing import Dict, List, Optional

import requests
from flask import Flask, jsonify, request, Response
from flasgger import Swagger

# ------------------------------------------------------------
# Uygulama ve Logger
# ------------------------------------------------------------
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("kripto-api")

# ------------------------------------------------------------
# Swagger UI yapılandırması
# ------------------------------------------------------------
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
        "APIKeyHeader": {
            "type": "apiKey",
            "name": "X-API-KEY",
            "in": "header"
        }
    }
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Kripto API",
        "description": "Gerçek zamanlı kripto API (Binance Futures USDT pariteleri, health ve CSV export)",
        "version": "1.1.0"
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

# ------------------------------------------------------------
# Güvenlik: Basit API key (docs ve swagger statikleri hariç)
# ------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "onur123")

# Whitelist setleri (tam yollar ve prefixler)
DOC_EXACT = ("/apidocs", "/apispec.json")
DOC_PREFIX = ("/apidocs/", "/flasgger_static/")
STATIC_PREFIX = ("/static/",)  # Flask static
PUBLIC_EXACT = ("/", "/health")

@app.before_request
def check_api_key():
    path = request.path or "/"

    # Statik dosyalar serbest
    if any(path.startswith(p) for p in STATIC_PREFIX):
        return

    # Flasgger statikleri ve docs serbest
    if (path in DOC_EXACT) or any(path.startswith(p) for p in DOC_PREFIX):
        return

    # Public endpointler serbest
    if path in PUBLIC_EXACT:
        return

    # Diğer tüm yollar API key ister
    key = request.headers.get("X-API-KEY")
    if key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

# ------------------------------------------------------------
# Sağlık kontrolü (public)
# ------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "time": int(time.time() * 1000)
    })

# ------------------------------------------------------------
# Binance Futures istemci yardımcıları
# ------------------------------------------------------------
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
            out[sym] = {
                "error": data.get("error", "no lastPrice"),
                "usdt.p": None
            }
    return out

# ------------------------------------------------------------
# Canlı fiyatlar (korumalı)
# ------------------------------------------------------------
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

@app.route("/live/prices", methods=["GET"])
def live_prices():
    q = request.args.get("symbols", "")
    if q.strip():
        symbols = [s.strip().upper() for s in q.split(",") if s.strip()]
    else:
        symbols = list(DEFAULT_SYMBOLS)

    prices = collect_binance_usdt_prices(symbols)

    if all(v.get("usdt.p") is None for v in prices.values()):
        return jsonify({"error": "Binance data unavailable", "details": prices}), 502

    return jsonify(prices), 200

# ------------------------------------------------------------
# CSV export (korumalı)
# ------------------------------------------------------------
@app.route("/export/csv", methods=["GET"])
def export_csv():
    q = request.args.get("symbols", "")
    if q.strip():
        symbols = [s.strip().upper() for s in q.split(",") if s.strip()]
    else:
        symbols = list(DEFAULT_SYMBOLS)

    prices = collect_binance_usdt_prices(symbols)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["symbol", "usdt.p", "ts"])
    for sym in symbols:
        row = prices.get(sym, {})
        writer.writerow([sym, row.get("usdt.p"), row.get("ts")])

    csv_data = buf.getvalue()
    buf.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=prices.csv"}
    )

# ------------------------------------------------------------
# Ana sayfa (public)
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "name": "Kripto API",
        "docs": "/apidocs/",
        "live_prices": "/live/prices",
        "export_csv": "/export/csv"
    })

# ------------------------------------------------------------
# Run
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
