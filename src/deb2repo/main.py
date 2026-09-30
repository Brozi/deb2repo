import re
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from deb2repo.database import SessionLocal, TargetRepo
from deb2repo.scheduler import run_polling_cycle


class RepoCreate(BaseModel):
    host: str
    owner: str
    package_name: str
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
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_polling_cycle, "interval", minutes=15)
    scheduler.start()
    print("Backgrund scheduler activated")

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


@app.get("/repos/")
def list_repos(db: Session = Depends(get_db)):
    return db.query(TargetRepo).all()


@app.post("/repos/")
def add_repo(repo: RepoCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(TargetRepo)
        .filter_by(
            host=repo.host,
            owner=repo.owner,
            package_name=repo.package_name,
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
        distro=repo.distro,
        last_tag=None,
    )
    db.add(new_repo)
    db.commit()
    db.refresh(new_repo)

    return {"message": "Repository added to the polling queue.", "data": new_repo}


@app.delete("/repos/{repo_id}/")
def remove_repo(repo_id: int, db: Session = Depends(get_db)):
    repo = db.query(TargetRepo).filter_by(id=repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    db.delete(repo)
    db.commit()
    return {"message": f"Successfully stopped tracking repository with ID {repo_id}"}


@app.post("/sync/", status_code=202)
def force_polling_cycle(background_tasks: BackgroundTasks):
    """
    Bypasses the 15-minute APScheduler interval and immediately
    forces the polling loop to execute in the background.
    """
    background_tasks.add_task(run_polling_cycle)
    return {"message": "Background sync triggered. Check Docker logs for progress."}
