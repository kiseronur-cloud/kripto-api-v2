# app.py
# Kripto API (Flask + Flasgger v3 UI + Binance Futures USDT pariteleri)
# Güvenli, üretim uyumlu, Swagger açıklamaları güncel ve Authorize kutusu aktif.

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
# Swagger UI yapılandırması (v3 ve stabil /apidocs/)
# ------------------------------------------------------------
app.config["SWAGGER"] = {
    "title": "Kripto API",
    "uiversion": 3,
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
    "specs_route": "/apidocs/"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Kripto API",
        "description": "Gerçek zamanlı kripto API (Binance Futures USDT pariteleri, health ve CSV export)",
        "version": "1.0.0"
    },
    "securityDefinitions": {
        "APIKeyHeader": {
            "type": "apiKey",
            "name": "X-API-KEY",
            "in": "header"
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
# Güvenlik: Basit API key (docs endpointleri hariç)
# ------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "onur123")

DOCS_ENDPOINTS = {
    "apidocs",      # Swagger UI
    "apispec"       # /apispec.json
}

@app.before_request
def check_api_key():
    allowed = set(DOCS_ENDPOINTS)
    endpoint = request.endpoint or ""
    if endpoint in allowed:
        return
    key = request.headers.get("X-API-KEY")
    if key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

# ------------------------------------------------------------
# Sağlık kontrolü
# ------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    """
    Servis sağlık kontrolü
    ---
    tags:
      - Sistem
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: Servis ayakta
    """
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
# Canlı fiyatlar (Binance Futures USDT pariteleri)
# ------------------------------------------------------------
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

@app.route("/live/prices", methods=["GET"])
def live_prices():
    """
    Binance Futures USDT pariteleri (gerçek zamanlı)
    ---
    tags:
      - Veri
    security:
      - APIKeyHeader: []
    parameters:
      - in: query
        name: symbols
        type: string
        required: false
        description: Virgülle ayrılmış semboller (örn. BTCUSDT,ETHUSDT)
    responses:
      200:
        description: USDT pariteleri son fiyat bilgisi
    """
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
# CSV export
# ------------------------------------------------------------
@app.route("/export/csv", methods=["GET"])
def export_csv():
    """
    Canlı fiyatları CSV olarak döndür
    ---
    tags:
      - Veri
    security:
      - APIKeyHeader: []
    parameters:
      - in: query
        name: symbols
        type: string
        required: false
        description: Virgülle ayrılmış semboller (örn. BTCUSDT,ETHUSDT)
    responses:
      200:
        description: CSV dosyası olarak çıktı
    """
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
# Ana sayfa
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """
    Basit bilgi
    ---
    tags:
      - Sistem
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: Bilgi
    """
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
