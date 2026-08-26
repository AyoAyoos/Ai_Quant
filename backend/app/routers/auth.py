from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.database import get_db
from app.models import User
from app.schemas import SignupRequest, LoginRequest, AuthResponse
from app.config import settings 


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

password_hash = PasswordHash.recommended()

SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def create_access_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": user_id,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED
)
def signup(
    data: SignupRequest,
    db: Session = Depends(get_db)
):
    existing_user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="An account with this email already exists."
        )

    hashed_password = password_hash.hash(data.password)

    new_user = User(
        email=data.email,
        password_hash=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(str(new_user.id))

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=str(new_user.id),
        email=new_user.email
    )


@router.post(
    "/login",
    response_model=AuthResponse
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if not password_hash.verify(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    access_token = create_access_token(str(user.id))

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=str(user.id),
        email=user.email
    )