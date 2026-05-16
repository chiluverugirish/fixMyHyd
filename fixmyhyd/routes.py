import os
import secrets
from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from .auth import admin_required, hash_password, user_required, verify_password
from .db import get_db_connection
from .services import process_complaint_submission
from .utils import friendly_error, parse_timestamp


def register_routes(app):
    @app.route("/")
    def home():
        conn = get_db_connection()
        total = conn.fetchscalar("SELECT COUNT(*) FROM complaints")
        resolved = conn.fetchscalar("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'")
        users = conn.fetchscalar("SELECT COUNT(*) FROM users")
        resolution_rate = round((resolved / total * 100) if total > 0 else 0)
        try:
            avg_result = conn.fetchscalar(
                "SELECT AVG(EXTRACT(DAY FROM (updated_at - created_at))) FROM complaints WHERE status = 'Resolved'"
            )
            avg_days = round(avg_result) if avg_result else 0
        except Exception:
            avg_days = 0
        conn.close()
        stats = {
            "total_complaints": total,
            "resolution_rate": resolution_rate,
            "total_users": users,
            "avg_days": avg_days,
        }
        bot_url = os.getenv("TELEGRAM_BOT_URL", "https://t.me/FixMyHyd_bot")
        return render_template("home.html", admin_stats=stats, bot_url=bot_url)

    @app.route("/user/login", methods=["GET", "POST"])
    def user_login():
        if "user_id" in session:
            return redirect(url_for("user_dashboard"))
        if request.method == "POST":
            phone = request.form.get("phone")
            password = request.form.get("password")
            if not phone or not password:
                flash("Please fill in all fields.", "error")
                return render_template("user_login.html")
            conn = get_db_connection()
            user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            conn.close()
            if user and user["password_hash"] and verify_password(password, user["password_hash"]):
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                flash("Login successful!", "success")
                return redirect(url_for("user_dashboard"))
            flash("Invalid phone number or password.", "error")
        return render_template("user_login.html")

    @app.route("/user/register", methods=["GET", "POST"])
    def user_register():
        if request.method == "POST":
            name = request.form.get("name")
            phone = request.form.get("phone")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")
            if not all([name, phone, password]):
                flash("Please fill in all required fields.", "error")
                return render_template("user_register.html")
            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("user_register.html")
            conn = get_db_connection()
            try:
                existing = conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
                if existing:
                    flash("Phone number already registered.", "error")
                    return render_template("user_register.html")
                pw_hash = hash_password(password)
                conn.execute("INSERT INTO users (name, phone, password_hash) VALUES (?, ?, ?)", (name, phone, pw_hash))
                conn.commit()
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for("user_login"))
            except Exception:
                flash("Registration failed. Please try again.", "error")
            finally:
                conn.close()
        return render_template("user_register.html")

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if "admin_id" in session:
            return redirect(url_for("admin_dashboard"))
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            if not username or not password:
                flash("Please fill in all fields.", "error")
                return render_template("admin_login.html")
            try:
                conn = get_db_connection()
                admin = conn.execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
                conn.close()
                if admin:
                    admin = dict(admin)
                    if verify_password(password, admin["password_hash"]):
                        session["admin_id"] = admin["id"]
                        session["admin_name"] = admin["name"]
                        flash("Admin login successful!", "success")
                        return redirect(url_for("admin_dashboard"))
                flash("Invalid username or password.", "error")
            except Exception:
                flash("Database error. Please try again.", "error")
        return render_template("admin_login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("home"))

    @app.route("/user/dashboard")
    @user_required
    def user_dashboard():
        conn = get_db_connection()
        raw = conn.execute(
            "SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (session["user_id"],)
        ).fetchall()
        complaints = []
        for c in raw:
            d = dict(c)
            d["created_at"] = parse_timestamp(d["created_at"])
            d["updated_at"] = parse_timestamp(d.get("updated_at"))
            complaints.append(d)
        total = conn.fetchscalar("SELECT COUNT(*) FROM complaints WHERE user_id = ?", (session["user_id"],))
        pending = conn.fetchscalar(
            "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status IN ('Submitted','In Progress','Acknowledged')",
            (session["user_id"],),
        )
        resolved = conn.fetchscalar(
            "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status = 'Resolved'", (session["user_id"],)
        )
        conn.close()
        stats = {
            "total_complaints": total,
            "pending_complaints": pending,
            "resolved_complaints": resolved,
            "resolution_rate": round((resolved / total * 100) if total > 0 else 0),
        }
        return render_template("user_dashboard.html", user_complaints=complaints, user_stats=stats)

    @app.route("/admin/dashboard")
    @admin_required
    def admin_dashboard():
        conn = get_db_connection()
        raw = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
        complaints = []
        for c in raw:
            d = dict(c)
            d["created_at"] = parse_timestamp(d["created_at"])
            d["updated_at"] = parse_timestamp(d.get("updated_at"))
            complaints.append(d)
        total = conn.fetchscalar("SELECT COUNT(*) FROM complaints")
        pending = conn.fetchscalar("SELECT COUNT(*) FROM complaints WHERE status IN ('Submitted','In Progress','Acknowledged')")
        resolved = conn.fetchscalar("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'")
        conn.close()
        stats = {
            "total_complaints": total,
            "pending_complaints": pending,
            "resolved_complaints": resolved,
            "resolution_rate": round((resolved / total * 100) if total > 0 else 0),
        }
        return render_template("admin_dashboard.html", all_complaints=complaints, admin_stats=stats)

    @app.route("/report-issue")
    @user_required
    def report_issue():
        return render_template("report_issue.html")

    @app.route("/api/report-issue", methods=["POST"])
    @user_required
    def report_issue_endpoint():
        try:
            return process_complaint_submission(
                image_file=request.files.get("image"),
                audio_file=request.files.get("audio"),
                text_description=request.form.get("description", ""),
                device_lat=request.form.get("device_latitude"),
                device_lng=request.form.get("device_longitude"),
                manual_address=request.form.get("location_text"),
                user_id=session.get("user_id"),
                source="portal",
                submitted_by=session.get("user_name", "Citizen"),
            )
        except Exception as e:
            print(f"[ERROR] report_issue_endpoint: {e}")
            return jsonify({"error": friendly_error(e)}), 500

    @app.route("/api/user/complaints")
    @user_required
    def get_user_complaints():
        conn = get_db_connection()
        complaints = conn.execute(
            "SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC", (session["user_id"],)
        ).fetchall()
        conn.close()
        return jsonify([dict(c) for c in complaints])

    @app.route("/api/user/complaints/<int:complaint_id>")
    @user_required
    def get_user_complaint(complaint_id):
        conn = get_db_connection()
        c = conn.execute("SELECT * FROM complaints WHERE id = ? AND user_id = ?", (complaint_id, session["user_id"])).fetchone()
        conn.close()
        return jsonify(dict(c)) if c else (jsonify({"error": "Not found"}), 404)

    @app.route("/api/admin/complaints")
    @admin_required
    def get_all_complaints():
        conn = get_db_connection()
        complaints = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
        conn.close()
        return jsonify([dict(c) for c in complaints])

    @app.route("/api/admin/complaints/<int:complaint_id>")
    @admin_required
    def get_complaint(complaint_id):
        conn = get_db_connection()
        c = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        conn.close()
        return jsonify(dict(c)) if c else (jsonify({"error": "Not found"}), 404)

    @app.route("/api/admin/complaints/<int:complaint_id>/status", methods=["PUT"])
    @admin_required
    def update_complaint_status(complaint_id):
        data = request.get_json()
        new_status = data.get("status")
        changed_by = data.get("changed_by", session.get("admin_name", "Admin"))
        comments = data.get("comments", "")
        conn = get_db_connection()
        c = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        if not c:
            conn.close()
            return jsonify({"error": "Not found"}), 404
        old_status = dict(c)["status"]
        conn.execute("UPDATE complaints SET status = ?, updated_at = ? WHERE id = ?", (new_status, datetime.now(), complaint_id))
        conn.execute(
            "INSERT INTO status_history (complaint_id, old_status, new_status, changed_by, comments) VALUES (?, ?, ?, ?, ?)",
            (complaint_id, old_status, new_status, changed_by, comments),
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Status updated"})

    @app.route("/api/admin/complaints/<int:complaint_id>", methods=["DELETE"])
    @admin_required
    def delete_complaint(complaint_id):
        conn = get_db_connection()
        conn.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Complaint deleted"})

    @app.route("/api/bot/register-user", methods=["POST"])
    def bot_register_user():
        data = request.get_json()
        telegram_id = str(data.get("telegram_id", ""))
        name = data.get("name", "Telegram User")
        username = data.get("username", "")
        phone = data.get("phone", "")

        if not telegram_id:
            return jsonify({"error": "telegram_id required"}), 400
        conn = get_db_connection()

        if phone:
            user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            if user:
                conn.execute("UPDATE users SET telegram_id = ? WHERE id = ?", (telegram_id, dict(user)["id"]))
                conn.commit()
                conn.close()
                return jsonify({"user_id": dict(user)["id"], "created": False, "linked": True})

        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if user:
            if phone and not dict(user).get("phone"):
                conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, dict(user)["id"]))
                conn.commit()
            conn.close()
            return jsonify({"user_id": dict(user)["id"], "created": False, "linked": False})

        password = secrets.token_urlsafe(8)
        pw_hash = hash_password(password)
        conn.execute(
            "INSERT INTO users (name, telegram_id, phone, password_hash) VALUES (?, ?, ?, ?)",
            (name or username or "Telegram User", telegram_id, phone, pw_hash),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        conn.close()
        return jsonify({"user_id": dict(user)["id"], "created": True, "linked": False, "password": password})

    @app.route("/api/bot/reset-password", methods=["POST"])
    def bot_reset_password():
        data = request.get_json()
        telegram_id = str(data.get("telegram_id", ""))
        if not telegram_id:
            return jsonify({"error": "telegram_id required"}), 400

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "No linked account found"}), 404

        password = secrets.token_urlsafe(8)
        pw_hash = hash_password(password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, dict(user)["id"]))
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "password": password, "phone": dict(user).get("phone", "")})

    @app.route("/api/bot/submit-complaint", methods=["POST"])
    def bot_submit_complaint():
        telegram_id = str(request.form.get("telegram_id", ""))
        if not telegram_id:
            return jsonify({"error": "telegram_id required"}), 400

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        conn.close()
        if not user:
            return jsonify({"error": "User not registered. Send /start to the bot first."}), 403

        user = dict(user)
        image_file = request.files.get("image")
        if not image_file:
            return jsonify({"error": "Image is required"}), 400

        try:
            return process_complaint_submission(
                image_file=image_file,
                audio_file=request.files.get("audio"),
                text_description=request.form.get("description", ""),
                device_lat=request.form.get("gps_lat"),
                device_lng=request.form.get("gps_lng"),
                manual_address=request.form.get("location_text"),
                user_id=user["id"],
                source="telegram",
                submitted_by=user.get("name", "Telegram User"),
            )
        except Exception as e:
            print(f"[ERROR] bot_submit_complaint: {e}")
            return jsonify({"error": friendly_error(e)}), 500

    @app.route("/api/bot/user-complaints/<telegram_id>")
    def bot_user_complaints(telegram_id):
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (str(telegram_id),)).fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "User not found"}), 404
        user_id = dict(user)["id"]
        complaints = conn.execute(
            "SELECT ghmc_id, subject, category, priority, status, created_at FROM complaints WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            (user_id,),
        ).fetchall()
        conn.close()
        return jsonify([dict(c) for c in complaints])

    @app.route("/health")
    def health():
        try:
            conn = get_db_connection()
            conn.execute("SELECT 1").fetchone()
            conn.close()
            return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200
        except Exception as e:
            return jsonify({"status": "unhealthy", "error": str(e)}), 500
