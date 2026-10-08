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
from deb2repo_server.database import RepoArtifact, SessionLocal, TargetRepo
from deb2repo_server.scheduler import rebuild_distro, run_polling_cycle

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
    repo_name: str
    distro: str

    # NULL means track all eligible packages from this source
    package_name: str | None = None

    @field_validator("distro")
    @classmethod
    def validate_distro(cls, value: str) -> str:
        if not re.match(r"^[a-z0-9]+$", value):
            raise ValueError(
                "Distro must be lowercase alphanumeric (e.g., jammy, noble)"
            )
        return value

    @field_validator("package_name")
    @classmethod
    def validate_package_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None

        if not re.fullmatch(r"^[a-z0-9][a-z0-9+,-]*", value):
            raise ValueError("Package name must be a valid Debian binary package name.")
        return value


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
    repos = db.query(TargetRepo).all()
    response = []

    for repo in repos:
        packages = sorted(
            {
                artifact.package_name
                for artifact in db.query(RepoArtifact)
                .filter_by(target_repo_id=repo.id)
                .all()
            }
        )

        response.append(
            {
                "id": repo.id,
                "host": repo.host,
                "owner": repo.owner,
                "repo_name": repo.repo_name,
                "distro": repo.distro,
                "package_name": repo.package_name,  # optional filter
                "packages": packages,  # actual APT package names
            }
        )

    return response


@app.post("/api/repos/add", status_code=201)
def add_repo(
    repo: RepoCreate, background_tasks: BackgroundTasks, db: DbSession, token: AuthDep
):
    existing = (
        db.query(TargetRepo)
        .filter_by(
            host=repo.host,
            owner=repo.owner,
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


def _resolve_artifact_path(
    repo_root: Path, pool_dir: Path, artifact: RepoArtifact
) -> Path:
    relative_path = Path(artifact.relative_path)

    if relative_path.is_absolute():
        raise HTTPException(
            status_code=500,
            detail=f"Invalid absolute artifact path stored for artifact {artifact.id}",
        )

    artifact_path = (repo_root / relative_path).resolve()

    if not artifact_path.is_relative_to(pool_dir):
        raise HTTPException(
            status_code=500,
            detail=f"Artifact path escapes the expected pool directory: {artifact.id}",
        )

    return artifact_path


@app.delete("/api/repos/delete/{repo_id}/")
def remove_repo(
    repo_id: int, background_tasks: BackgroundTasks, db: DbSession, token: AuthDep
):
    repo = db.query(TargetRepo).filter_by(id=repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    artifacts = (
        db.query(RepoArtifact)
        .filter_by(target_repo_id=repo.id)
        .order_by(RepoArtifact.id)
        .all()
    )

    # Don't delete a legacy record while leaving unowned files behind
    if repo.last_tag and not artifacts:
        raise HTTPException(
            status_code=500,
            detail=(
                "This repository has no artifact manifest."
                "Backfill or review its files before deleting it."
            ),
        )

    repo_root = Path(settings.base_repo_path).resolve()
    pool_dir = (repo_root / "pool" / repo.distro / "main").resolve()

    if artifacts and (not repo_root.exists() or not repo_root.is_dir()):
        raise HTTPException(
            status_code=500,
            detail="The repository directory does not exist or is not a directory.",
        )

    removed_files = 0

    for artifact in artifacts:
        artifact_path = _resolve_artifact_path(repo_root, pool_dir, artifact)

        shared_artifact = (
            db.query(RepoArtifact)
            .filter(
                RepoArtifact.relative_path == artifact.relative_path,
                RepoArtifact.target_repo_id != repo.id,
            )
            .first()
        )

        if shared_artifact:
            continue

        if not artifact_path.exists():
            continue

        if not artifact_path.is_file():
            raise HTTPException(
                status_code=500,
                detail=f"Artifact path is not a regular file: {artifact_path}",
            )

        try:
            artifact_path.unlink()
            removed_files += 1
        except OSError as error:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete artifact {artifact_path}: {error}",
            )

    db.query(RepoArtifact).filter_by(target_repo_id=repo.id).delete(
        synchronize_session=False
    )
    db.delete(repo)
    db.commit()

    # This works even when the removed source was the final source for its distro
    background_tasks.add_task(rebuild_distro, repo.distro)

    return {
        "message": f"Successfully purged repository '{repo.repo_name}'.",
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
