import base64
import io
import json
import os
import tempfile
import time
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime

from flask import jsonify
from geopy.exc import GeocoderUnavailable
from geopy.geocoders import Nominatim
from google import genai
from google.genai import types as genai_types
import cloudinary.uploader
import requests

from config import get_portal_base_url

from .constants import COMPLAINT_CATEGORIES
from .db import get_db

logger = logging.getLogger("fixmyhyd")
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="api_worker")

GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", 25))
CLOUDINARY_TIMEOUT = int(os.getenv("CLOUDINARY_TIMEOUT", 30))
GEOCODE_TIMEOUT = int(os.getenv("GEOCODE_TIMEOUT", 8))
PORTAL_BASE_URL = get_portal_base_url()
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", 25))
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.1-8b-instant")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")
GROQ_AUDIO_MODEL = os.getenv("GROQ_AUDIO_MODEL", "whisper-large-v3")
AI_ANALYZER_WARNING = (
    "AI analyzer had a small issue. Your upload was saved and the complaint was submitted "
    "without image analysis."
)


def call_with_timeout(fn, timeout_secs, default_return, label="external_api"):
    future = _executor.submit(fn)
    try:
        return future.result(timeout=timeout_secs)
    except FutureTimeoutError:
        logger.warning(f"[{label}] Timed out after {timeout_secs}s")
        future.cancel()
        return default_return
    except Exception as e:
        logger.warning(f"[{label}] Error: {type(e).__name__}: {e}")
        return default_return


def upload_image_to_cloudinary(image_bytes, ghmc_id):
    safe_id = ghmc_id.replace("/", "_")

    def _do_upload():
        return cloudinary.uploader.upload(
            image_bytes,
            public_id=f"fixmyhyd/{safe_id}",
            folder="fixmyhyd_complaints",
            resource_type="auto",
            format="jpg",
        )

    try:
        upload_response = call_with_timeout(_do_upload, CLOUDINARY_TIMEOUT, None, label="cloudinary_upload")
        if upload_response:
            return upload_response.get("secure_url", upload_response.get("url"))
    except Exception as e:
        logger.warning(f"[CLOUDINARY] Upload failed: {e}")

    logger.info("[CLOUDINARY] Falling back to local storage")
    uploads_dir = os.path.join("static", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    image_filename = f"{safe_id}.jpg"
    with open(os.path.join(uploads_dir, image_filename), "wb") as f:
        f.write(image_bytes)
    return f"uploads/{image_filename}"


def safe_gemini_text(response):
    if response is None:
        return None
    text = getattr(response, "text", None)
    if text is None:
        return None
    return str(text).strip()


def _extract_warning(payload):
    if isinstance(payload, dict):
        return payload.pop("_warning", None)
    return None


def _normalize_json_text(text):
    if not text:
        return None
    return text.replace("```json", "").replace("```", "").strip()


def _groq_content_to_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts).strip() or None
    return None


def groq_chat_completion(messages, model, max_tokens=512, temperature=0.2, response_format=None):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        f"{GROQ_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=GROQ_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    return _groq_content_to_text(message.get("content"))


def analyze_image_with_groq(image_bytes):
    prompt = f"""Analyze this image of a civic issue in Hyderabad, India.
Return ONLY a valid JSON object with:
1. \"summary\": one-sentence description of the scene
2. \"category\": one of {', '.join(COMPLAINT_CATEGORIES)}"""

    image_data = base64.b64encode(image_bytes).decode("utf-8")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                },
            ],
        }
    ]

    try:
        text = groq_chat_completion(
            messages,
            GROQ_VISION_MODEL,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        text = _normalize_json_text(text)
        return json.loads(text) if text else None
    except Exception as e:
        logger.warning(f"[GROQ IMAGE] Error: {type(e).__name__}: {e}")
        return None


def transcribe_audio_with_groq(audio_path):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    ext = os.path.splitext(audio_path)[1].lower()
    mime_type = "audio/ogg" if ext == ".ogg" else "audio/wav"
    headers = {"Authorization": f"Bearer {api_key}"}
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, mime_type)}
        data = {"model": GROQ_AUDIO_MODEL}
        response = requests.post(
            f"{GROQ_BASE_URL}/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=GROQ_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text") or payload.get("transcript")
        return str(text).strip() if text else None


