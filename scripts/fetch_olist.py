"""Download and verify the publisher's immutable Kaggle v2 archive."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

SOURCE = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
DOWNLOAD = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce?datasetVersionNumber=2"
SHA256 = "967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784"


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(target: Path) -> None:
    if target.exists() and checksum(target) == SHA256:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".part")
    try:
        with urlopen(DOWNLOAD, timeout=60) as response, temporary.open("wb") as output:
            for block in iter(lambda: response.read(256 * 1024), b""):
                output.write(block)
        if checksum(temporary) != SHA256:
            raise ValueError("Kaggle archive did not match the pinned v2 SHA-256")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/olist-v2.zip"))
    fetch(parser.parse_args().output)
