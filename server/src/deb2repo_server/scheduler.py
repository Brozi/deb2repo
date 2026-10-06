from pathlib import Path
import threading
from typing import Any

from deb2repo_server import poller, repo_builder
from deb2repo_server.config import settings
from deb2repo_server.database import SessionLocal, TargetRepo
from deb2repo_server.parser import extract_package_name

_POLL_LOCK = threading.Lock()


def run_polling_cycle(rebuild: bool = False):

    if not _POLL_LOCK.acquire(blocking=False):
        print("Warning: Polling cycle already in progress. Skipping duplicate trigger.")
        return

    try:

        print("Starting background polling cycle...")
        db = SessionLocal()

        try:

            active_distros = db.query(TargetRepo.distro).distinct().all()

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

                    if latest_tag == repo.last_tag:
                        continue

                    print(
                        f"New release found for {repo.host}/{repo.owner}/{repo.repo_name}: {latest_tag}"
                    )

                    downloaded_files: list[Path] | None = poller.get_latest_deb(
                        repo.host,
                        repo.owner,
                        repo.repo_name,
                        repo.distro,
                        repo.package_name,
                    )

                    if not downloaded_files:
                        print(
                            f"Warning: No files downloaded for {repo.host}/{repo.owner}/{repo.repo_name}. Skipping DB update"
                        )
                        continue

                    if not repo.package_name:
                        repo.package_name = downloaded_files[0].name.split("_")[0]
                        print(
                            f"Discovered and saved true package name: '{repo.package_name}'"
                        )

                    repo.last_tag = latest_tag
                    needs_rebuild = True

                db.commit()

                if needs_rebuild:
                    repo_root = settings.base_repo_path
                    print(f"Changes detected for {distro_name}. Rebuilding index...")

                    try:

                        repo_builder.generate_compressed_index(repo_root, distro_name)

                        repo_builder.generate_and_sign_release(
                            repo_root,
                            settings.gpg_key_id,
                            distro_name,
                            settings.repo_origin,
                        )

                        print(
                            f"Successfully finalized repository update for {distro_name}."
                        )

                    except RuntimeError as e:
                        print(
                            f"CRITICAL ERROR: Failed to rebuild repo for {distro_name}: {e}"
                        )

                    except Exception as e:  # noqa: BLE001
                        print(
                            f"Unexpected error during repo rebuild for {distro_name}: {e}"
                        )

                else:
                    print("No changes detected. Skipping rebuild.")

            else:
                if not active_distros:
                    print("No active distributions found. Skipping rebuild")
        finally:
            db.close()

    finally:
        _POLL_LOCK.release()
        print("Polling cycle completed.")