def analyze_text_with_groq(description):
    prompt = f"""Analyze this civic complaint from Hyderabad. Return ONLY a valid JSON object with:
1. \"category\": one of {', '.join(COMPLAINT_CATEGORIES)}
2. \"priority\": \"Low\", \"Medium\", or \"High\"
3. \"summary\": one-sentence summary
4. \"actionable_steps\": list of 2-3 brief steps
Complaint: \"{description}\" """

    messages = [{"role": "user", "content": prompt}]
    try:
        text = groq_chat_completion(
            messages,
            GROQ_TEXT_MODEL,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        text = _normalize_json_text(text)
        return json.loads(text) if text else None
    except Exception as e:
        logger.warning(f"[GROQ TEXT] Error: {type(e).__name__}: {e}")
        return None


def generate_formal_report_with_groq(data):
    prompt = f"""You are an AI assistant for GHMC Hyderabad. Synthesize this information into a structured formal complaint.
Return ONLY a valid JSON object with: \"subject\", \"description\", \"zone\" (Hyderabad zone if determinable, else \"Unknown\").
Data:
- Image Analysis: {data.get('image_analysis')}
- Voice Transcription: {data.get('voice_transcription')}
- Text Analysis: {data.get('text_analysis')}
- Location: {data.get('location_text', 'Not provided')}"""

    messages = [{"role": "user", "content": prompt}]
    try:
        text = groq_chat_completion(
            messages,
            GROQ_TEXT_MODEL,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        text = _normalize_json_text(text)
        return json.loads(text) if text else None
    except Exception as e:
        logger.warning(f"[GROQ REPORT] Error: {type(e).__name__}: {e}")
        return None


def analyze_image_with_gemini(image_stream, max_retries=1):
    image_bytes = image_stream.read()
    api_key = os.getenv("GOOGLE_API_KEY_IMAGE")
    if not api_key:
        logger.info("[GEMINI IMAGE] No API key; trying Groq fallback")
        groq_result = analyze_image_with_groq(image_bytes)
        if groq_result:
            return groq_result
        return {"summary": "AI analysis unavailable", "category": "Other", "_warning": AI_ANALYZER_WARNING}

    image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    prompt = f"""Analyze this image of a civic issue in Hyderabad, India.
Return ONLY a valid JSON object with:
1. \"summary\": one-sentence description of the scene
2. \"category\": one of {', '.join(COMPLAINT_CATEGORIES)}"""

    def _call():
        client = genai.Client(api_key=api_key)
        return client.models.generate_content(model="gemini-2.0-flash-lite", contents=[prompt, image_part])

    for attempt in range(max_retries):
        try:
            response = call_with_timeout(_call, GEMINI_TIMEOUT, None, label="gemini_image")
            text = safe_gemini_text(response)
            if not text:
                logger.warning(f"[GEMINI IMAGE] Empty response on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                groq_result = analyze_image_with_groq(image_bytes)
                if groq_result:
                    return groq_result
                return {"summary": "AI analysis unavailable", "category": "Other", "_warning": AI_ANALYZER_WARNING}
            text = text.replace("```json", "").replace("```", "")
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"[GEMINI IMAGE] JSON parse error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            groq_result = analyze_image_with_groq(image_bytes)
            if groq_result:
                return groq_result
            return {"summary": "AI analysis unavailable", "category": "Other", "_warning": AI_ANALYZER_WARNING}
        except Exception as e:
            logger.warning(f"[GEMINI IMAGE] Error (attempt {attempt + 1}): {type(e).__name__}: {e}")
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2**attempt) * 2 + 7)
                continue
            groq_result = analyze_image_with_groq(image_bytes)
            if groq_result:
                return groq_result
            return {"summary": "AI analysis unavailable", "category": "Other", "_warning": AI_ANALYZER_WARNING}

    groq_result = analyze_image_with_groq(image_bytes)
    if groq_result:
        return groq_result
    return {"summary": "AI analysis unavailable", "category": "Other", "_warning": AI_ANALYZER_WARNING}


def transcribe_audio_with_gemini(audio_path, max_retries=1):
    api_key = os.getenv("GOOGLE_API_KEY_AUDIO")
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    ext = os.path.splitext(audio_path)[1].lower()
    mime_type = "audio/ogg" if ext == ".ogg" else "audio/wav"
    if not api_key:
        logger.info("[GEMINI AUDIO] No API key; trying Groq fallback")
        groq_result = transcribe_audio_with_groq(audio_path)
        if groq_result:
            return {"transcription": groq_result}
        return {"transcription": "", "_warning": AI_ANALYZER_WARNING}

    logger.info(f"[GEMINI AUDIO] {len(audio_bytes)} bytes, mime={mime_type}")
    audio_part = genai_types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    prompt = "Transcribe this audio complaint from a citizen in Hyderabad. Return ONLY the transcribed text."

    def _call():
        client = genai.Client(api_key=api_key)
        return client.models.generate_content(model="gemini-2.0-flash-lite", contents=[prompt, audio_part])

    for attempt in range(max_retries):
        try:
            response = call_with_timeout(_call, GEMINI_TIMEOUT, None, label="gemini_audio")
            text = safe_gemini_text(response)
            if text is None:
                logger.warning(f"[GEMINI AUDIO] Empty response on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                groq_result = transcribe_audio_with_groq(audio_path)
                if groq_result:
                    return {"transcription": groq_result}
                return {"transcription": "", "_warning": AI_ANALYZER_WARNING}
            logger.info(f"[GEMINI AUDIO] Success: {text[:120]}")
            return {"transcription": text}
        except Exception as e:
            logger.warning(f"[GEMINI AUDIO] Error (attempt {attempt + 1}): {type(e).__name__}: {e}")
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2**attempt) * 2 + 7)
                continue
            groq_result = transcribe_audio_with_groq(audio_path)
            if groq_result:
                return {"transcription": groq_result}
            return {"transcription": "", "_warning": AI_ANALYZER_WARNING}

    groq_result = transcribe_audio_with_groq(audio_path)
    if groq_result:
        return {"transcription": groq_result}
    return {"transcription": "", "_warning": AI_ANALYZER_WARNING}


