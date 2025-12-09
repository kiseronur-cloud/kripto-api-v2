from flask import Flask, request, jsonify, Response
from flasgger import Swagger
import logging
import requests
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

app = Flask(__name__)

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
        "description": "Gerçek zamanlı kripto veri API'si",
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

swagger = Swagger(app, config=swagger_config, template=swagger_template)


@app.before_request
def check_api_key():
    # Swagger UI ve JSON spec için kontrolü atla
    if request.path.startswith("/apidocs") or request.path.startswith("/apispec"):
        return
    # API key kontrolü
    if request.headers.get("X-API-KEY") != "onur123":
        return jsonify({"error": "Geçersiz API anahtarı"}), 401


@app.route("/")
def get_():
    """
    Ana karşılama endpoint'i
    ---
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: API çalışıyor mesajı
        content:
          text/html:
            schema:
              type: string
    """
    return "API çalışıyor! Hoş geldin Onur 👋"


@app.route("/export/csv")
def export_csv():
    """
    Örnek CSV veri çıktısı
    ---
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: CSV dosyası olarak örnek veri
        content:
          text/csv:
            schema:
              type: string
              format: binary
    """
    data = [
        ["id", "coin", "price"],
        [1, "Bitcoin", 43000],
        [2, "Ethereum", 2300],
        [3, "Solana", 95]
    ]

    def generate():
        for row in data:
            yield ",".join(map(str, row)) + "\n"

    return Response(generate(), mimetype="text/csv")


@app.route("/export/pdf")
def export_pdf():
    """
    Örnek PDF veri çıktısı
    ---
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: PDF dosyası olarak örnek veri
        content:
          application/pdf:
            schema:
              type: string
              format: binary
    """
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    data = [
        ["id", "coin", "price"],
        [1, "Bitcoin", 43000],
        [2, "Ethereum", 2300],
        [3, "Solana", 95]
    ]

    x, y = 50, 750
    for row in data:
        p.drawString(x, y, "   ".join(map(str, row)))
        y -= 20

    p.showPage()
    p.save()
    buffer.seek(0)

    return Response(buffer, mimetype='application/pdf', headers={
        "Content-Disposition": "attachment;filename=kripto-veri.pdf"
    })


@app.route("/live/prices")
def live_prices():
    """
    Canlı kripto para fiyatları (CoinGecko API üzerinden)
    ---
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: Canlı fiyat verisi
        content:
          application/json:
            schema:
              type: object
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin,ethereum,solana",
        "vs_currencies": "usd"
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}, 500


@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Unhandled Exception:")
    return {"error": str(e)}, 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
