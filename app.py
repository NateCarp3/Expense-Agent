"""Expense Agent — Flask backend.

Serves the single-page app, stores the ledger in Postgres (SQLite locally),
protects everything behind one password, and proxies PDF reading /
categorization requests to the Anthropic API so the key never reaches the browser.
"""
import hmac
import json
import os
from datetime import timedelta
from functools import wraps

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER") is not None  # https on Render
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

db_url = os.environ.get("DATABASE_URL", "sqlite:///expenses.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db = SQLAlchemy(app)

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODELS = {
    "quick": os.environ.get("MODEL_QUICK", "claude-haiku-5-5"),
    "default": os.environ.get("MODEL_DEFAULT", "claude-sonnet-5-5"),
    "complex": os.environ.get("MODEL_DEFAULT", "claude-sonnet-5-5"),
}


class Doc(db.Model):
    """One JSON document: 'settings' or a month of transactions ('m-2026-10')."""
    id = db.Column(db.String(64), primary_key=True)
    body = db.Column(db.Text, nullable=False)


with app.app_context():
    db.create_all()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("ok"):
            if request.path.startswith("/api/"):
                return jsonify(error="login required"), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if not APP_PASSWORD:
        error = "APP_PASSWORD isn't set on the server yet."
    elif request.method == "POST":
        if hmac.compare_digest(request.form.get("password", "").encode(), APP_PASSWORD.encode()):
            session.permanent = True
            session["ok"] = True
            return redirect(url_for("index"))
        error = "Wrong password."
    return render_template("login.html", error=error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    resp = send_from_directory(app.template_folder, "index.html")
    resp.headers["Cache-Control"] = "no-store"  # always load the latest version after a deploy
    return resp


@app.get("/healthz")
def healthz():
    return "ok"


# ---- document store -------------------------------------------------------
def valid_id(doc_id):
    return doc_id == "settings" or (doc_id.startswith("m-") and len(doc_id) <= 16)


@app.get("/api/docs")
@login_required
def list_docs():
    return jsonify([{"id": d.id, "data": json.loads(d.body)} for d in Doc.query.all()])


@app.put("/api/docs/<doc_id>")
@login_required
def put_doc(doc_id):
    if not valid_id(doc_id):
        abort(400)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    doc = db.session.get(Doc, doc_id) or Doc(id=doc_id)
    doc.body = json.dumps(data)
    db.session.add(doc)
    db.session.commit()
    return jsonify(ok=True)


@app.delete("/api/docs/<doc_id>")
@login_required
def delete_doc(doc_id):
    doc = db.session.get(Doc, doc_id)
    if doc:
        db.session.delete(doc)
        db.session.commit()
    return jsonify(ok=True)


# ---- Claude proxy ---------------------------------------------------------
@app.post("/api/claude")
@login_required
def ask_claude():
    if not ANTHROPIC_API_KEY:
        return jsonify(code="not_granted", message="ANTHROPIC_API_KEY isn't set on the server."), 503
    payload = request.get_json(silent=True) or {}
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt or len(prompt) > 60000:
        abort(400)
    model = MODELS.get(payload.get("tier") or "default", MODELS["default"])

    import anthropic  # imported lazily so the app starts without the key

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError:
        return jsonify(code="rate_limited", message="Rate limited, try again shortly."), 429
    except anthropic.APIError as e:
        app.logger.warning("Anthropic error: %s", e)
        return jsonify(code="unavailable", message="Claude request failed."), 502
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return jsonify(text=text, truncated=msg.stop_reason == "max_tokens")


if __name__ == "__main__":
    app.run(debug=True)
