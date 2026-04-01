from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/api/health")
def health():
    return jsonify(status="ok", service="backend")


@app.route("/api/hello")
def hello():
    return jsonify(message="Hello from the backend")
