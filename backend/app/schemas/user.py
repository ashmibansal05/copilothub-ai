
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


# ============================================================
# Username Validation
# ============================================================

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


# ============================================================
# Phase 15: Reusable Password Strength Validation
# ============================================================

def check_password_strength(v: str) -> str:
    """
    Validate password strength for registration and
    password changes.

    Requirements:
    - Maximum 72 bytes (bcrypt limitation).
    - At least one letter.
    - At least one number.

    Minimum length is enforced by the Pydantic field.
    """

    if len(v.encode("utf-8")) > 72:
        raise ValueError(
            "Password must be at most 72 bytes long"
        )

    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError(
            "Password must contain at least one letter and one number"
        )

    return v


# ============================================================
# User Registration Schema
# ============================================================

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    full_name: str = Field(
        min_length=1,
        max_length=100,
    )
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-30 characters: "
                "letters, numbers and underscores only"
            )

        return v

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError(
                "Full name cannot be empty"
            )

        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return check_password_strength(v)


# ============================================================
# User Response Schema
# ============================================================

class UserRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime