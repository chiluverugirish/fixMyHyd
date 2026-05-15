import os
import io
import json
import sqlite3
import time
import hashlib
import secrets
import tempfile
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from PIL import Image, ExifTags
from dotenv import load_dotenv
import google.generativeai as genai
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable
import cloudinary
import cloudinary.uploader

# Werkzeug compatibility shim for 'partitioned' kwarg in older versions
try:
    from werkzeug.wrappers import Response as _WerkzeugResponse
    _orig_set_cookie = _WerkzeugResponse.set_cookie
    def _set_cookie_compat(self, *args, **kwargs):
        kwargs.pop('partitioned', None)
        return _orig_set_cookie(self, *args, **kwargs)
    _WerkzeugResponse.set_cookie = _set_cookie_compat
    if hasattr(_WerkzeugResponse, 'delete_cookie'):
        _orig_delete_cookie = _WerkzeugResponse.delete_cookie
        def _delete_cookie_compat(self, *args, **kwargs):
            kwargs.pop('partitioned', None)
            return _orig_delete_cookie(self, *args, **kwargs)
        _WerkzeugResponse.delete_cookie = _delete_cookie_compat
except Exception:
    pass

# ==================== 1. INITIALIZATION ====================

load_dotenv()
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

COMPLAINT_CATEGORIES = [
    "Open Garbage Dump", "Sewage Leak/Overflow", "Pothole/Damaged Road",
    "Damaged Electrical Infrastructure", "Fallen Tree", "Water Logging",
    "Stray Animals", "Other"
]

PORTAL_BASE_URL = os.getenv('PORTAL_BASE_URL', 'http://localhost:5001')

