from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)
