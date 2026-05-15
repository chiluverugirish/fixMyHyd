"""
FixMyHyd Telegram Bot
Reports go through the Flask backend — same pipeline as the portal.
Auto-creates a portal account for every new Telegram user (linked by telegram_id).
"""

import os
import io
import asyncio
import requests
import logging
from dotenv import load_dotenv

# Enable logging to clean up output
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import telegram.error
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters, ContextTypes
)

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="telegram.ext")
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_URL = os.getenv("PORTAL_BASE_URL", "http://localhost:5001")

# Conversation states
WAITING_FOR_PHOTO, WAITING_FOR_DESCRIPTION, WAITING_FOR_LOCATION = range(3)

# ==================== HELPERS ====================

def register_user(user):
    """Auto-create or fetch portal account linked to Telegram."""
    try:
        resp = requests.post(f"{BACKEND_URL}/api/bot/register-user", json={
            "telegram_id": str(user.id),
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "username": user.username or "",
        }, timeout=10)
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        print(f"register_user error: {e}")
        return None

def submit_complaint(telegram_id, image_bytes, description, gps_lat=None, gps_lng=None, location_text=None, audio_bytes=None):
    """Send complaint to backend for AI processing and DB storage."""
    try:
        files = {"image": ("photo.jpg", io.BytesIO(image_bytes), "image/jpeg")}
        if audio_bytes:
            files["audio"] = ("voice.ogg", io.BytesIO(audio_bytes), "audio/ogg")
        data = {
            "telegram_id": str(telegram_id),
            "description": description or "",
        }
        if gps_lat and gps_lng:
            data["gps_lat"] = str(gps_lat)
            data["gps_lng"] = str(gps_lng)
        if location_text:
            data["location_text"] = location_text
        resp = requests.post(
            f"{BACKEND_URL}/api/bot/submit-complaint",
            files=files,
            data=data,
            timeout=60
        )
        try:
            return resp.json(), resp.status_code
        except Exception:
            return {"error": f"Server error (HTTP {resp.status_code}). Please try again shortly."}, resp.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def get_user_complaints(telegram_id):
    try:
        resp = requests.get(f"{BACKEND_URL}/api/bot/user-complaints/{telegram_id}", timeout=10)
        return resp.json() if resp.status_code == 200 else []
    except Exception:
        return []

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    contact_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("Share Contact to Link Account", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True
    )

    welcome = (
        f"👋 *Welcome to FixMyHyd, {user.first_name}!*\n\n"
        "I help you report civic issues in Hyderabad directly to GHMC.\n\n"
        "🔗 *Link Your Account*\n"
        "To sync your Telegram reports with your Web Portal account, please share your phone number using the button below.\n\n"
        "📸 *How to report an issue:*\n"
        "Just send me a photo of the problem and I'll walk you through the rest.\n\n"
        "📋 *Commands:*\n"
        "/report — Start a new complaint\n"
        "/mystatus — View your recent reports\n"
        "/portal — Get your portal dashboard link\n"
        "/resetpassword — Generate a new portal password\n"
        "/help — Show this message"
    )

    await update.message.reply_text(welcome, reply_markup=contact_keyboard, parse_mode="Markdown")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact
    phone = contact.phone_number if contact else ""
    
    # Standardize phone number by removing country code (keep only last 10 digits for Indian numbers)
    if phone:
        phone_digits = ''.join(filter(str.isdigit, phone))
        if len(phone_digits) >= 10:
            phone = phone_digits[-10:]
        else:
            phone = phone_digits
        
    try:
        resp = requests.post(f"{BACKEND_URL}/api/bot/register-user", json={
            "telegram_id": str(user.id),
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "username": user.username or "",
            "phone": phone
        }, timeout=10)
        result = resp.json() if resp.status_code == 200 else {}
    except Exception as e:
        print(f"register_user error: {e}")
        result = {}

    created = result.get("created", False)
    linked = result.get("linked", False)
    
    if linked:
        msg = "✅ *Account Linked!*\nYour Telegram account is now synced with your portal account. You can use /report to start reporting issues."
    elif created:
        pwd = result.get("password", "")
        msg = (f"✅ *Account Created!*\nA new portal account was created for you.\n\n"
               f"🌐 *Portal Login:* {BACKEND_URL}/user/login\n"
               f"📞 *Phone:* `{phone}`\n"
               f"🔑 *Password:* `{pwd}`\n\n"
               "You can use /report to start reporting issues.")
    else:
        msg = "✅ You are already registered and your account is ready to use! Send /report to start."
        
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def portal_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🌐 *Your Dashboard*\n\n"
        f"View all your complaints and their status:\n"
        f"{BACKEND_URL}/user/dashboard\n\n"
        f"Your account is linked to Telegram ID: `{user.id}`",
        parse_mode="Markdown"
    )

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    complaints = await asyncio.to_thread(get_user_complaints, user.id)

    if not complaints:
        await update.message.reply_text(
            "You haven't submitted any complaints yet.\nSend a photo to get started! 📸"
        )
        return

    status_icons = {
        "Submitted": "📬", "Acknowledged": "👀",
        "In Progress": "🔧", "Resolved": "✅", "Closed": "🗂️"
    }
    msg = "📋 *Your Recent Reports:*\n\n"
    for c in complaints[:5]:
        icon = status_icons.get(c.get('status', ''), '📌')
        msg += (
            f"{icon} `{c['ghmc_id']}`\n"
            f"   *{c['subject'][:45]}{'...' if len(c.get('subject','')) > 45 else ''}*\n"
            f"   Category: {c['category']} | Priority: {c['priority']}\n"
            f"   Status: *{c['status']}*\n\n"
        )
    msg += f"Full details: {BACKEND_URL}/user/dashboard"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def reset_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.effective_message.reply_text("⏳ *Generating new password...*", parse_mode="Markdown")
    try:
        resp = await asyncio.to_thread(requests.post, f"{BACKEND_URL}/api/bot/reset-password", json={
            "telegram_id": str(user.id)
        }, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            pwd = data.get("password")
            phone = data.get("phone", "Your registered phone")
            msg = (f"✅ *Password Reset Successful!*\n\n"
                   f"🌐 *Portal Login:* {BACKEND_URL}/user/login\n"
                   f"📞 *Phone:* `{phone}`\n"
                   f"🔑 *New Password:* `{pwd}`\n\n"
                   "_Please keep this password safe._")
        else:
            msg = "❌ No linked portal account found. Use /start and share your contact to create one."
    except Exception as e:
        msg = "❌ Server error. Please try again later."
        
    await update.message.reply_text(msg, parse_mode="Markdown")

# ==================== REPORT CONVERSATION ====================

async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📸 *New Complaint*\n\n"
        "Send me a clear photo of the civic issue.\n"
        "_Make sure the issue is visible in the photo._",
        parse_mode="Markdown"
    )
    return WAITING_FOR_PHOTO

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]  # largest size
    file = await photo.get_file()
    photo_bytes = await file.download_as_bytearray()
    context.user_data['photo_bytes'] = bytes(photo_bytes)

    # If photo came with a caption, treat it as description
    if update.message.caption:
        context.user_data['description'] = update.message.caption

    await update.message.reply_text(
        "✅ Photo received!\n\n"
        "📝 Now describe the issue briefly (text or voice message).\n"
        "_(e.g. 'Large pothole on main road near Ameerpet metro')_\n\n"
        "Or type /skip to submit with just the photo.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_DESCRIPTION

async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"[STATE: WAITING_FOR_DESCRIPTION] voice={bool(update.message.voice)} audio={bool(update.message.audio)} text={bool(update.message.text)}")
    if update.message.voice or update.message.audio:
        voice_obj = update.message.voice or update.message.audio
        file = await voice_obj.get_file()
        audio_bytes = await file.download_as_bytearray()
        context.user_data['audio_bytes'] = bytes(audio_bytes)
        context.user_data['description'] = ""
        await update.message.reply_text("🎤 Voice note received! Our AI will transcribe it.")
    else:
        context.user_data['description'] = update.message.text
    return await ask_for_location(update, context)