def analyze_text_with_gemini(description, max_retries=1):
    api_key = os.getenv("GOOGLE_API_KEY_TEXT")
    if not api_key:
        logger.info("[GEMINI TEXT] No API key; trying Groq fallback")
        groq_result = analyze_text_with_groq(description)
        if groq_result:
            return groq_result
        return {"category": "Other", "priority": "Medium", "summary": description, "actionable_steps": [], "_warning": AI_ANALYZER_WARNING}

    prompt = f"""Analyze this civic complaint from Hyderabad. Return ONLY a valid JSON object with:
1. \"category\": one of {', '.join(COMPLAINT_CATEGORIES)}
2. \"priority\": \"Low\", \"Medium\", or \"High\"
3. \"summary\": one-sentence summary
4. \"actionable_steps\": list of 2-3 brief steps
Complaint: \"{description}\" """

    def _call():
        client = genai.Client(api_key=api_key)
        return client.models.generate_content(model="gemini-2.0-flash-lite", contents=prompt)

    for attempt in range(max_retries):
        try:
            response = call_with_timeout(_call, GEMINI_TIMEOUT, None, label="gemini_text")
            text = safe_gemini_text(response)
            if not text:
                logger.warning(f"[GEMINI TEXT] Empty response on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                groq_result = analyze_text_with_groq(description)
                if groq_result:
                    return groq_result
                return {"category": "Other", "priority": "Medium", "summary": description, "actionable_steps": [], "_warning": AI_ANALYZER_WARNING}
            text = text.replace("```json", "").replace("```", "")
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"[GEMINI TEXT] JSON parse error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            groq_result = analyze_text_with_groq(description)
            if groq_result:
                return groq_result
            return {"category": "Other", "priority": "Medium", "summary": description, "actionable_steps": [], "_warning": AI_ANALYZER_WARNING}
        except Exception as e:
            logger.warning(f"[GEMINI TEXT] Error (attempt {attempt + 1}): {type(e).__name__}: {e}")
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2**attempt) * 2 + 7)
                continue
            groq_result = analyze_text_with_groq(description)
            if groq_result:
                return groq_result
            return {"category": "Other", "priority": "Medium", "summary": description, "actionable_steps": [], "_warning": AI_ANALYZER_WARNING}

    groq_result = analyze_text_with_groq(description)
    if groq_result:
        return groq_result
    return {"category": "Other", "priority": "Medium", "summary": description, "actionable_steps": [], "_warning": AI_ANALYZER_WARNING}


