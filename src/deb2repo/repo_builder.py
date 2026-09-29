import os
import subprocess
import textwrap


def generate_compressed_index(repo_root: str):
    pool_dir = "pool/main/"

    tmp_compressed = os.path.join(repo_root, "Packages.gz.tmp")
    final_compressed = os.path.join(repo_root, "Packages.gz")

    with open(tmp_compressed, "wb") as out_file:
        p1 = subprocess.Popen(
            ["dpkg-scanpackages", pool_dir, "/dev/null"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        p2 = subprocess.Popen(
            ["gzip", "-9c"],
            cwd=repo_root,
            stdin=p1.stdout,
            stdout=out_file,
            stderr=subprocess.PIPE,
        )

        if p1.stdout is not None:
            p1.stdout.close()

        _, stderr_p2 = p2.communicate()

        if p2.returncode != 0:
            os.remove(tmp_compressed)
            raise RuntimeError(f"Gzip failed with error: {stderr_p2.decode()}")

        _ = p1.wait()
        if p1.returncode != 0:
            os.remove(tmp_compressed)
            if p1.stderr is not None:
                raise RuntimeError(
                    f"dpkg-scanpackages failed with error: {p1.stderr.read().decode()}"
                )
    os.replace(tmp_compressed, final_compressed)
    print("Succesfully generated Packages.gz atomically")


def generate_and_sign_release(
    repo_root: str, gpg_key_id: str, codename: str, origin: str
):
    release_conf_path = os.path.join(repo_root, "apt-release.conf")

    tmp_release_path = os.path.join(repo_root, "Release.tmp")
    final_release = os.path.join(repo_root, "Release")

    tmp_gpg = os.path.join(repo_root, "Release.gpg.tmp")
    final_gpg = os.path.join(repo_root, "Release.gpg")

    conf_content = textwrap.dedent(f"""APT::FTPArchive::Release::Origin "{origin}";
    APT::FTPArchive::Release::Label "{origin} - {codename.capitalize()}";
    APT::FTPArchive::Release::Suite "stable";
    APT::FTPArchive::Release::Codename "{codename}";
    APT::FTPArchive::Release::Architectures "amd64 all";
    APT::FTPArchive::Release::Components "main";
    """)
    with open(release_conf_path, "w") as f:
        f.write(conf_content)

    with open(tmp_release_path, "w") as out_file:
        try:
            _ = subprocess.run(
                ["apt-ftparchive", "release", "-c", release_conf_path, "."],
                cwd=repo_root,
                stdout=out_file,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            if os.path.exists(tmp_release_path):
                os.remove(tmp_release_path)
            raise RuntimeError(f"apt-ftparchive failed with error: {e.stderr.decode()}")
    try:
        _ = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--armor",
                "--detach-sign",
                "--default-key",
                gpg_key_id,
                "--output",
                "Release.gpg.tmp",
                "Release.tmp",
            ],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        os.remove(tmp_release_path)
        if os.path.exists(tmp_gpg):
            os.remove(tmp_gpg)
        raise RuntimeError(f"GPG signing failed with error: {e.stderr.decode()}")

    os.replace(tmp_release_path, final_release)
    os.replace(tmp_gpg, final_gpg)

    os.remove(release_conf_path)
    print("Successfully generated and signed Release and Release.gpg atomically")
