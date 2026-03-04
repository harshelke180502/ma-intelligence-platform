from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared declarative base for all ORM models.

    All models inherit from this class so that Base.metadata holds the
    complete schema graph.  Alembic's env.py imports Base from here to
    generate auto-migrations.
    """
