from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, create_engine
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
    # Optional filter. NULL means track every eligible package from this source.
    package_name: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    distro: Mapped[str] = mapped_column(String, index=True)


class RepoArtifact(Base):
    """An exact .deb file downloaded on behalf of one tracked upstream repository"""

    __tablename__ = "repo_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "target_repo_id",
            "relative_path",
            name="uq_repo_artifact_target_repo_path",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target_repo_id: Mapped[int] = mapped_column(
        ForeignKey("target_repos.id", ondelete="CASCADE"), index=True
    )
    package_name: Mapped[str] = mapped_column(String, index=True)
    release_tag: Mapped[str] = mapped_column(String)
    relative_path: Mapped[str] = mapped_column(String, index=True)


Base.metadata.create_all(bind=engine)