def generate_formal_report_with_gemini(data, max_retries=1):
    api_key = os.getenv("GOOGLE_API_KEY_REPORT")
    if not api_key:
        logger.info("[GEMINI REPORT] No API key; trying Groq fallback")
        groq_result = generate_formal_report_with_groq(data)
        if groq_result:
            return groq_result
        return {
            "subject": data.get("text_analysis", {}).get("summary", "Civic Issue Report"),
            "description": str(data.get("image_analysis", {}).get("summary", "")),
            "zone": "Unknown",
            "_warning": AI_ANALYZER_WARNING,
        }

    prompt = f"""You are an AI assistant for GHMC Hyderabad. Synthesize this information into a structured formal complaint.
Return ONLY a valid JSON object with: \"subject\", \"description\", \"zone\" (Hyderabad zone if determinable, else \"Unknown\").
Data:
- Image Analysis: {data.get('image_analysis')}
- Voice Transcription: {data.get('voice_transcription')}
- Text Analysis: {data.get('text_analysis')}
- Location: {data.get('location_text', 'Not provided')}"""

    def _call():
        client = genai.Client(api_key=api_key)
        return client.models.generate_content(model="gemini-2.0-flash-lite", contents=prompt)

    for attempt in range(max_retries):
        try:
            response = call_with_timeout(_call, GEMINI_TIMEOUT, None, label="gemini_report")
            text = safe_gemini_text(response)
            if not text:
                logger.warning(f"[GEMINI REPORT] Empty response on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                groq_result = generate_formal_report_with_groq(data)
                if groq_result:
                    return groq_result
                return {
                    "subject": data.get("text_analysis", {}).get("summary", "Civic Issue Report"),
                    "description": str(data.get("image_analysis", {}).get("summary", "")),
                    "zone": "Unknown",
                    "_warning": AI_ANALYZER_WARNING,
                }
            text = text.replace("```json", "").replace("```", "")
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"[GEMINI REPORT] JSON parse error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            groq_result = generate_formal_report_with_groq(data)
            if groq_result:
                return groq_result
            return {
                "subject": data.get("text_analysis", {}).get("summary", "Civic Issue Report"),
                "description": str(data.get("image_analysis", {}).get("summary", "")),
                "zone": "Unknown",
                "_warning": AI_ANALYZER_WARNING,
            }
        except Exception as e:
            logger.warning(f"[GEMINI REPORT] Error (attempt {attempt + 1}): {type(e).__name__}: {e}")
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep((2**attempt) * 2 + 7)
                continue
            groq_result = generate_formal_report_with_groq(data)
            if groq_result:
                return groq_result
            return {
                "subject": data.get("text_analysis", {}).get("summary", "Civic Issue Report"),
                "description": str(data.get("image_analysis", {}).get("summary", "")),
                "zone": "Unknown",
                "_warning": AI_ANALYZER_WARNING,
            }

    groq_result = generate_formal_report_with_groq(data)
    if groq_result:
        return groq_result
    return {
        "subject": data.get("text_analysis", {}).get("summary", "Civic Issue Report"),
        "description": str(data.get("image_analysis", {}).get("summary", "")),
        "zone": "Unknown",
        "_warning": AI_ANALYZER_WARNING,
    }


def reverse_geocode(lat, lng):
    if lat is None or lng is None:
        return "Location not available"

    def _do_geocode():
        geolocator = Nominatim(user_agent="fixmyhyd_app", timeout=5)
        location = geolocator.reverse((lat, lng), exactly_one=True, timeout=5)
        return location.address if location else f"({lat:.4f}, {lng:.4f})"

    try:
        result = call_with_timeout(_do_geocode, GEOCODE_TIMEOUT, None, label="reverse_geocode")
        if result is not None:
            return result
    except GeocoderUnavailable as e:
        logger.warning(f"[GEOLOCATION] Service unavailable ({e}), using coordinates: {lat}, {lng}")
    except Exception as e:
        logger.warning(f"[GEOLOCATION] Error: {e}, using coordinates fallback")
    return f"GPS: {lat:.4f}, {lng:.4f}"


def process_complaint_submission(
    image_file,
    audio_file,
    text_description,
    device_lat,
    device_lng,
    manual_address,
    user_id,
    source,
    submitted_by,
):
    logger.info(f"[COMPLAINT] Starting submission for user_id={user_id} source={source}")
    ai_warning = None

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
        logger.warning("[COMPLAINT] No location provided")
        return jsonify({"error": "Location data required (GPS or address)"}), 400

    try:
        image_bytes = image_file.stream.read()
    except Exception as e:
        logger.warning(f"[COMPLAINT] Failed to read image stream: {e}")
        return jsonify({"error": "Unable to read uploaded image."}), 400

    logger.info("[COMPLAINT] Analyzing image with Gemini...")
    image_analysis = analyze_image_with_gemini(io.BytesIO(image_bytes))
    ai_warning = ai_warning or _extract_warning(image_analysis)

    full_description = text_description or ""
    voice_transcription = None
    temp_path = None
    if audio_file:
        mime = getattr(audio_file, "content_type", "") or getattr(audio_file, "mimetype", "")
        ext = ".ogg" if "ogg" in mime else ".wav"
        temp_path = os.path.join(tempfile.gettempdir(), f"audio_{user_id}_{int(time.time())}{ext}")
        try:
            audio_file.save(temp_path)
            result = transcribe_audio_with_gemini(temp_path)
            ai_warning = ai_warning or _extract_warning(result)
            if result and result.get("transcription"):
                voice_transcription = result["transcription"]
                full_description += f"\n\n(Voice: {voice_transcription})"
        except Exception as e:
            logger.warning(f"[COMPLAINT] Audio transcription failed: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    logger.warning(f"[COMPLAINT] Failed to remove temp audio: {e}")

    full_description = full_description.strip()
    if not full_description:
        full_description = image_analysis.get("summary", "Civic issue reported via image")

    logger.info("[COMPLAINT] Analyzing text with Gemini...")
    text_analysis = analyze_text_with_gemini(full_description)
    ai_warning = ai_warning or _extract_warning(text_analysis)

    logger.info("[COMPLAINT] Generating formal report with Gemini...")
    formal_report = generate_formal_report_with_gemini(
        {
            "image_analysis": image_analysis,
            "voice_transcription": voice_transcription,
            "text_analysis": text_analysis,
            "location_text": final_location,
        }
    )
    ai_warning = ai_warning or _extract_warning(formal_report)

    final_category = text_analysis.get("category", image_analysis.get("category", "Other"))
    final_priority = text_analysis.get("priority", "Medium")
    ghmc_id = f"GHMC/HYD/{int(datetime.now().timestamp())}"

    image_path = upload_image_to_cloudinary(image_bytes, ghmc_id)

    conn = None
    try:
        conn, is_pg = get_db()
        ph = "%s" if is_pg else "?"
        cursor = conn.cursor()
        if is_pg:
            cursor.execute(
                f"""INSERT INTO complaints
                   (ghmc_id, category, priority, subject, description, location, zone,
                    gps_lat, gps_lng, user_id, source, submitted_by, image_path)
                   VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                   RETURNING id""",
                (
                    ghmc_id,
                    final_category,
                    final_priority,
                    formal_report.get("subject", "Civic Issue"),
                    formal_report.get("description", full_description),
                    final_location,
                    formal_report.get("zone", "Unknown"),
                    final_lat,
                    final_lng,
                    user_id,
                    source,
                    submitted_by,
                    image_path,
                ),
            )
            inserted_row = cursor.fetchone()
            complaint_id = inserted_row["id"] if isinstance(inserted_row, dict) else inserted_row[0]
        else:
            cursor.execute(
                f"""INSERT INTO complaints
                   (ghmc_id, category, priority, subject, description, location, zone,
                    gps_lat, gps_lng, user_id, source, submitted_by, image_path)
                   VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                (
                    ghmc_id,
                    final_category,
                    final_priority,
                    formal_report.get("subject", "Civic Issue"),
                    formal_report.get("description", full_description),
                    final_location,
                    formal_report.get("zone", "Unknown"),
                    final_lat,
                    final_lng,
                    user_id,
                    source,
                    submitted_by,
                    image_path,
                ),
            )
            complaint_id = cursor.lastrowid

        conn.commit()
        cursor.close()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Complaint submitted successfully.",
                    "acknowledgement": {
                        "complaint_id": complaint_id,
                        "ghmc_id": ghmc_id,
                        "subject": formal_report.get("subject"),
                        "category": final_category,
                        "priority": final_priority,
                        "portal_url": f"{PORTAL_BASE_URL}/user/dashboard",
                        "voice_transcription": voice_transcription,
                    },
                    **({"warning": ai_warning} if ai_warning else {}),
                }
            ),
            201,
        )
    except Exception as e:
        logger.error(f"[COMPLAINT] DB insert failed: {type(e).__name__}: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Database error while saving complaint. Please try again."}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
