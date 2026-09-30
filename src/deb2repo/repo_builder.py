import os
import subprocess
import textwrap


def generate_compressed_index(
    base_path: str, distro: str, architectures: list[str] = ["amd64", "arm64"]
):
    pool_dir = os.path.join("pool", distro, "main")
    dists_dir = os.path.join(base_path, "dists", distro)

    for arch in architectures:
        binary_dir = os.path.join(dists_dir, "main", f"binary-{arch}")
        os.makedirs(binary_dir, exist_ok=True)

        tmp_compressed = os.path.join(binary_dir, "Packages.gz.tmp")
        final_compressed = os.path.join(binary_dir, "Packages.gz")

        with open(tmp_compressed, "wb") as out_file:
            p1 = subprocess.Popen(
                ["dpkg-scanpackages", "-a", arch, pool_dir, "/dev/null"],
                cwd=base_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            p2 = subprocess.Popen(
                ["gzip", "-9c"],
                cwd=base_path,
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
        print(f"Succesfully generated Packages.gz for {distro}-{arch}")


def generate_and_sign_release(
    repo_root: str,
    gpg_key_id: str,
    codename: str,
    origin: str,
    architectures: list[str] = ["amd64", "arm64"],
):
    dists_dir = os.path.join(repo_root, "dists", codename)
    release_conf_path = os.path.join(repo_root, "apt-release.conf")

    tmp_release_path = os.path.join(repo_root, "Release.tmp")
    final_release = os.path.join(repo_root, "Release")

    tmp_gpg = os.path.join(repo_root, "Release.gpg.tmp")
    final_gpg = os.path.join(repo_root, "Release.gpg")

    arch_string = " ".join(architectures)

    conf_content = textwrap.dedent(f"""APT::FTPArchive::Release::Origin "{origin}";
    APT::FTPArchive::Release::Label "{origin} - {codename.capitalize()}";
    APT::FTPArchive::Release::Suite "stable";
    APT::FTPArchive::Release::Codename "{codename}";
    APT::FTPArchive::Release::Architectures "{arch_string}";
    APT::FTPArchive::Release::Components "main";
    """)
    with open(release_conf_path, "w") as f:
        _ = f.write(conf_content)

    with open(tmp_release_path, "w") as out_file:
        try:
            _ = subprocess.run(
                [
                    "apt-ftparchive",
                    "release",
                    "-c",
                    release_conf_path,
                    f"dists/{codename}",
                ],
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
                tmp_gpg,
                tmp_release_path,
            ],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        if os.path.exists(tmp_release_path):
            os.remove(tmp_release_path)
        if os.path.exists(tmp_gpg):
            os.remove(tmp_gpg)
        raise RuntimeError(f"GPG signing failed with error: {e.stderr.decode()}")

    os.replace(tmp_release_path, final_release)
    os.replace(tmp_gpg, final_gpg)

    os.remove(release_conf_path)
    print(f"Successfully generated and signed Release for {codename}")
