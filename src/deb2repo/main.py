from poller import get_latest_deb


def main():
    host = "github"
    owner = "dariogriffo"
    repo = "cliamp-debian"
    distro = "noble"
    get_latest_deb(host, owner, repo, distro)


main()
