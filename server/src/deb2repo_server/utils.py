import subprocess
from pathlib import Path


def extract_package_name(deb_path: Path | str) -> str:
    """Extracts the true package name form a downloaded .deb package"""

    try:
        results = subprocess.run(
            ["dpkg-deb", "-f", str(deb_path), "Package"],
            capture_output=True,
            text=True,
            check=True,
        )
        name = results.stdout.strip()
        if not name:
            raise ValueError("dpkg-deb retrurned an empty string.")
        return name
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to read .deb metadata: {e.stderr}")


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


def get_deb_identity(filepath: str) -> tuple[str, str]:
    """Return the package name and Debian architecture from package metadata"""
    try:
        result = subprocess.run(
            ["dpkg-deb", "-f", filepath, "Package", "Architecture"],
            capture_output=True,
            text=True,
            check=True,
        )

    except subprocess.CalledProcessError as error:
        raise ValueError(f"Unable to read .deb metadata: {error.stderr}") from error

    values = result.stdout.splitlines()
    if len(values) != 2 or not all(values):
        raise ValueError(".deb metadata did not contain Package and Architecture")

    return values[0], values[1]
