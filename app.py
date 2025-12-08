import logging
from flask import Flask, request
from flasgger import Swagger

app = Flask(__name__)
swagger = Swagger(app)

# Logging yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

@app.before_request
def log_request_info():
    logging.info(f"Request: {request.method} {request.path} | IP: {request.remote_addr}")

@app.route("/")
def home():
    """
    Ana karşılama endpoint'i
    ---
    responses:
      200:
        description: API çalışıyor mesajı
    """
    return "API çalışıyor! Hoş geldin Onur 👋"

@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Unhandled Exception:")
    return {"error": str(e)}, 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
