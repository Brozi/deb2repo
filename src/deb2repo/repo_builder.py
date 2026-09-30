import glob
import os
import subprocess
import textwrap
from functools import cmp_to_key


def generate_compressed_index(
    base_path: str, distro: str, architectures: list[str] = ["amd64", "arm64"]
):
    pool_dir = os.path.join("pool", distro, "main")
    dists_dir = os.path.join(base_path, "dists", distro)

    for arch in architectures:
        binary_dir = os.path.join(dists_dir, "main", f"binary-{arch}")
        os.makedirs(binary_dir, exist_ok=True)

        tmp_uncompressed = os.path.join(binary_dir, "Packages.tmp")
        final_uncompressed = os.path.join(binary_dir, "Packages")

        tmp_compressed = os.path.join(binary_dir, "Packages.gz.tmp")
        final_compressed = os.path.join(binary_dir, "Packages.gz")

        with open(tmp_uncompressed, "wb") as out_file:
            scan_result = subprocess.run(
                ["dpkg-scanpackages", "-a", arch, pool_dir, "/dev/null"],
                cwd=base_path,
                stdout=out_file,
                stderr=subprocess.PIPE,
                check=True,
            )

            if scan_result.returncode != 0:
                if os.path.exists(tmp_compressed):
                    os.remove(tmp_compressed)
                raise RuntimeError(
                    f"dpkg-scanpackages failed with error: {scan_result.stderr.decode()}"
                )

        with open(tmp_uncompressed, "rb") as in_file, open(
            tmp_compressed, "wb"
        ) as out_file:
            gz_result = subprocess.run(
                ["gzip", "-9c"],
                stdin=in_file,
                stdout=out_file,
                stderr=subprocess.PIPE,
                check=True,
            )

            if gz_result.returncode != 0:
                if os.path.exists(tmp_uncompressed):
                    os.remove(tmp_uncompressed)
                if os.path.exists(tmp_compressed):
                    os.remove(tmp_compressed)
                raise RuntimeError(
                    f"gzip failed with error: {gz_result.stderr.decode()}"
                )

        os.replace(tmp_uncompressed, final_uncompressed)
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
    release_conf_path = os.path.join(dists_dir, "apt-release.conf")

    tmp_release_path = os.path.join(dists_dir, "Release.tmp")
    final_release = os.path.join(dists_dir, "Release")

    tmp_gpg = os.path.join(dists_dir, "Release.gpg.tmp")
    final_gpg = os.path.join(dists_dir, "Release.gpg")

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


def get_deb_version(filepath: str) -> str:
    """Extract the version directly from the internal .deb file metadata"""
    try:
        result = subprocess.run(
            ["dpkg-deb", "-f", filepath, "Version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"get_deb_version failed with {e}"


def compare_deb_versions(file_a: str, file_b: str) -> int:
    """Rank versions using dpkg
    return: 1 if A is newer than B"""
    ver_a = get_deb_version(file_a)
    ver_b = get_deb_version(file_b)

    if ver_a == ver_b:
        return 0

    try:
        # dpkg --compare-versions exits with 0 if the condition (gt) is true
        _ = subprocess.run(
            ["dpkg", "--compare-versions", ver_a, "gt", ver_b], check=True
        )
        return 1
    except subprocess.CalledProcessError:
        return -1


def prune_obsolete_binaries(pool_dir: str, keep_count: int = 2):
    """Retains the most recent N binaries for a package and deletes the rest"""
    package_groups = {}
    search_pattern = os.path.join(pool_dir, "*.deb")

    for file_path in glob.glob(search_pattern):
        filename = os.path.basename(file_path)
        parts = filename.replace(".deb", "").split("_")

        pkg_name = parts[0]
        arch = parts[-1]
        group_key = (pkg_name, arch)

        if group_key not in package_groups:
            package_groups[group_key] = []
        package_groups[group_key].append(file_path)

    for (pkg, arch), files in package_groups.items():
        # sort natively by semantic Debian version (highest to lowest)
        files.sort(key=cmp_to_key(compare_deb_versions), reverse=True)

        if len(files) > keep_count:
            obsolete_files = files[keep_count:]
            for old_file in obsolete_files:
                try:
                    os.remove(old_file)
                    print(
                        f"Garbage collection: Pruned {pkg} ({arch}) -> {os.path.basename(old_file)}"
                    )
                except OSError as e:
                    print(f"Error deleting file {old_file}: {e}")
