from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_engine(
    "sqlite:///./repo_state.db", connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TargetRepo(Base):

    __tablename__ = "target_repos"

    id = Column(Integer, primary_key=True, index=True)
    host = Column(String, index=True)
    owner = Column(String, index=True)
    package_name = Column(String, index=True)
    last_tag = Column(String, nullable=True)
    distro = Column(String, index=True)


Base.metadata.create_all(bind=engine)
