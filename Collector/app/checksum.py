import hashlib
from pathlib import Path


def calculate_sha256(file_path: str | Path) -> str:
    """
    Verilen dosyanın SHA256 checksum değerini hesaplar.
    """
    path = Path(file_path)

    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()