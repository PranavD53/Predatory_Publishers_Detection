import os

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort

from predatory_detector.model import predict_journal
from predatory_detector.database import (
    init_db,
    save_prediction,
    get_recent_predictions_for_user,
    verify_user_credentials,
    create_user,
    list_users,
    update_user_role,
    get_user_by_id,
)


def create_app() -> Flask:
    app = Flask(__name__)
    # app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-in-production")

    init_db()

    @app.context_processor
    def inject_user():
        user_id = session.get("user_id")
        if not user_id:
            return {"current_user": None}
        user = get_user_by_id(user_id)
        return {"current_user": user}

    def login_required(role: str | None = None):
        def decorator(fn):
            def wrapper(*args, **kwargs):
                user_id = session.get("user_id")
                if not user_id:
                    return redirect(url_for("login", next=request.path))
                user = get_user_by_id(user_id)
                if not user:
                    session.clear()
                    return redirect(url_for("login", next=request.path))
                if role and user.get("role") != role:
                    abort(403)
                return fn(*args, **kwargs)

            wrapper.__name__ = fn.__name__
            return wrapper

        return decorator

    @app.route("/")
    def index():
        user_id = session.get("user_id")
        recent = get_recent_predictions_for_user(user_id, limit=5) if user_id else []
        return render_template("index.html", recent_predictions=recent)

    @app.route("/analyze", methods=["POST"])
    def analyze():
        data = request.get_json() or {}
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"error": "Journal URL is required."}), 400

        try:
            result = predict_journal(url)
            user_id = session.get("user_id")
            # Guest predictions are not tied to any user; admins cannot see user content.
            save_prediction(
                url=url,
                risk_score=float(result["risk_score"]),
                label=result["label"],
                confidence=float(result["confidence"]),
                user_id=user_id,
            )
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            user = verify_user_credentials(username, password)
            if not user:
                return render_template(
                    "login.html", error="Invalid credentials.", show_guest=True
                )
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        return render_template("login.html", show_guest=True)

    @app.route("/guest")
    def guest_mode():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            if not username or not password:
                return render_template(
                    "signup.html",
                    error="Username and password are required.",
                )
            try:
                create_user(username, password, role="user")
            except Exception:
                return render_template(
                    "signup.html",
                    error="Username already exists.",
                )
            return redirect(url_for("login"))
        return render_template("signup.html")

    @app.route("/admin", methods=["GET", "POST"])
    @login_required(role="admin")
    def admin_dashboard():
        if request.method == "POST":
            target_id = int(request.form.get("user_id"))
            new_role = request.form.get("role")
            if new_role not in {"admin", "user"}:
                abort(400)
            update_user_role(target_id, new_role)
            return redirect(url_for("admin_dashboard"))

        users = list_users()
        return render_template("admin.html", users=users)

    @app.route("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok"}, 200

    return app


if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(debug=False)

