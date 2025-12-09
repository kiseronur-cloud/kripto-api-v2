from flask import Flask, request, jsonify, Response
from flasgger import Swagger
import logging
import requests
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

app = Flask(__name__)

app.config['SWAGGER'] = {
    'title': 'Kripto API',
    'uiversion': 3,
    'specs_route': '/apidocs/'
}

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
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
        "description": "Gerçek zamanlı kripto veri API'si (Binance Futures USDT pariteleri)",
        "version": "1.0"
    },
    "securityDefinitions": {
        "APIKeyHeader": {
            "type": "apiKey",
            "name": "X-API-KEY",
            "in": "header"
        }
    },
    "security": [{"APIKeyHeader": []}]
}

@app.before_request
def check_api_key():
    path = request.path
    if (
        path.startswith("/apidocs") or
        path.startswith("/apispec") or
        path.startswith("/flasgger_static") or
        path.startswith("/apidocs/static") or
        path.startswith("/static") or
        path == "/favicon.ico"
    ):
        return
    if request.headers.get("X-API-KEY") != "onur123":
        return jsonify({"error": "Geçersiz API anahtarı"}), 401

@app.route("/")
def root():
    return "API çalışıyor! Hoş geldin Onur 👋"

@app.route("/export/csv")
def export_csv():
    data = [
        ["id", "coin", "pair"],
        [1, "Bitcoin", "BTCUSDT"],
        [2, "Ethereum", "ETHUSDT"],
        [3, "Solana", "SOLUSDT"],
        [4, "Dogecoin", "DOGEUSDT"],
        [5, "XRP", "XRPUSDT"]
    ]
    def generate():
        for row in data:
            yield ",".join(map(str, row)) + "\n"
    return Response(generate(), mimetype="text/csv")

@app.route("/export/pdf")
def export_pdf():
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    data = [
        ["id", "coin", "pair"],
        [1, "Bitcoin", "BTCUSDT"],
        [2, "Ethereum", "ETHUSDT"],
        [3, "Solana", "SOLUSDT"],
        [4, "Dogecoin", "DOGEUSDT"],
        [5, "XRP", "XRPUSDT"]
    ]
    x, y = 50, 750
    for row in data:
        p.drawString(x, y, "   ".join(map(str, row)))
        y -= 20
    p.showPage()
    p.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={
        "Content-Disposition": "attachment;filename=kripto-pariteler.pdf"
    })

@app.route("/live/prices")
def live_prices():
    """
    Binance Futures USDT paritelerinden canlı fiyatlar
    """
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
    result = {}
    try:
        for sym in symbols:
            response = requests.get(url, params={"symbol": sym}, timeout=5)
            response.raise_for_status()
            data = response.json()
            result[sym] = {"usdt.p": float(data["price"])}
        return result
    except Exception as e:
        return {"error": str(e)}, 500

@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Unhandled Exception:")
    return {"error": str(e)}, 500

swagger = Swagger(app, config=swagger_config, template=swagger_template)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
