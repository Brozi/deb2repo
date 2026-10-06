import re
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, cast

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from deb2repo_server.config import settings
from deb2repo_server.database import SessionLocal, TargetRepo
from deb2repo_server.scheduler import run_polling_cycle

security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifies the incoming Bearer token against the server's configured secret."""

    expected_token = settings.api_token

    if not expected_token:
        raise HTTPException(
            status_code=500, detail="Server API token is not configured."
        )

    if not secrets.compare_digest(credentials.credentials, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


class RepoCreate(BaseModel):
    host: str
    owner: str
    package_name: str | None = None
    repo_name: str
    distro: str

    @field_validator("distro")
    @classmethod
    def validate_distro(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9]+$", v):
            raise ValueError(
                "Distro must be lowercase alphanumeric (e.g., jammy, noble)"
            )
        return v


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    scheduler = BackgroundScheduler()
    polling_interval = cast(dict[str, Any], settings.polling_interval)

    scheduler.add_job(
        func=run_polling_cycle, trigger="interval", **polling_interval, jitter=180
    )
    scheduler.start()
    print(f"Backgrund scheduler activated (Interval: {settings.polling_interval})")

    yield

    scheduler.shutdown()

    print("Backgrund scheduler deactivated")


app = FastAPI(lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
AuthDep = Annotated[str, Depends(verify_token)]


@app.get("/api/repos/list")
def list_repos(db: DbSession, token: AuthDep):
    return db.query(TargetRepo).all()


@app.post("/api/repos/add", status_code=201)
def add_repo(
    repo: RepoCreate, background_tasks: BackgroundTasks, db: DbSession, token: AuthDep
):
    existing = (
        db.query(TargetRepo)
        .filter_by(
            host=repo.host,
            owner=repo.owner,
            package_name=repo.package_name,
            repo_name=repo.repo_name,
            distro=repo.distro,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail=f"Repository already tracked for {repo.distro}"
        )
    new_repo = TargetRepo(
        host=repo.host,
        owner=repo.owner,
        package_name=repo.package_name,
        repo_name=repo.repo_name,
        distro=repo.distro,
        last_tag=None,
    )
    db.add(new_repo)
    db.commit()
    db.refresh(new_repo)

    background_tasks.add_task(run_polling_cycle, rebuild=True)

    return {"message": "Repository added to the polling queue.", "data": new_repo}


@app.delete("/api/repos/delete/{repo_id}/")
def remove_repo(
    repo_id: int, background_tasks: BackgroundTasks, db: DbSession, token: AuthDep
):
    repo = db.query(TargetRepo).filter_by(id=repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    base_repo_path = Path(settings.base_repo_path).resolve()

    if not base_repo_path.exists() or not base_repo_path.is_dir():
        raise HTTPException(
            status_code=500,
            detail="The repo directory does not exist or is not a directory.",
        )

    safe_prefix = f"{repo.package_name}_"

    removed_files = 0

    for file in base_repo_path.glob(f"{safe_prefix}*.deb"):
        if file.is_relative_to(base_repo_path) and file.is_file():
            try:
                file.unlink()
                removed_files += 1
            except OSError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete file {file}: {e}",
                )
    db.delete(repo)
    db.commit()

    background_tasks.add_task(run_polling_cycle)
    return {
        "message": f"Successfully purged package '{repo.repo_name}'",
        "deleted_files_count": removed_files,
    }


@app.post("/api/repos/sync/", status_code=202)
def force_polling_cycle(background_tasks: BackgroundTasks, token: AuthDep):
    """
    Bypasses the 15-minute APScheduler interval and immediately
    forces the polling loop to execute in the background.
    """
    background_tasks.add_task(run_polling_cycle)
    return {"message": "Background sync triggered. Check Docker logs for progress."}


@app.post("/api/repos/rebuild/", status_code=202)
def force_package_rebuild(background_tasks: BackgroundTasks, token: AuthDep):
    """
    Force rebuild of the package indexes without their removal.
    """
    background_tasks.add_task(run_polling_cycle, rebuild=True)
    return {"message": "Background sync triggered. Check Docker logs for progress."}


@app.post("/api/repos/redownload/all/", status_code=202)
def force_redownload_all(
    background_tasks: BackgroundTasks, db: DbSession, token: AuthDep
):
    repos = db.query(TargetRepo).all()
    if not repos:
        raise HTTPException(
            status_code=404, detail="No repositories found to redownload."
        )

    for repo in repos:
        repo.last_tag = None  # Reset last_tag to force redownload
        db.add(repo)

    db.commit()

    background_tasks.add_task(run_polling_cycle)

    return {
        "message": "Global reset complete. Redownload initiated.",
        "affected_count": len(repos),
    }


@app.post("/api/repos/redownload/{repo_id}/", status_code=202)
def force_repo_redownload(
    repo_id: int, background_tasks: BackgroundTasks, db: DbSession, token: AuthDep
):
    repo = db.query(TargetRepo).filter_by(id=repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Wiping the state tricks the poller into treating it as a brand new repository
    repo.last_tag = None
    db.commit()

    background_tasks.add_task(run_polling_cycle)
    return {"message": f"Reset state for '{repo.repo_name}'. Redownload initiated."}
