from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from settings import DATA_ACCESS_MODE, DATABASE_URL
from shared.db.models import Base

from shared.internal_api.client import RemoteSession

ENGINE_DATABASE_URL = (
    'sqlite:///:memory:' if DATA_ACCESS_MODE == 'remote' else DATABASE_URL
)

engine = create_engine(
    ENGINE_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
    if "sqlite" in ENGINE_DATABASE_URL else {},
    pool_pre_ping=True,
)

SessionFactory = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def SessionLocal():
    return SessionFactory()


def init_db():
    if DATA_ACCESS_MODE == 'remote':
        return

    Base.metadata.create_all(bind=engine)


def run_in_session(func, *args, commit: bool = False, **kwargs):
    if DATA_ACCESS_MODE == 'remote':
        return func(RemoteSession(), *args, **kwargs)

    session = SessionLocal()
    try:
        result = func(session, *args, **kwargs)

        if commit:
            session.commit()

        return result

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
