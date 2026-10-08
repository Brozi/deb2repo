import threading
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from deb2repo_server import poller, repo_builder
from deb2repo_server.config import settings
from deb2repo_server.database import RepoArtifact, SessionLocal, TargetRepo
from deb2repo_server.parser import extract_package_name

_POLL_LOCK = threading.Lock()


def _relative_artifact_path(filepath: Path) -> str:
    repo_root = Path(settings.base_repo_path).resolve()
    return str(filepath.resolve().relative_to(repo_root))


def _record_downloaded_artifacts(
    db: Session, repo: TargetRepo, release_tag: str, downloaded_files: list[Path]
) -> None:

    artifacts_by_path = {
        artifact.relative_path: artifact
        for artifact in db.query(RepoArtifact).filter_by(target_repo_id=repo.id).all()
    }

    for filepath in downloaded_files:
        if not filepath.is_file():
            continue

        relative_path = _relative_artifact_path(filepath)
        package_name = extract_package_name(filepath)

        artifact = artifacts_by_path.get(relative_path)

        if artifact is not None:
            artifact.package_name = package_name
            artifact.release_tag = release_tag
            continue

        artifact = RepoArtifact(
            target_repo_id=repo.id,
            package_name=package_name,
            release_tag=release_tag,
            relative_path=relative_path,
        )

        db.add(artifact)

        artifacts_by_path[relative_path] = artifact


def _remove_missing_artifact_records(db: Session, distro: str) -> None:
    repo_root = Path(settings.base_repo_path).resolve()

    if not repo_root.is_dir():
        return

    artifacts = (
        db.query(RepoArtifact)
        .join(TargetRepo)
        .filter(TargetRepo.distro == distro)
        .all()
    )

    for artifact in artifacts:
        artifact_path = repo_root / artifact.relative_path
        if not artifact_path.is_file():
            db.delete(artifact)


def _rebuild_distro(distro: str) -> None:
    print(f"Rebuilding index for {distro}...")

    try:
        repo_builder.generate_compressed_index(settings.base_repo_path, distro)
        repo_builder.generate_and_sign_release(
            settings.base_repo_path, settings.gpg_key_id, distro, settings.repo_origin
        )
        print(f"Successfully finalized repository update for {distro}")
    except RuntimeError as error:
        print(f"CRITICAL ERROR: Failed to rebuild repo for {distro}: {error}")
    except Exception as error:
        print(f"Unexpected error during repo rebuild for {distro}: {error}")


def rebuild_distro(distro: str) -> None:
    """Rebuild one distro even if it no longer has a tracked upstream repository"""
    with _POLL_LOCK:
        _rebuild_distro(distro)


def run_polling_cycle(rebuild: bool = False):

    if not _POLL_LOCK.acquire(blocking=False):
        print("Warning: Polling cycle already in progress. Skipping duplicate trigger.")
        return

    try:

        print("Starting background polling cycle...")
        db = SessionLocal()

        try:

            active_distros = db.query(TargetRepo.distro).distinct().all()
            if not active_distros:
                print("No active distributions found. Skipping rebuild.")
                return

            for (distro_name,) in active_distros:
                repos_for_distro = (
                    db.query(TargetRepo).filter_by(distro=distro_name).all()
                )

                if rebuild:
                    needs_rebuild = True
                else:

                    needs_rebuild = False

                for repo in repos_for_distro:
                    latest_tag = poller.get_latest_tag(
                        repo.host, repo.owner, repo.repo_name
                    )
                    if latest_tag is None:
                        print(
                            f"No stable release tag for {repo.host}/{repo.owner}/{repo.repo_name}."
                        )
                        continue

                    if latest_tag == repo.last_tag:
                        continue

                    print(
                        f"New release found for {repo.host}/{repo.owner}/{repo.repo_name}: {latest_tag}"
                    )
                    try:

                        downloaded_files: list[Path] | None = poller.get_latest_deb(
                            repo.host,
                            repo.owner,
                            repo.repo_name,
                            repo.distro,
                            repo.package_name,
                        )
                    except Exception as error:

                        print(
                            f"Error polling "
                            f"{repo.host}/{repo.owner}/{repo.repo_name}: {error}"
                        )
                        continue

                    if not downloaded_files:
                        print(
                            f"Warning: No files downloaded for {repo.host}/{repo.owner}/{repo.repo_name}. Skipping DB update"
                        )
                        continue

                    try:
                        _record_downloaded_artifacts(
                            db, repo, latest_tag, downloaded_files
                        )
                        _remove_missing_artifact_records(db, repo.distro)

                        repo.last_tag = latest_tag

                        db.commit()
                    except SQLAlchemyError as error:
                        db.rollback()
                        print(
                            "Error recording downloaded artifacts for "
                            f"{repo.host}/{repo.owner}/{repo.repo_name}: {error}"
                        )
                        continue

                    needs_rebuild = True

                if needs_rebuild:
                    _rebuild_distro(distro_name)
                else:
                    print("No changes detected. Skipping rebuild for {distro_name}.")
        finally:
            db.close()

    finally:
        _POLL_LOCK.release()
        print("Polling cycle completed.")