async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = ""
    return await ask_for_location(update, context)

async def ask_for_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("📍 Share My Location", callback_data="use_location"),
        InlineKeyboardButton("✏️ Type Address", callback_data="type_address"),
    ]]
    await update.effective_message.reply_text(
        "📍 *Where is this issue located?*\n\n"
        "Share your live location or type the address manually.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return WAITING_FOR_LOCATION

async def location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "type_address":
        await query.edit_message_text("✏️ Type the address or nearest landmark:")
        context.user_data['awaiting_text_location'] = True
        return WAITING_FOR_LOCATION
    elif query.data == "use_location":
        await query.edit_message_text(
            "📍 Please send your location using Telegram's location feature.\n"
            "_(Tap the 📎 attachment icon → Location)_"
        )
        return WAITING_FOR_LOCATION

async def receive_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.location:
        context.user_data['gps_lat'] = update.message.location.latitude
        context.user_data['gps_lng'] = update.message.location.longitude
        context.user_data['location_text'] = None
    elif update.message.text:
        context.user_data['location_text'] = update.message.text
        context.user_data['gps_lat'] = None
        context.user_data['gps_lng'] = None
    else:
        await update.message.reply_text("Please send a location or type an address.")
        return WAITING_FOR_LOCATION

    return await submit_report(update, context)

async def submit_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.effective_message.reply_text(
        "⏳ *Submitting your complaint...*\n"
        "_AI is analyzing your photo and description. This takes a few seconds._",
        parse_mode="Markdown"
    )

    result, status_code = await asyncio.to_thread(
        submit_complaint,
        telegram_id=user.id,
        image_bytes=context.user_data.get('photo_bytes'),
        description=context.user_data.get('description', ''),
        gps_lat=context.user_data.get('gps_lat'),
        gps_lng=context.user_data.get('gps_lng'),
        location_text=context.user_data.get('location_text'),
        audio_bytes=context.user_data.get('audio_bytes'),
    )

    context.user_data.clear()

    if status_code == 201 and result.get('status') == 'success':
        ack = result['acknowledgement']
        transcription = ack.get('voice_transcription') or ''
        transcription_line = f"\n🎤 *Voice Transcribed:*\n_{transcription[:300]}_\n" if transcription else ""
        await update.effective_message.reply_text(
            f"✅ *Complaint Submitted Successfully!*\n\n"
            f"🆔 *GHMC ID:* `{ack['ghmc_id']}`\n"
            f"📂 *Category:* {ack['category']}\n"
            f"🚨 *Priority:* {ack['priority']}\n"
            f"📄 *Subject:* {ack['subject']}\n"
            f"{transcription_line}\n"
            f"Track your complaint:\n{ack['portal_url']}\n\n"
            f"Use /mystatus to check updates anytime.",
            parse_mode="Markdown"
        )
    else:
        error_msg = result.get('error', 'Unknown error')
        await update.effective_message.reply_text(
            f"❌ *Submission failed*\n\n`{error_msg}`\n\nPlease try again with /report.",
            parse_mode="Markdown"
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Report cancelled. Send /report to start again.")
    return ConversationHandler.END

# Handle direct photo messages (no /report command needed)
async def handle_direct_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """If user sends a photo outside the conversation, start report flow automatically."""
    # Register user if needed
    await asyncio.to_thread(register_user, update.effective_user)
    context.user_data.clear()
    return await receive_photo(update, context)

async def debug_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        m = update.message
        logging.info(f"[DEBUG] Incoming message: voice={bool(m.voice)} audio={bool(m.audio)} text={bool(m.text)} photo={bool(m.photo)} location={bool(m.location)}")

async def voice_outside_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch voice/audio notes sent when no active conversation is in progress."""
    await update.message.reply_text(
        "🎤 Got your voice note!\n\n"
        "Please send a 📸 *photo* of the issue first, then I'll ask for your description.\n"
        "Or use /report to start the complaint flow.",
        parse_mode="Markdown"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle and silence common benign errors like network timeouts."""
    if isinstance(context.error, telegram.error.NetworkError):
        # Transient network issues resolve themselves
        return
    if isinstance(context.error, telegram.error.Conflict):
        print("\n[ERROR] Telegram Conflict: Another instance of this bot is already running!")
        return
    logging.error(msg="Exception while handling an update:", exc_info=context.error)

# ==================== MAIN ====================

def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")

    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .build()
    )

    report_conv = ConversationHandler(
        entry_points=[
            CommandHandler("report", report_start),
            MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_direct_photo),
        ],
        states={
            WAITING_FOR_PHOTO: [MessageHandler(filters.PHOTO, receive_photo)],
            WAITING_FOR_DESCRIPTION: [
                MessageHandler((filters.TEXT | filters.VOICE | filters.AUDIO) & ~filters.COMMAND, receive_description),
                CommandHandler("skip", skip_description),
            ],
            WAITING_FOR_LOCATION: [
                CallbackQueryHandler(location_callback, pattern="^(use_location|type_address)$"),
                MessageHandler(filters.LOCATION, receive_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_location),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Log every incoming message before any handler (group -1)
    app.add_handler(MessageHandler(filters.ALL, debug_all_messages), group=-1)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("portal", portal_link))
    app.add_handler(CommandHandler("mystatus", my_status))
    app.add_handler(CommandHandler("resetpassword", reset_password))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(report_conv)

    # Fallback: voice/audio sent outside an active conversation
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_outside_conversation))
    app.add_error_handler(error_handler)

    print("FixMyHyd bot is running...")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except telegram.error.Conflict:
        print("\n[ERROR] Telegram Conflict: Another instance of this bot is already running (e.g., deployed on a server).")
        print("Please stop the other instance or use a different test token for local development.\n")

if __name__ == '__main__':
    main()
