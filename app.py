import logging
import csv
from flask import Flask, request, abort, Response
from flasgger import Swagger

app = Flask(__name__)

API_KEY = "onur123"

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Kripto API",
        "description": "Swagger UI ile test edilebilir, API key korumalı örnek API",
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

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec_1',
            "route": '/apispec_1.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/"
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

@app.before_request
def log_and_auth():
    logging.info(f"Request: {request.method} {request.path} | IP: {request.remote_addr}")
    if request.path != "/" and not request.path.startswith("/flasgger_static") and not request.path.startswith("/apispec_"):
        key = request.headers.get("X-API-KEY")
        if key != API_KEY:
            logging.warning("Unauthorized access attempt")
            abort(401, description="Geçersiz API anahtarı")

@app.route("/")
def home():
    """
    Ana karşılama endpoint'i
    ---
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: API çalışıyor mesajı
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

@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Unhandled Exception:")
    return {"error": str(e)}, 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