# ==================== CLOUDINARY CONFIGURATION ====================
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def upload_image_to_cloudinary(image_bytes, ghmc_id):
    """Upload image to Cloudinary and return the URL."""
    try:
        safe_id = ghmc_id.replace('/', '_')
        upload_response = cloudinary.uploader.upload(
            image_bytes,
            public_id=f"fixmyhyd/{safe_id}",
            folder="fixmyhyd_complaints",
            resource_type="auto",
            format="jpg"
        )
        return upload_response.get('secure_url', upload_response.get('url'))
    except Exception as e:
        print(f"[CLOUDINARY] Upload failed: {e}")
        # Fallback to local storage if Cloudinary fails
        uploads_dir = os.path.join('static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        image_filename = f"{safe_id}.jpg"
        with open(os.path.join(uploads_dir, image_filename), 'wb') as f:
            f.write(image_bytes)
        return f"uploads/{image_filename}"

# ==================== 2. DATABASE ====================

def get_db():
    database_url = os.getenv('DATABASE_URL')
    if database_url and ('postgresql' in database_url or 'postgres' in database_url):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            return conn, True
        except Exception as e:
            print(f"PostgreSQL failed, falling back to SQLite: {e}")
    db_path = '/tmp/fixmyhyd.db' if '/opt/render' in os.getcwd() else os.getenv('DATABASE_PATH', 'fixmyhyd.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn, False

class DBConnection:
    """Wrapper for both SQLite and PostgreSQL connections."""
    def __init__(self, conn, is_postgres):
        self._conn = conn
        self._is_postgres = is_postgres
    
    def execute(self, query, params=()):
        """Execute query - returns wrapper that supports fetchone/fetchall."""
        if self._is_postgres:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            return cursor
        else:
            return self._conn.execute(query, params)
    
    def commit(self):
        """Commit transaction."""
        self._conn.commit()
    
    def close(self):
        """Close connection."""
        self._conn.close()
    
    def cursor(self):
        """Get a cursor for advanced operations."""
        return self._conn.cursor()

def get_db_connection():
    conn, pg = get_db()
    return DBConnection(conn, pg)

def is_postgres():
    conn, pg = get_db()
    conn.close()
    return pg

def hash_password(password):
    salt = secrets.token_hex(16)
    return f"{salt}:{hashlib.sha256((password + salt).encode()).hexdigest()}"

def verify_password(password, stored_hash):
    try:
        salt, pw_hash = stored_hash.split(':')
        return hashlib.sha256((password + salt).encode()).hexdigest() == pw_hash
    except Exception:
        return False

def init_database():
    conn, pg = get_db()
    cursor = conn.cursor()
    ph = '%s' if pg else '?'

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS users (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            email TEXT UNIQUE,
            password_hash TEXT,
            name TEXT NOT NULL,
            phone TEXT,
            telegram_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS admins (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS complaints (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            ghmc_id TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            priority TEXT DEFAULT 'Medium',
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT,
            zone TEXT,
            gps_lat REAL,
            gps_lng REAL,
            status TEXT DEFAULT 'Submitted',
            submitted_by TEXT DEFAULT 'Citizen',
            source TEXT DEFAULT 'portal',
            user_id INTEGER,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Migration: add image_path to existing DBs
    try:
        cursor.execute('ALTER TABLE complaints ADD COLUMN image_path TEXT')
        conn.commit()
    except Exception:
        pass

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS status_history (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            complaint_id INTEGER,
            old_status TEXT,
            new_status TEXT,
            changed_by TEXT,
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Default admin
    cursor.execute('SELECT COUNT(*) FROM admins')
    result = cursor.fetchone()
    admin_count = result[0] if pg else result[0]
    if admin_count == 0:
        pw = hash_password('admin123')
        cursor.execute(
            f'INSERT INTO admins (username, password_hash, name) VALUES ({ph}, {ph}, {ph})',
            ('admin', pw, 'System Administrator')
        )

    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialized")

try:
    init_database()
except Exception as e:
    print(f"DB init failed: {e}")
    import traceback; traceback.print_exc()

# ==================== 3. AI FUNCTIONS (Gemini) ====================

def analyze_image_with_gemini(image_stream, max_retries=3):
    api_key = os.getenv("GOOGLE_API_KEY_IMAGE")
    if not api_key:
        return {"summary": "AI unavailable", "category": "Other"}
    genai.configure(api_key=api_key)
    image_bytes = image_stream.read()
    image_part = {"mime_type": "image/jpeg", "data": image_bytes}
    prompt = f"""Analyze this image of a civic issue in Hyderabad, India.
Return ONLY a valid JSON object with:
1. "summary": one-sentence description of the scene
2. "category": one of {', '.join(COMPLAINT_CATEGORIES)}"""
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    for attempt in range(max_retries):
        try:
            response = model.generate_content([prompt, image_part])
            text = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(text)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 2 + 7)
                continue
            raise
    return None

def transcribe_audio_with_gemini(audio_path, max_retries=3):
    api_key = os.getenv("GOOGLE_API_KEY_AUDIO")
    if not api_key:
        print("[TRANSCRIBE] No GOOGLE_API_KEY_AUDIO set")
        return {"transcription": ""}
    genai.configure(api_key=api_key)
    ext = os.path.splitext(audio_path)[1].lower()
    mime_type = 'audio/ogg' if ext == '.ogg' else 'audio/wav'
    with open(audio_path, 'rb') as f:
        audio_bytes = f.read()
    print(f"[TRANSCRIBE] {len(audio_bytes)} bytes, mime={mime_type}")
    audio_part = {"mime_type": mime_type, "data": audio_bytes}
    prompt = "Transcribe this audio complaint from a citizen in Hyderabad. Return ONLY the transcribed text."
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    for attempt in range(max_retries):
        try:
            response = model.generate_content([prompt, audio_part])
            print(f"[TRANSCRIBE] Success: {response.text[:120]}")
            return {"transcription": response.text}
        except Exception as e:
            print(f"[TRANSCRIBE] Error (attempt {attempt+1}): {type(e).__name__}: {e}")
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 2 + 7)
                continue
            return {"transcription": ""}
    return {"transcription": ""}

def analyze_text_with_gemini(description, max_retries=3):
    api_key = os.getenv("GOOGLE_API_KEY_TEXT")
    if not api_key:
        return {"category": "Other", "priority": "Medium", "summary": description, "actionable_steps": []}
    genai.configure(api_key=api_key)
    prompt = f"""Analyze this civic complaint from Hyderabad. Return ONLY a valid JSON object with:
1. "category": one of {', '.join(COMPLAINT_CATEGORIES)}
2. "priority": "Low", "Medium", or "High"
3. "summary": one-sentence summary
4. "actionable_steps": list of 2-3 brief steps
Complaint: "{description}" """
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(text)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 2 + 7)
                continue
            raise
    return None

def generate_formal_report_with_gemini(data, max_retries=3):
    api_key = os.getenv("GOOGLE_API_KEY_REPORT")
    if not api_key:
        return {
            "subject": data.get('text_analysis', {}).get('summary', 'Civic Issue Report'),
            "description": str(data.get('image_analysis', {}).get('summary', '')),
            "zone": "Unknown"
        }
    genai.configure(api_key=api_key)
    prompt = f"""You are an AI assistant for GHMC Hyderabad. Synthesize this information into a structured formal complaint.
Return ONLY a valid JSON object with: "subject", "description", "zone" (Hyderabad zone if determinable, else "Unknown").
Data:
- Image Analysis: {data.get('image_analysis')}
- Voice Transcription: {data.get('voice_transcription')}
- Text Analysis: {data.get('text_analysis')}
- Location: {data.get('location_text', 'Not provided')}"""
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(text)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 2 + 7)
                continue
            raise
    return None

# ==================== 4. GEOCODING ====================

def reverse_geocode(lat, lng):
    """Reverse geocode GPS coordinates to address. Falls back to coordinates if service unavailable."""
    if lat is None or lng is None:
        return "Location not available"
    try:
        geolocator = Nominatim(user_agent="fixmyhyd_app", timeout=5)
        location = geolocator.reverse((lat, lng), exactly_one=True, timeout=5)
        return location.address if location else f"({lat:.4f}, {lng:.4f})"
    except GeocoderUnavailable as e:
        # Service unavailable or coordinates not supported - use coordinates as fallback
        print(f"[GEOLOCATION] Service unavailable ({str(e)}), using coordinates: {lat}, {lng}")
        return f"GPS: {lat:.4f}, {lng:.4f}"
    except Exception as e:
        # Any other error - use coordinates as fallback
        print(f"[GEOLOCATION] Error: {str(e)}, using coordinates fallback")
        return f"GPS: {lat:.4f}, {lng:.4f}"

# ==================== 5. AUTH HELPERS ====================

def execute_query(conn, query, params=None, fetch_one=False, fetch_all=False):
    pg = os.getenv('DATABASE_URL', '')
    is_pg = 'postgresql' in pg or 'postgres' in pg
    cursor = conn.cursor()
    if is_pg and params:
        query = query.replace('?', '%s')
    cursor.execute(query, params or ())
    if fetch_one:
        result = cursor.fetchone()
        return dict(result) if result else None
    if fetch_all:
        results = cursor.fetchall()
        return [dict(r) for r in results] if results else []
    return cursor

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session and 'admin_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Admin access required.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def user_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    return decorated

# ==================== 6. TIMESTAMP UTILS ====================

def parse_timestamp(ts):
    if isinstance(ts, datetime):
        return ts
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    except Exception:
        try:
            return datetime.strptime(str(ts), '%Y-%m-%d %H:%M:%S')
        except Exception:
            return None

@app.template_filter('format_date')
def format_date(ts):
    if isinstance(ts, str):
        ts = parse_timestamp(ts)
    return ts.strftime('%d %b %Y') if ts else 'N/A'

@app.template_filter('format_datetime')
def format_datetime(ts):
    if isinstance(ts, str):
        ts = parse_timestamp(ts)
    return ts.strftime('%d %b %Y %I:%M %p') if ts else 'N/A'

# ==================== 7. ERROR HELPERS ====================

def _friendly_error(e):
    s = str(e)
    if '429' in s or 'quota' in s.lower() or 'ResourceExhausted' in type(e).__name__:
        return "AI service quota exceeded. Please wait a few minutes and try again."
    if 'API_KEY' in s or 'api key' in s.lower():
        return "AI service configuration error. Please contact support."
    return "An unexpected error occurred. Please try again."

# ==================== 8. WEB ROUTES ====================

@app.route('/')
def home():
    conn = get_db_connection()
    total = conn.execute('SELECT COUNT(*) FROM complaints').fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'").fetchone()[0]
    users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    resolution_rate = round((resolved / total * 100) if total > 0 else 0)
    try:
        avg_result = conn.execute(
            "SELECT AVG(CAST((julianday(updated_at) - julianday(created_at)) AS REAL)) FROM complaints WHERE status = 'Resolved'"
        ).fetchone()[0]
        avg_days = round(avg_result) if avg_result else 0
    except Exception:
        avg_days = 0
    conn.close()
    stats = {"total_complaints": total, "resolution_rate": resolution_rate, "total_users": users, "avg_days": avg_days}
    bot_url = os.getenv('TELEGRAM_BOT_URL', 'https://t.me/FixMyHyd_bot') # You can change this in .env
    return render_template('home.html', admin_stats=stats, bot_url=bot_url)

@app.route('/user/login', methods=['GET', 'POST'])
def user_login():
    if 'user_id' in session:
        return redirect(url_for('user_dashboard'))
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        if not phone or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('user_login.html')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE phone = ?', (phone,)).fetchone()
        conn.close()
        if user and user['password_hash'] and verify_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            flash('Login successful!', 'success')
            return redirect(url_for('user_dashboard'))
        flash('Invalid phone number or password.', 'error')
    return render_template('user_login.html')

@app.route('/user/register', methods=['GET', 'POST'])
def user_register():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not all([name, phone, password]):
            flash('Please fill in all required fields.', 'error')
            return render_template('user_register.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('user_register.html')
        conn = get_db_connection()
        try:
            existing = conn.execute('SELECT id FROM users WHERE phone = ?', (phone,)).fetchone()
            if existing:
                flash('Phone number already registered.', 'error')
                return render_template('user_register.html')
            pw_hash = hash_password(password)
            conn.execute(
                'INSERT INTO users (name, phone, password_hash) VALUES (?, ?, ?)',
                (name, phone, pw_hash)
            )
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('user_login'))
        except Exception as e:
            flash('Registration failed. Please try again.', 'error')
        finally:
            conn.close()
    return render_template('user_register.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('admin_login.html')
        try:
            conn = get_db_connection()
            admin = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
            conn.close()
            if admin:
                admin = dict(admin)
                if verify_password(password, admin['password_hash']):
                    session['admin_id'] = admin['id']
                    session['admin_name'] = admin['name']
                    flash('Admin login successful!', 'success')
                    return redirect(url_for('admin_dashboard'))
            flash('Invalid username or password.', 'error')
        except Exception as e:
            flash('Database error. Please try again.', 'error')
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/user/dashboard')
@user_required
def user_dashboard():
    conn = get_db_connection()
    raw = conn.execute(
        'SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC LIMIT 20',
        (session['user_id'],)
    ).fetchall()
    complaints = []
    for c in raw:
        d = dict(c)
        d['created_at'] = parse_timestamp(d['created_at'])
        d['updated_at'] = parse_timestamp(d.get('updated_at'))
        complaints.append(d)
    total = conn.execute('SELECT COUNT(*) FROM complaints WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status IN ('Submitted','In Progress','Acknowledged')",
        (session['user_id'],)
    ).fetchone()[0]
    resolved = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status = 'Resolved'",
        (session['user_id'],)
    ).fetchone()[0]
    conn.close()
    stats = {
        'total_complaints': total,
        'pending_complaints': pending,
        'resolved_complaints': resolved,
        'resolution_rate': round((resolved / total * 100) if total > 0 else 0)
    }
    return render_template('user_dashboard.html', user_complaints=complaints, user_stats=stats)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    raw = conn.execute('SELECT * FROM complaints ORDER BY created_at DESC').fetchall()
    complaints = []
    for c in raw:
        d = dict(c)
        d['created_at'] = parse_timestamp(d['created_at'])
        d['updated_at'] = parse_timestamp(d.get('updated_at'))
        complaints.append(d)
    total = conn.execute('SELECT COUNT(*) FROM complaints').fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE status IN ('Submitted','In Progress','Acknowledged')"
    ).fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'").fetchone()[0]
    conn.close()
    stats = {
        'total_complaints': total,
        'pending_complaints': pending,
        'resolved_complaints': resolved,
        'resolution_rate': round((resolved / total * 100) if total > 0 else 0)
    }
    return render_template('admin_dashboard.html', all_complaints=complaints, admin_stats=stats)

@app.route('/report-issue')
@user_required
def report_issue():
    return render_template('report_issue.html')

# ==================== 8. PORTAL API ROUTES ====================

@app.route('/api/report-issue', methods=['POST'])
@user_required
def report_issue_endpoint():
    try:
        return _process_complaint_submission(
            image_file=request.files.get('image'),
            audio_file=request.files.get('audio'),
            text_description=request.form.get('description', ''),
            device_lat=request.form.get('device_latitude'),
            device_lng=request.form.get('device_longitude'),
            manual_address=request.form.get('location_text'),
            user_id=session.get('user_id'),
            source='portal',
            submitted_by=session.get('user_name', 'Citizen')
        )
    except Exception as e:
        print(f"[ERROR] report_issue_endpoint: {e}")
        return jsonify({"error": _friendly_error(e)}), 500

@app.route('/api/user/complaints')
@user_required
def get_user_complaints():
    conn = get_db_connection()
    complaints = conn.execute(
        'SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(c) for c in complaints])

@app.route('/api/user/complaints/<int:complaint_id>')
@user_required
def get_user_complaint(complaint_id):
    conn = get_db_connection()
    c = conn.execute(
        'SELECT * FROM complaints WHERE id = ? AND user_id = ?',
        (complaint_id, session['user_id'])
    ).fetchone()
    conn.close()
    return jsonify(dict(c)) if c else (jsonify({"error": "Not found"}), 404)

@app.route('/api/admin/complaints')
@admin_required
def get_all_complaints():
    conn = get_db_connection()
    complaints = conn.execute('SELECT * FROM complaints ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(c) for c in complaints])

@app.route('/api/admin/complaints/<int:complaint_id>')
@admin_required
def get_complaint(complaint_id):
    conn = get_db_connection()
    c = conn.execute('SELECT * FROM complaints WHERE id = ?', (complaint_id,)).fetchone()
    conn.close()
    return jsonify(dict(c)) if c else (jsonify({"error": "Not found"}), 404)

@app.route('/api/admin/complaints/<int:complaint_id>/status', methods=['PUT'])
@admin_required
def update_complaint_status(complaint_id):
    data = request.get_json()
    new_status = data.get('status')
    changed_by = data.get('changed_by', session.get('admin_name', 'Admin'))
    comments = data.get('comments', '')
    conn = get_db_connection()
    c = conn.execute('SELECT * FROM complaints WHERE id = ?', (complaint_id,)).fetchone()
    if not c:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    old_status = dict(c)['status']
    conn.execute(
        'UPDATE complaints SET status = ?, updated_at = ? WHERE id = ?',
        (new_status, datetime.now(), complaint_id)
    )
    conn.execute(
        'INSERT INTO status_history (complaint_id, old_status, new_status, changed_by, comments) VALUES (?, ?, ?, ?, ?)',
        (complaint_id, old_status, new_status, changed_by, comments)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Status updated"})

@app.route('/api/admin/complaints/<int:complaint_id>', methods=['DELETE'])
@admin_required
def delete_complaint(complaint_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM complaints WHERE id = ?', (complaint_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Complaint deleted"})

# ==================== 9. BOT API ROUTES ====================

@app.route('/api/bot/register-user', methods=['POST'])
def bot_register_user():
    """Called by Telegram bot on /start. Creates or fetches user by telegram_id, linking by phone if provided."""
    data = request.get_json()
    telegram_id = str(data.get('telegram_id', ''))
    name = data.get('name', 'Telegram User')
    username = data.get('username', '')
    phone = data.get('phone', '')

    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    conn = get_db_connection()

    if phone:
        # Check if user with this phone exists
        user = conn.execute('SELECT * FROM users WHERE phone = ?', (phone,)).fetchone()
        if user:
            # Link telegram_id to this portal account
            conn.execute('UPDATE users SET telegram_id = ? WHERE id = ?', (telegram_id, dict(user)['id']))
            conn.commit()
            conn.close()
            return jsonify({"user_id": dict(user)['id'], "created": False, "linked": True})

    user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if user:
        if phone and not dict(user).get('phone'):
            conn.execute('UPDATE users SET phone = ? WHERE id = ?', (phone, dict(user)['id']))
            conn.commit()
        conn.close()
        return jsonify({"user_id": dict(user)['id'], "created": False, "linked": False})
        
    # Auto-create account linked to Telegram ID
    password = secrets.token_urlsafe(8)
    pw_hash = hash_password(password)
    conn.execute(
        'INSERT INTO users (name, telegram_id, phone, password_hash) VALUES (?, ?, ?, ?)',
        (name or username or 'Telegram User', telegram_id, phone, pw_hash)
    )
    conn.commit()
    user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    conn.close()
    return jsonify({"user_id": dict(user)['id'], "created": True, "linked": False, "password": password})

@app.route('/api/bot/reset-password', methods=['POST'])
def bot_reset_password():
    data = request.get_json()
    telegram_id = str(data.get('telegram_id', ''))
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "No linked account found"}), 404
        
    password = secrets.token_urlsafe(8)
    pw_hash = hash_password(password)
    conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (pw_hash, dict(user)['id']))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "password": password, "phone": dict(user).get('phone', '')})

