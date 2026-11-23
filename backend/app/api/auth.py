from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.limits import client_ip, enforce, ip_limit, user_limit
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MessageResponse, TokenResponse
from app.schemas.user import UserCreate, UserRead
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ip_limit("register", 10, 60))],
)
def register(data: UserCreate, db: Session = Depends(get_db)) -> User:
    if user_service.get_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    if user_service.get_by_username(db, data.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username is already taken")
    try:
        return user_service.create_user(db, data)
    except IntegrityError:  # race between check and insert
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already exists")


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    enforce("login-ip", client_ip(request), 20, 60)  # slows down guessing from one machine...
    enforce("login-email", data.email.lower(), 8, 60)  # ...and guessing against one account
    user = user_service.authenticate(db, data.email, data.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(str(user.id))
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout", response_model=MessageResponse)
def logout(_: User = Depends(get_current_user)) -> MessageResponse:
    # JWTs are stateless: the client deletes its token. To revoke every token at once, change the password.
    return MessageResponse(message="Logged out")


@router.post(
    "/change-password", response_model=TokenResponse,
    dependencies=[Depends(user_limit("change-password", 5, 60))],
)
def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Changes the password and invalidates ALL older tokens. Returns a fresh token for this device."""
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The new password must be different")
    user_service.set_password(db, user, data.new_password)
    token, expires_in = create_access_token(str(user.id))
    return TokenResponse(access_token=token, expires_in=expires_in)