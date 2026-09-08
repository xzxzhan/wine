from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR / 'wine.db'}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    from app import models  # noqa: F401  (register models with SQLModel metadata)

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
