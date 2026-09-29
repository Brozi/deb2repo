from deb2repo import poller, repo_builder
from deb2repo.database import SessionLocal, TargetRepo


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
            print("Changes detected. Triggering rebuild...")
            repo_builder.sign_and_build_repos()
        else:
            print("No changes detected. Skipping rebuild.")

    finally:
        db.close()
