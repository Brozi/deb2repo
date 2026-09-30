from deb2repo import poller, repo_builder
from deb2repo.config import settings
from deb2repo.database import SessionLocal, TargetRepo


def run_polling_cycle(rebuild: bool = False):
    print("Starting background polling cycle...")

    db = SessionLocal()

    try:
        active_distros = db.query(TargetRepo.distro).distinct().all()

        for (distro_name,) in active_distros:
            repos_for_distro = db.query(TargetRepo).filter_by(distro=distro_name).all()

            if rebuild:
                needs_rebuild = True

            needs_rebuild = False

            for repo in repos_for_distro:
                latest_tag = poller.get_latest_tag(
                    repo.host, repo.owner, repo.package_name
                )

                if latest_tag == repo.last_tag:
                    continue

                print(
                    f"New release found for {repo.host}/{repo.owner}/{repo.package_name}: {latest_tag}"
                )

                poller.get_latest_deb(
                    repo.host, repo.owner, repo.package_name, repo.distro
                )

                repo.last_tag = latest_tag
                needs_rebuild = True

            db.commit()

            if needs_rebuild:
                print(f"Changes detected for {distro_name}. Rebuilding index...")
                repo_root = settings.base_repo_path

                try:

                    repo_builder.generate_compressed_index(repo_root, distro_name)

                    repo_builder.generate_and_sign_release(
                        repo_root,
                        settings.gpg_key_id,
                        distro_name,
                        settings.repo_origin,
                    )

                    print(f"Succesfully finalized repository update for {distro_name}.")

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

    finally:
        db.close()