@app.route('/api/bot/submit-complaint', methods=['POST'])
def bot_submit_complaint():
    """Called by Telegram bot to submit a complaint. Uses multipart/form-data."""
    telegram_id = str(request.form.get('telegram_id', ''))
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "User not registered. Send /start to the bot first."}), 403

    user = dict(user)
    image_file = request.files.get('image')
    if not image_file:
        return jsonify({"error": "Image is required"}), 400

    try:
        return _process_complaint_submission(
            image_file=image_file,
            audio_file=request.files.get('audio'),
            text_description=request.form.get('description', ''),
            device_lat=request.form.get('gps_lat'),
            device_lng=request.form.get('gps_lng'),
            manual_address=request.form.get('location_text'),
            user_id=user['id'],
            source='telegram',
            submitted_by=user.get('name', 'Telegram User')
        )
    except Exception as e:
        print(f"[ERROR] bot_submit_complaint: {e}")
        return jsonify({"error": _friendly_error(e)}), 500

@app.route('/api/bot/user-complaints/<telegram_id>')
def bot_user_complaints(telegram_id):
    """Called by Telegram bot to show a user's complaints."""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (str(telegram_id),)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    user_id = dict(user)['id']
    complaints = conn.execute(
        'SELECT ghmc_id, subject, category, priority, status, created_at FROM complaints WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(c) for c in complaints])

# ==================== 10. SHARED COMPLAINT PROCESSING ====================

def _process_complaint_submission(image_file, audio_file, text_description,
                                   device_lat, device_lng, manual_address,
                                   user_id, source, submitted_by):
    """Core complaint processing — used by both portal and bot endpoints."""
    # --- Location ---
    final_lat, final_lng, final_location = None, None, None
    if device_lat and device_lng:
        try:
            final_lat, final_lng = float(device_lat), float(device_lng)
            final_location = reverse_geocode(final_lat, final_lng)
        except ValueError:
            pass
    if not final_location and manual_address:
        final_location = manual_address
    if not final_location:
        return jsonify({"error": "Location data required (GPS or address)"}), 400

    # --- Image ---
    image_bytes = image_file.stream.read()
    image_analysis = analyze_image_with_gemini(io.BytesIO(image_bytes))
    if not image_analysis:
        return jsonify({"error": "AI image analysis failed"}), 500

    # --- Voice Transcription (optional) ---
    full_description = text_description or ""
    voice_transcription = None
    if audio_file:
        mime = getattr(audio_file, 'content_type', '') or getattr(audio_file, 'mimetype', '')
        ext = '.ogg' if 'ogg' in mime else '.wav'
        temp_path = os.path.join(tempfile.gettempdir(), f"audio_{user_id}_{int(time.time())}{ext}")
        audio_file.save(temp_path)
        print(f"[AUDIO] Saved to {temp_path}, size={os.path.getsize(temp_path)} bytes, mime={mime}")
        result = transcribe_audio_with_gemini(temp_path)
        try:
            os.remove(temp_path)
        except Exception:
            pass
        if result and result.get("transcription"):
            voice_transcription = result["transcription"]
            full_description += f"\n\n(Voice: {voice_transcription})"

    full_description = full_description.strip()
    if not full_description:
        full_description = image_analysis.get("summary", "Civic issue reported via image")

    # --- Text Analysis ---
    text_analysis = analyze_text_with_gemini(full_description)
    if not text_analysis:
        return jsonify({"error": "AI text analysis failed"}), 500

    # --- Formal Report ---
    formal_report = generate_formal_report_with_gemini({
        'image_analysis': image_analysis,
        'voice_transcription': voice_transcription,
        'text_analysis': text_analysis,
        'location_text': final_location,
    })
    if not formal_report:
        return jsonify({"error": "AI report generation failed"}), 500

    final_category = text_analysis.get("category", image_analysis.get("category", "Other"))
    final_priority = text_analysis.get("priority", "Medium")
    ghmc_id = f"GHMC/HYD/{int(datetime.now().timestamp())}"

    # --- Upload Image to Cloudinary ---
    image_path = upload_image_to_cloudinary(image_bytes, ghmc_id)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO complaints
               (ghmc_id, category, priority, subject, description, location, zone,
                gps_lat, gps_lng, user_id, source, submitted_by, image_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                ghmc_id, final_category, final_priority,
                formal_report.get('subject', 'Civic Issue'),
                formal_report.get('description', full_description),
                final_location,
                formal_report.get('zone', 'Unknown'),
                final_lat, final_lng,
                user_id, source, submitted_by,
                image_path
            )
        )
        complaint_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "status": "success",
            "message": "Complaint submitted successfully.",
            "acknowledgement": {
                "complaint_id": complaint_id,
                "ghmc_id": ghmc_id,
                "subject": formal_report.get('subject'),
                "category": final_category,
                "priority": final_priority,
                "portal_url": f"{PORTAL_BASE_URL}/user/dashboard",
                "voice_transcription": voice_transcription
            }
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# ==================== 11. HEALTH ====================

@app.route('/health')
def health():
    try:
        conn = get_db_connection()
        conn.execute('SELECT 1').fetchone()
        conn.close()
        return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    os.makedirs('temp', exist_ok=True)
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=os.environ.get('FLASK_ENV') == 'development', use_reloader=False, host='0.0.0.0', port=port)
