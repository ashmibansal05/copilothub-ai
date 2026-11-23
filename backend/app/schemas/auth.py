from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import check_password_strength


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        return check_password_strength(v)