import os

from deb2repo import poller, repo_builder
from deb2repo.database import SessionLocal, TargetRepo

GPG_KEY_ID = os.environ.get("GPG_KEY_ID")
REPO_ORIGIN = os.environ.get("REPO_ORIGIN", "My Custom Repo")


def run_polling_cycle():
    print("Starting background polling cycle...")

    db = SessionLocal()

    try:
        repos = db.query(TargetRepo).all()
        needs_rebuild = False

        for repo in repos:
            latest_tag = poller.get_latest_tag(repo.host, repo.owner, repo.name)

            if latest_tag == repo.last_tag:
                continue

            print(
                f"New release found for {repo.host}/{repo.owner}/{repo.name}: {latest_tag}"
            )

            poller.get_latest_deb(repo.host, repo.owner, repo.name, repo.distro)

            repo.last_tag = latest_tag

        db.commit()

        if needs_rebuild:
            print("Changes detected for {repo.distro}. Rebuilding index...")
            repo_root = f"/app/repo/{repo.distro}"

            os.makedirs(os.path.join(repo_root, "pool", "main"), exist_ok=True)

            try:

                repo_builder.generate_compressed_index(repo_root)

                repo_builder.generate_and_sign_release(
                    repo_root, GPG_KEY_ID, repo.distro, REPO_ORIGIN
                )

                print(f"Succesfully finalized repository update for {repo.distro}.")

            except RuntimeError as e:
                print(f"CRITICAL ERROR: Failed to rebuild repo for {repo.distro}: {e}")

            except Exception as e:  # noqa: BLE001
                print(f"Unexpected error during repo rebuild for {repo.distro}: {e}")

        else:
            print("No changes detected. Skipping rebuild.")

    finally:
        db.close()
