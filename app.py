# app.py
# Kripto API (Flask + Flasgger v3 UI + Binance Futures USDT pariteleri)
# Güvenli, üretim uyumlu, minimalist ama tamamlayıcı özelliklerle (health, csv export) hazır sürüm.

import os
import csv
import io
import time
import json
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
    # Docs ve health’i opsiyonel olarak serbest bırak
    # Health’i kamuya kapatmak istersen 'health' ekleme.
    allowed = set(DOCS_ENDPOINTS)
    endpoint = request.endpoint or ""
    if endpoint in allowed:
        return

    key = request.headers.get("X-API-KEY")
    if key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

# ------------------------------------------------------------
# Sağlık kontrolü (opsiyonel olarak serbest)
# ------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    """
    Servis sağlık kontrolü
    ---
    tags:
      - Sistem
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
    """
    Binance Futures 24hr ticker endpointinden tek sembol için veri çeker.
    Basit retry ve timeout içerir.
    """
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(BINANCE_FAPI_24HR, params={"symbol": symbol}, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return data
        except Exception as e:
            last_err = e
            logger.warning(f"Binance fetch error for {symbol} (attempt {attempt+1}): {e}")
            time.sleep(0.2)
    return {"error": str(last_err) if last_err else "unknown error"}

def collect_binance_usdt_prices(symbols: List[str]) -> Dict[str, Dict]:
    """
    Semboller için toplu istek yapar ve çıktıyı {SYMBOL: {"usdt.p": price, "ts": ...}} formatına normalleştirir.
    """
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
    parameters:
      - in: query
        name: symbols
        type: string
        required: false
        description: Virgülle ayrılmış semboller (örn. BTCUSDT,ETHUSDT)
    responses:
      200:
        description: USDT pariteleri son fiyat bilgisi
        examples:
          application/json:
            BTCUSDT: {"usdt.p": "68234.12", "ts": 1733792110000}
            ETHUSDT: {"usdt.p": "3567.22", "ts": 1733792110000}
    """
    # Query ile sembolleri özelleştirme (örn. ?symbols=BTCUSDT,BNBUSDT)
    q = request.args.get("symbols", "")
    if q.strip():
        symbols = [s.strip().upper() for s in q.split(",") if s.strip()]
    else:
        symbols = list(DEFAULT_SYMBOLS)

    prices = collect_binance_usdt_prices(symbols)

    # Tamamı hatalıysa anlaşılır yanıt ver
    if all(v.get("usdt.p") is None for v in prices.values()):
        return jsonify({"error": "Binance data unavailable", "details": prices}), 502

    return jsonify(prices), 200

# ------------------------------------------------------------
# CSV export (canlı fiyatlardan CSV üretir)
# ------------------------------------------------------------
@app.route("/export/csv", methods=["GET"])
def export_csv():
    """
    Canlı fiyatları CSV olarak döndür
    ---
    tags:
      - Veri
    parameters:
      - in: query
        name: symbols
        type: string
        required: false
        description: Virgülle ayrılmış semboller (örn. BTCUSDT,ETHUSDT)
    responses:
      200:
        description: CSV dosyası olarak çıktı
        schema:
          type: string
          format: binary
    """
    q = request.args.get("symbols", "")
    if q.strip():
        symbols = [s.strip().upper() for s in q.split(",") if s.strip()]
    else:
        symbols = list(DEFAULT_SYMBOLS)

    prices = collect_binance_usdt_prices(symbols)

    # CSV oluştur
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
        headers={
            "Content-Disposition": "attachment; filename=prices.csv"
        }
    )

# ------------------------------------------------------------
# Ana sayfa: basit bilgi (401 beklenir, docs açık)
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """
    Basit bilgi
    ---
    tags:
      - Sistem
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
# Üretim uyumlu run
# ------------------------------------------------------------
if __name__ == "__main__":
    # Render varsayılan portu: 10000 (service logs'ta görünüyor)
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
