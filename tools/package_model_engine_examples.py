#!/usr/bin/env python3
"""Build or check the deterministic model/engine download; never deploy a service."""
import argparse
import hashlib
from pathlib import Path
import tempfile
import zipfile

from validate_model_engine_evidence import validate_package


def files(assets: Path) -> dict[str, bytes]:
    result = {}
    for path in sorted(assets.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlinks are not downloadable inputs: {path.name}")
        if path.is_file() and path != assets / "SHA256SUMS":
            result[path.relative_to(assets).as_posix()] = path.read_bytes()
    return result


def package(assets: Path, check: bool = False) -> None:
    validate_package(assets)
    contents = files(assets)
    checksum = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n"
                       for name, data in contents.items()).encode()
    contents["SHA256SUMS"] = checksum
    archive = assets.with_suffix(".zip")
    if not check:
        with tempfile.TemporaryDirectory(prefix=".model-engine-package-", dir=assets.parent) as temp:
            staged = Path(temp) / archive.name
            with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as output:
                for name, data in sorted(contents.items()):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    output.writestr(info, data, compresslevel=9)
            # A concurrent source edit must cause an error instead of a stale download.
            if files(assets) != {k: v for k, v in contents.items() if k != "SHA256SUMS"}:
                raise ValueError("package sources changed during build; retry on a stable tree")
            checksum_staged = Path(temp) / "SHA256SUMS"
            checksum_staged.write_bytes(checksum)
            checksum_staged.replace(assets / "SHA256SUMS")
            staged.replace(archive)
    if (assets / "SHA256SUMS").read_bytes() != checksum:
        raise ValueError("SHA256SUMS does not match every current source file")
    with zipfile.ZipFile(archive) as output:
        if len(output.namelist()) != len(contents) or set(output.namelist()) != set(contents):
            raise ValueError("ZIP file list does not match the configuration directory")
        for name, data in contents.items():
            if output.read(name) != data:
                raise ValueError(f"ZIP content mismatch: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--assets", type=Path,
                        default=Path(__file__).resolve().parents[1] / "docs/assets/model-engine-standard")
    args = parser.parse_args()
    try:
        package(args.assets, check=args.check)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print("PASS: model/engine checksum and ZIP match all package sources")
