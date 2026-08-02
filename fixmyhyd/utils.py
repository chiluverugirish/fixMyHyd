from datetime import datetime
import hashlib
import secrets


def parse_timestamp(ts):
    if isinstance(ts, datetime):
        return ts
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def format_date(ts):
    if isinstance(ts, str):
        ts = parse_timestamp(ts)
    return ts.strftime("%d %b %Y") if ts else "N/A"


def format_datetime(ts):
    if isinstance(ts, str):
        ts = parse_timestamp(ts)
    return ts.strftime("%d %b %Y %I:%M %p") if ts else "N/A"


def friendly_error(e):
    s = str(e)
    if "429" in s or "quota" in s.lower() or "ResourceExhausted" in type(e).__name__:
        return "AI service quota exceeded. Please wait a few minutes and try again."
    if "API_KEY" in s or "api key" in s.lower():
        return "AI service configuration error. Please contact support."
    return "An unexpected error occurred. Please try again."


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"{salt}:{hashlib.sha256((password + salt).encode()).hexdigest()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, pw_hash = stored_hash.split(":")
        return hashlib.sha256((password + salt).encode()).hexdigest() == pw_hash
    except Exception:
        return False
