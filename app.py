import os

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort

from predatory_detector.database import (
    init_db,
    save_prediction,
    get_recent_predictions_for_user,
    get_all_recent_predictions,
    delete_prediction_by_id,
    delete_predictions_by_ids,
    clear_predictions_for_user,
    clear_all_predictions,
    verify_user_credentials,
    create_user,
    list_users,
    update_user_role,
    get_user_by_id,
    delete_user_by_id,
    submit_admin_request,
    handle_admin_request,
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "9f2c4a8b7d6e1f3a5c8d2b7e4f9a1c3d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b")

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
        # Lazy import so web workers can boot quickly on platforms like Render.
        from predatory_detector.model import predict_journal

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
            action = request.form.get("action")
            if action in {"approve", "reject", "revoke"}:
                handle_admin_request(target_id, action)
            else:
                new_role = request.form.get("role")
                if new_role in {"admin", "user"}:
                    update_user_role(target_id, new_role)
            return redirect(url_for("admin_dashboard"))

        users = list_users()
        return render_template("admin.html", users=users)

    @app.route("/delete-account", methods=["POST"])
    @login_required()
    def delete_account():
        user_id = session.get("user_id")
        delete_user_by_id(user_id)
        session.clear()
        return redirect(url_for("index"))

    @app.route("/request-admin", methods=["POST"])
    @login_required()
    def request_admin():
        user_id = session.get("user_id")
        submit_admin_request(user_id)
        return redirect(url_for("index"))

    @app.route("/history")
    @login_required()
    def history():
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        is_admin = user and user.get("role") == "admin"
        
        # Get query param view ('mine' or 'all')
        view = request.args.get("view", "mine")
        if view == "all" and is_admin:
            predictions = get_all_recent_predictions(limit=200)
        else:
            predictions = get_recent_predictions_for_user(user_id, limit=100)
            view = "mine"
            
        return render_template(
            "history.html",
            predictions=predictions,
            view=view,
            is_admin=is_admin
        )

    @app.route("/delete-history/<int:pred_id>", methods=["POST"])
    @login_required()
    def delete_history_item(pred_id):
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        is_admin = user and user.get("role") == "admin"
        
        # Check prediction ownership
        from predatory_detector.database import get_conn, query_row
        with get_conn() as conn:
            row = query_row(conn, "SELECT user_id FROM predictions WHERE id = ?", (pred_id,))
            
        if not row:
            return redirect(url_for("history"))
            
        pred_user_id = row[0]
        if pred_user_id != user_id and not is_admin:
            abort(403)
            
        delete_prediction_by_id(pred_id)
        
        view = request.args.get("view", "mine")
        return redirect(url_for("history", view=view))

    @app.route("/clear-history", methods=["POST"])
    @login_required()
    def clear_history():
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        is_admin = user and user.get("role") == "admin"
        
        scope = request.form.get("scope", "user")
        if scope == "all":
            if not is_admin:
                abort(403)
            clear_all_predictions()
            return redirect(url_for("history", view="all"))
        else:
            clear_predictions_for_user(user_id)
            return redirect(url_for("history", view="mine"))

    @app.route("/delete-history-multiple", methods=["POST"])
    @login_required()
    def delete_history_multiple():
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        is_admin = user and user.get("role") == "admin"
        
        ids_str = request.form.get("prediction_ids", "")
        if not ids_str:
            view = request.form.get("view", "mine")
            return redirect(url_for("history", view=view))
            
        try:
            pred_ids = [int(x) for x in ids_str.split(",") if x.strip()]
        except ValueError:
            abort(400)
            
        if not pred_ids:
            view = request.form.get("view", "mine")
            return redirect(url_for("history", view=view))
            
        # Verify ownership / admin rights for each prediction ID
        from predatory_detector.database import get_conn, query_rows
        placeholders = ",".join(["?"] * len(pred_ids))
        with get_conn() as conn:
            rows = query_rows(conn, f"SELECT id, user_id FROM predictions WHERE id IN ({placeholders})", tuple(pred_ids))
            
        valid_ids = []
        for row in rows:
            # row can be indexed by key
            pid = row["id"]
            p_uid = row["user_id"]
            if p_uid == user_id or is_admin:
                valid_ids.append(pid)
                
        if valid_ids:
            delete_predictions_by_ids(valid_ids)
            
        view = request.form.get("view", "mine")
        return redirect(url_for("history", view=view))

    @app.route("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok"}, 200

    return app


if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)

