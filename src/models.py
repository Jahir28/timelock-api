from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, text
from sqlalchemy.types import Unicode, UnicodeText

from src.database import Base


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Capsule(Base):
    __tablename__ = "Capsules"

    id = Column("Id", Integer, primary_key=True, index=True, autoincrement=True)
    title = Column("Title", Unicode(120), nullable=False)
    content = Column("Content", UnicodeText, nullable=False)
    unlock_at = Column("UnlockAt", DateTime, nullable=False, index=True)
    public_code = Column("PublicCode", Unicode(32), nullable=False, unique=True, index=True)
    is_deleted = Column("IsDeleted", Boolean, nullable=False, default=False, server_default=text("0"))
    created_at = Column("CreatedAt", DateTime, nullable=False, default=utc_now_naive)
