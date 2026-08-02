"""
Web routes for FixMyHyd FastAPI application (HTML templates).
Session-based authentication using signed cookies.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from itsdangerous import URLSafeSerializer, BadSignature

from fixmyhyd.database import get_db_session
from fixmyhyd.models import User, Admin, Complaint, StatusHistory
from fixmyhyd.utils import hash_password, verify_password
from config import settings

web_router = APIRouter()
templates = Jinja2Templates(directory="../templates")

# Session serializer
_session_serializer = URLSafeSerializer(settings.SECRET_KEY, salt="fixmyhyd-session")


def _get_session(request: Request) -> Optional[dict]:
    session_cookie = request.cookies.get("fixmyhyd_session")
    if not session_cookie:
        return None
    try:
        return _session_serializer.loads(session_cookie)
    except BadSignature:
        return None


def _set_session(response: RedirectResponse, session_data: dict) -> RedirectResponse:
    response.set_cookie(
        "fixmyhyd_session",
        _session_serializer.dumps(session_data),
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="Lax",
        secure=not settings.DEBUG,
    )
    return response


def _clear_session(response: RedirectResponse) -> RedirectResponse:
    response.delete_cookie("fixmyhyd_session")
    return response


def _get_current_user(request: Request, db: Session) -> Optional[User]:
    session = _get_session(request)
    if not session:
        return None
    if session.get("type") == "admin":
        return None
    user = db.query(User).filter(User.id == session.get("user_id")).first()
    return user


def _get_current_admin(request: Request, db: Session) -> Optional[Admin]:
    session = _get_session(request)
    if not session:
        return None
    if session.get("type") != "admin":
        return None
    admin = db.query(Admin).filter(Admin.id == session.get("admin_id")).first()
    return admin


# Home page
@web_router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db_session)):
    total = db.query(Complaint).count()
    resolved = db.query(Complaint).filter(Complaint.status == "Resolved").count()
    users = db.query(User).count()
    resolution_rate = round((resolved / total * 100) if total > 0 else 0)
    
    try:
        avg_result = db.query(
            Complaint.created_at, Complaint.updated_at
        ).filter(Complaint.status == "Resolved").all()
        avg_days = 0
        if avg_result:
            days = [(r.updated_at - r.created_at).days for r in avg_result if r.updated_at]
            avg_days = round(sum(days) / len(days)) if days else 0
    except Exception:
        avg_days = 0
    
    stats = {
        "total_complaints": total,
        "resolution_rate": resolution_rate,
        "total_users": users,
        "avg_days": avg_days,
    }
    bot_url = settings.TELEGRAM_BOT_URL
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "admin_stats": stats, "bot_url": bot_url}
    )


# User authentication
@web_router.get("/user/login", response_class=HTMLResponse)
async def user_login_page(request: Request):
    return templates.TemplateResponse("user_login.html", {"request": request})


@web_router.post("/user/login")
async def user_login_post(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_session)
):
    user = db.query(User).filter(User.phone == phone).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "user_login.html",
            {"request": request, "error": "Invalid phone number or password."}
        )
    
    response = RedirectResponse(url="/user/dashboard", status_code=303)
    return _set_session(response, {"type": "user", "user_id": user.id, "name": user.name})


@web_router.get("/user/register", response_class=HTMLResponse)
async def user_register_page(request: Request):
    return templates.TemplateResponse("user_register.html", {"request": request})


@web_router.post("/user/register")
async def user_register_post(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db_session)
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "user_register.html",
            {"request": request, "error": "Passwords do not match."}
        )
    
    existing = db.query(User).filter(User.phone == phone).first()
    if existing:
        return templates.TemplateResponse(
            "user_register.html",
            {"request": request, "error": "Phone number already registered."}
        )
    
    pw_hash = hash_password(password)
    user = User(name=name, phone=phone, password_hash=pw_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    response = RedirectResponse(url="/user/dashboard", status_code=303)
    return _set_session(response, {"type": "user", "user_id": user.id, "name": user.name})


@web_router.get("/user/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request, db: Session = Depends(get_db_session)):
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/user/login", status_code=303)
    
    raw = db.query(Complaint).filter(Complaint.user_id == user.id).order_by(Complaint.created_at.desc()).limit(20).all()
    complaints = []
    for c in raw:
        d = {
            "id": c.id,
            "ghmc_id": c.ghmc_id,
            "category": c.category,
            "priority": c.priority,
            "subject": c.subject,
            "status": c.status,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        complaints.append(d)
    
    total = db.query(Complaint).filter(Complaint.user_id == user.id).count()
    pending = db.query(Complaint).filter(
        Complaint.user_id == user.id,
        Complaint.status.in_(["Submitted", "In Progress", "Acknowledged"])
    ).count()
    resolved = db.query(Complaint).filter(Complaint.user_id == user.id, Complaint.status == "Resolved").count()
    
    stats = {
        "total_complaints": total,
        "pending_complaints": pending,
        "resolved_complaints": resolved,
        "resolution_rate": round((resolved / total * 100) if total > 0 else 0),
    }
    
    return templates.TemplateResponse(
        "user_dashboard.html",
        {"request": request, "user_complaints": complaints, "user_stats": stats, "user_name": user.name}
    )


# Admin authentication
@web_router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@web_router.post("/admin/login")
async def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_session)
):
    admin = db.query(Admin).filter(Admin.username == username).first()
    if not admin or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Invalid username or password."}
        )
    
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    return _set_session(response, {"type": "admin", "admin_id": admin.id, "name": admin.name})


@web_router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db_session)):
    admin = _get_current_admin(request, db)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)
    
    raw = db.query(Complaint).order_by(Complaint.created_at.desc()).all()
    complaints = []
    for c in raw:
        d = {
            "id": c.id,
            "ghmc_id": c.ghmc_id,
            "category": c.category,
            "priority": c.priority,
            "subject": c.subject,
            "status": c.status,
            "location": c.location,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        complaints.append(d)
    
    total = db.query(Complaint).count()
    pending = db.query(Complaint).filter(Complaint.status.in_(["Submitted", "In Progress", "Acknowledged"])).count()
    resolved = db.query(Complaint).filter(Complaint.status == "Resolved").count()
    
    stats = {
        "total_complaints": total,
        "pending_complaints": pending,
        "resolved_complaints": resolved,
        "resolution_rate": round((resolved / total * 100) if total > 0 else 0),
    }
    
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "all_complaints": complaints, "admin_stats": stats, "admin_name": admin.name}
    )


# Report issue
@web_router.get("/report-issue", response_class=HTMLResponse)
async def report_issue_page(request: Request, db: Session = Depends(get_db_session)):
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/user/login", status_code=303)
    return templates.TemplateResponse("report_issue.html", {"request": request, "user_name": user.name})


@web_router.post("/report-issue")
async def report_issue_post(request: Request, db: Session = Depends(get_db_session)):
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/user/login", status_code=303)
    
    form = await request.form()
    description = form.get("description", "")
    location_text = form.get("location_text", "")
    
    image = form.get("image")
    if not image or not image.filename:
        return templates.TemplateResponse(
            "report_issue.html",
            {"request": request, "error": "Image is required.", "user_name": user.name}
        )
    
    image_bytes = await image.read()
    
    from fixmyhyd.services.complaint_service import ComplaintService
    from fixmyhyd.schemas import ComplaintCreate
    
    complaint_service = ComplaintService(db)
    complaint_data = ComplaintCreate(
        description=description,
        location=location_text or None,
        user_id=user.id,
        image=type("UploadFileMock", (), {"file": type("FileMock", (), {"read": lambda: image_bytes})()})(),
    )
    
    try:
        complaint_service.create_complaint(complaint_data)
        return RedirectResponse(url="/user/dashboard", status_code=303)
    except Exception as e:
        return templates.TemplateResponse(
            "report_issue.html",
            {"request": request, "error": f"Failed to submit complaint: {e}", "user_name": user.name}
        )


# Admin status update
@web_router.post("/admin/complaints/{complaint_id}/status")
async def admin_update_status(
    request: Request,
    complaint_id: int,
    status: str = Form(...),
    comments: str = Form(default=""),
    db: Session = Depends(get_db_session)
):
    admin = _get_current_admin(request, db)
    if not admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    old_status = complaint.status
    complaint.status = status
    complaint.updated_at = datetime.utcnow()
    
    status_history = StatusHistory(
        complaint_id=complaint.id,
        old_status=old_status,
        new_status=status,
        changed_by=admin.name,
        comments=comments,
    )
    db.add(status_history)
    db.commit()
    
    return RedirectResponse(url="/admin/dashboard", status_code=303)


@web_router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=303)
    return _clear_session(response)
