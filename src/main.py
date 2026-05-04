import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import Annotated

import qrcode
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.database import get_db, init_db
from src.models import Capsule
from src.schemas import (
    CapsuleCreate,
    CapsuleCreateResponse,
    CapsuleRead,
    CapsuleUpdate,
    HealthResponse,
    LockedCapsuleResponse,
    UnlockedCapsuleResponse,
)


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PUBLIC_CODE_LENGTH = 8


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TimeLock API",
    version="1.0.0",
    description=(
        "Create digital time capsules that stay locked until a specific UTC date. "
        "Each capsule receives a public open link and a QR code."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DbSession = Annotated[Session, Depends(get_db)]


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def public_base_url(request: Request) -> str:
    configured_base_url = os.getenv("PUBLIC_BASE_URL")
    if configured_base_url:
        return configured_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def open_url(request: Request, public_code: str) -> str:
    return f"{public_base_url(request)}/open/{public_code}"


def qr_url(request: Request, capsule_id: int) -> str:
    return f"{public_base_url(request)}/capsules/{capsule_id}/qr"


def generate_public_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(PUBLIC_CODE_LENGTH))


def generate_unique_public_code(db: Session) -> str:
    for _ in range(20):
        public_code = generate_public_code()
        exists = db.scalar(select(Capsule.id).where(Capsule.public_code == public_code))
        if not exists:
            return public_code
    raise HTTPException(status_code=500, detail="Could not generate a unique public code.")


def get_active_capsule(db: Session, capsule_id: int) -> Capsule:
    capsule = db.scalar(
        select(Capsule).where(Capsule.id == capsule_id, Capsule.is_deleted.is_(False))
    )
    if capsule is None:
        raise HTTPException(status_code=404, detail="Capsule not found.")
    return capsule


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(db: DbSession):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed.",
        )
    return {"status": "ok", "database": "connected"}


@app.post(
    "/capsules",
    response_model=CapsuleCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["capsules"],
)
def create_capsule(payload: CapsuleCreate, request: Request, db: DbSession):
    capsule = Capsule(
        title=payload.title.strip(),
        content=payload.content,
        unlock_at=to_utc_naive(payload.unlock_at),
        public_code=generate_unique_public_code(db),
    )
    db.add(capsule)
    db.commit()
    db.refresh(capsule)

    return {
        "id": capsule.id,
        "publicCode": capsule.public_code,
        "openUrl": open_url(request, capsule.public_code),
        "qrUrl": qr_url(request, capsule.id),
    }


@app.get("/capsules", response_model=list[CapsuleRead], tags=["capsules"])
def list_capsules(db: DbSession):
    return db.scalars(
        select(Capsule)
        .where(Capsule.is_deleted.is_(False))
        .order_by(Capsule.created_at.desc())
    ).all()


@app.get("/capsules/{capsule_id}", response_model=CapsuleRead, tags=["capsules"])
def read_capsule(capsule_id: int, db: DbSession):
    return get_active_capsule(db, capsule_id)


@app.put("/capsules/{capsule_id}", response_model=CapsuleRead, tags=["capsules"])
def update_capsule(capsule_id: int, payload: CapsuleUpdate, db: DbSession):
    capsule = get_active_capsule(db, capsule_id)
    updates = payload.model_dump(exclude_unset=True)

    if "title" in updates and updates["title"] is not None:
        capsule.title = updates["title"].strip()
    if "content" in updates and updates["content"] is not None:
        capsule.content = updates["content"]
    if "unlock_at" in updates and updates["unlock_at"] is not None:
        capsule.unlock_at = to_utc_naive(updates["unlock_at"])

    db.commit()
    db.refresh(capsule)
    return capsule


@app.delete("/capsules/{capsule_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["capsules"])
def delete_capsule(capsule_id: int, db: DbSession):
    capsule = get_active_capsule(db, capsule_id)
    capsule.is_deleted = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/capsules/{capsule_id}/qr",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
    tags=["capsules"],
)
def read_capsule_qr(capsule_id: int, request: Request, db: DbSession):
    capsule = get_active_capsule(db, capsule_id)
    image = qrcode.make(open_url(request, capsule.public_code))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get(
    "/open/{public_code}",
    response_model=LockedCapsuleResponse | UnlockedCapsuleResponse,
    tags=["public"],
)
def open_capsule(public_code: str, db: DbSession):
    capsule = db.scalar(
        select(Capsule).where(
            Capsule.public_code == public_code.upper(),
            Capsule.is_deleted.is_(False),
        )
    )
    if capsule is None:
        raise HTTPException(status_code=404, detail="Capsule not found.")

    if utc_now_naive() < capsule.unlock_at:
        unlock_at = capsule.unlock_at.replace(tzinfo=timezone.utc)
        readable_date = unlock_at.date().isoformat()
        return {
            "status": "locked",
            "message": f"This capsule can be opened on {readable_date}.",
            "unlockAt": capsule.unlock_at,
        }

    return {
        "status": "unlocked",
        "title": capsule.title,
        "content": capsule.content,
        "publicCode": capsule.public_code,
    }
