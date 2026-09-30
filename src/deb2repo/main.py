from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from deb2repo.database import SessionLocal, TargetRepo
from deb2repo.scheduler import run_polling_cycle


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


@app.post("/api/repos/")
def add_repo(
    host: str, owner: str, package_name: str, distro: str, db: Session = Depends(get_db)
):
    existing = (
        db.query(TargetRepo)
        .filter_by(host=host, owner=owner, package_name=package_name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Repository already tracked")
    new_repo = TargetRepo(
        host=host, owner=owner, package_name=package_name, distro=distro
    )
    db.add(new_repo)
    db.commit()

    return {
        "status": "success",
        "message": f"Added {host}/{owner}/{package_name} {distro} to the polling queue.",
    }


@app.post("/sync/", status_code=202)
def force_polling_cycle(background_tasks: BackgroundTasks):
    """
    Bypasses the 15-minute APScheduler interval and immediately
    forces the polling loop to execute in the background.
    """
    background_tasks.add_task(run_polling_cycle)
    return {"message": "Background sync triggered. Check Docker logs for progress."}
