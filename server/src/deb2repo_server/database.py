from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from deb2repo_server.config import settings

engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})

SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)


class Base(DeclarativeBase):
    pass


class TargetRepo(Base):
    __tablename__ = "target_repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    host: Mapped[str] = mapped_column(String, index=True)
    owner: Mapped[str] = mapped_column(String, index=True)
    repo_name: Mapped[str] = mapped_column(String, index=True)
    last_tag: Mapped[str | None] = mapped_column(String, nullable=True)
    package_name: Mapped[str] = mapped_column(String, index=True)
    distro: Mapped[str] = mapped_column(String, index=True)


Base.metadata.create_all(bind=engine)
