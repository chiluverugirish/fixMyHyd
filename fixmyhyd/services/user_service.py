"""
User service for handling user-related business logic.
"""

import secrets
import hashlib
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from fixmyhyd.models import User
from fixmyhyd.schemas import UserCreate, UserResponse


class UserService:
    """Service for user operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def hash_password(self, password: str) -> str:
        """Hash password with salt."""
        salt = secrets.token_hex(16)
        return f"{salt}:{hashlib.sha256((password + salt).encode()).hexdigest()}"
    
    def verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify password against stored hash."""
        try:
            salt, pw_hash = stored_hash.split(":")
            return hashlib.sha256((password + salt).encode()).hexdigest() == pw_hash
        except Exception:
            return False
    
    def create_user(self, user_data: UserCreate) -> UserResponse:
        """Create a new user."""
        # Check if phone already exists
        if user_data.phone:
            existing = self.db.query(User).filter(
                User.phone == user_data.phone
            ).first()
            if existing:
                raise ValueError("Phone number already registered")
        
        # Hash password
        password_hash = self.hash_password(user_data.password)
        
        # Create user
        user = User(
            name=user_data.name,
            phone=user_data.phone,
            email=user_data.email,
            password_hash=password_hash,
            telegram_id=user_data.telegram_id
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        return UserResponse.model_validate(user)
    
    def authenticate_user(self, phone: str, password: str) -> Optional[str]:
        """Authenticate user and return token."""
        user = self.db.query(User).filter(User.phone == phone).first()
        
        if not user or not user.password_hash:
            return None
        
        if not self.verify_password(password, user.password_hash):
            return None
        
        # Generate simple token (in production, use JWT)
        token = secrets.token_urlsafe(32)
        return token
    
    def get_user_by_id(self, user_id: int) -> Optional[UserResponse]:
        """Get user by ID."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        return UserResponse.model_validate(user)
    
    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[UserResponse]:
        """Get user by Telegram ID."""
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return None
        return UserResponse.model_validate(user)
    
    def register_telegram_user(
        self, 
        telegram_id: str, 
        name: str, 
        username: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register or link user from Telegram bot."""
        # Check if user exists by telegram_id
        existing_user = self.db.query(User).filter(
            User.telegram_id == telegram_id
        ).first()
        
        if existing_user:
            # Update phone if provided
            if phone and not existing_user.phone:
                existing_user.phone = phone
                self.db.commit()
                self.db.refresh(existing_user)
            
            return {
                "created": False,
                "linked": bool(phone),
                "user": UserResponse.model_validate(existing_user).model_dump()
            }
        
        # Check if user exists by phone
        if phone:
            existing_by_phone = self.db.query(User).filter(
                User.phone == phone
            ).first()
            
            if existing_by_phone:
                # Link telegram_id to existing user
                existing_by_phone.telegram_id = telegram_id
                self.db.commit()
                self.db.refresh(existing_by_phone)
                
                return {
                    "created": False,
                    "linked": True,
                    "user": UserResponse.model_validate(existing_by_phone).model_dump()
                }
        
        # Create new user
        password = secrets.token_urlsafe(12)
        user_data = UserCreate(
            name=name,
            telegram_id=telegram_id,
            phone=phone,
            password=password
        )
        
        user = self.create_user(user_data)
        
        return {
            "created": True,
            "linked": False,
            "user": user.model_dump(),
            "password": password
        }
    
    def reset_password_telegram(self, telegram_id: str) -> Dict[str, Any]:
        """Reset password for Telegram user."""
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            raise ValueError("User not found")
        
        # Generate new password
        new_password = secrets.token_urlsafe(12)
        user.password_hash = self.hash_password(new_password)
        
        self.db.commit()
        self.db.refresh(user)
        
        return {
            "password": new_password,
            "phone": user.phone or "Your registered phone"
        }
