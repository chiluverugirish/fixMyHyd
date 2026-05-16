import hashlib
import secrets
from functools import wraps

from flask import flash, redirect, session, url_for


def hash_password(password):
    salt = secrets.token_hex(16)
    return f"{salt}:{hashlib.sha256((password + salt).encode()).hexdigest()}"


def verify_password(password, stored_hash):
    try:
        salt, pw_hash = stored_hash.split(":")
        return hashlib.sha256((password + salt).encode()).hexdigest() == pw_hash
    except Exception:
        return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session and "admin_id" not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("home"))
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin_id" not in session:
            flash("Admin access required.", "error")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)

    return decorated


def user_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("user_login"))
        return f(*args, **kwargs)

    return decorated
