import glob
import os
import subprocess
from functools import cmp_to_key


def get_deb_version(filepath: str) -> str:
    try:
        result = subprocess.run(
            ["dpkg-deb", "-f", filepath, "Version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "0"


def compare_deb_versions(file_a: str, file_b: str) -> int:
    ver_a = get_deb_version(file_a)
    ver_b = get_deb_version(file_b)
    if ver_a == ver_b:
        return 0
    try:
        _ = subprocess.run(
            ["dpkg", "--compare_versions", ver_a, "gt", ver_b], check=True
        )
        return 1
    except subprocess.CalledProcessError:
        return -1


def prune_obsolete_pkgs(pool_dir: str, keep_count: int = 2):
    if keep_count == 0:
        return
    package_groups: dict[tuple[str, str], list[str]] = {}
    search_pattern = os.path.join(pool_dir, "*.deb")

    for filepath in glob.glob(search_pattern):
        filename = os.path.basename(filepath)
        parts = filename.replace(".deb", "").split("-")
        pkg_name = parts[0]
        arch = parts[-1]
        group_key = (pkg_name, arch)

        if group_key not in package_groups:
            package_groups[group_key] = []
        package_groups[group_key].append(filepath)

    for (pkg, arch), files in package_groups.items():
        files.sort(key=cmp_to_key(compare_deb_versions), reverse=True)
        if len(files) > keep_count:
            obsolete_pkgs = files[keep_count:]
            for old_pkg in obsolete_pkgs:
                try:
                    os.remove(old_pkg)
                    print(
                        f"Garbage collection: Pruned {pkg} ({arch}) -> {os.path.basename(old_pkg)}"
                    )
                except OSError as e:
                    print(f"Warning: Failed to delete {old_pkg}: {e}")
