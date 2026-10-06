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
