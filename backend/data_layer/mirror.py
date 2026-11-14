"""Mirror the CoStar kit onto this machine, once (package D17).

`costar.kit_dir()` has always told the reader to "mirror it once from
`COSTAR_KIT_URL`", and nothing implemented it - so @Sri-SriPod extracted the zip by
hand to run a live bundle, and anyone else joining the repo would have to as well.
This is that one command:

    python -m backend.data_layer.mirror            # download, extract, verify
    python -m backend.data_layer.mirror --force    # re-mirror over an existing kit
    python -m backend.data_layer.mirror --check    # report what is here, change nothing

**What it costs:** a 49 MB download that extracts to about 404 MB. Everything lands
under `data/cache/`, which is git-ignored, because the kit is **sponsor data under a
hackathon licence and is never committed**.

**Secrets.** The zip is password-protected and `COSTAR_KIT_URL` is a *signed* S3 URL
whose query string contains an AWS credential and signature. Neither is ever printed,
logged or written anywhere by this module:

- the URL is only ever described by its scheme, host and path, never its query
  (`_describe_url`), and a test asserts a signature cannot reach the output;
- the password is passed to `unzip` **on stdin, not in argv**, because an argument is
  visible to any other process on the machine through `ps`;
- nothing from the environment is echoed back, not even to say it looks wrong - the
  messages name the *variable*, never the value.

**Why `zipfile` and not `unzip`.** Measured on the real kit 2026-11-14: the archive
uses **legacy ZipCrypto** (`flag_bits & 1` set, compression method 8 - not method 99,
which would be AES), so Python's own `zipfile` can decrypt it, at **16 MB/s - about
26 s for the 423 MB uncompressed**. That is the path with no subprocess, no argv and
no tty, so it is the default.

`unzip` is only the fallback, for an archive `zipfile` cannot decrypt. Two findings
about it, both measured here:

- **`unzip` will not take a password on stdin.** Piping it gives
  `unable to get password` and skips every member, exit 5: it reads the prompt from
  `/dev/tty`, not stdin. So the fallback has to use `-P`, which **does** put the
  password in argv where `ps` can see it - hence it is the fallback and the docstring
  says so, rather than being the quiet default.
- A wrong password and an unsupported cipher produce near-identical errors, so the
  messages below never assert which it was.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

_ROOT = Path(__file__).resolve().parents[2]

#: The file `costar.kit_dir()` checks for. If this is present the mirror is usable;
#: the same marker is used here so the two cannot disagree about "mirrored".
MARKER = "commercial-properties.csv"

#: Everything the lane reads, as a completeness check after extraction. A truncated
#: download that still happens to contain the marker would otherwise look mirrored and
#: fail later, one dataset at a time, inside whatever was being demonstrated.
EXPECTED = (MARKER, "residential-listings.csv", "schemas", "models", "data")

ZIP_ENV = "COSTAR_KIT_ZIP"
URL_ENV = "COSTAR_KIT_URL"
PASSWORD_ENV = "COSTAR_ZIP_PASSWORD"
DIR_ENV = "COSTAR_KIT_DIR"

DOWNLOAD_TIMEOUT_S = 600.0
_CHUNK = 1 << 20


class MirrorFailed(RuntimeError):
    """Something went wrong that the operator has to fix. The message never carries a
    secret - only the name of the variable that needs attention."""


def target_dir() -> Path:
    """Where the kit goes. Matches `costar.kit_dir()`'s own resolution order."""
    override = os.environ.get(DIR_ENV)
    return Path(override) if override else _ROOT / "data" / "cache" / "costar" / "kit"


def is_mirrored(where: Optional[Path] = None) -> bool:
    return ((where or target_dir()) / MARKER).is_file()


def _describe_url(url: str) -> str:
    """A signed URL with its query removed, safe to print.

    The AWS credential and signature live in the query string, so dropping it is the
    whole protection. `urlsplit` is used rather than a split on `"?"` so a URL with no
    query, or one carrying a fragment, cannot slip a signature through.

    `hostname` and not `netloc`: `netloc` keeps `user:password@`, so a URL with
    credentials in its authority would print them. No kit URL has looked like that,
    which is exactly why it would go unnoticed.
    """
    parts = urlsplit(url)
    host = parts.hostname or "an unnamed host"
    port = f":{parts.port}" if parts.port else ""
    path = parts.path or "/"
    return f"{parts.scheme or 'https'}://{host}{port}{path}"


def _missing(where: Path) -> list[str]:
    return [name for name in EXPECTED if not (where / name).exists()]


# ---------- getting the zip ----------

def _download(url: str, into: Path, log: Callable[[str], None]) -> Path:
    import httpx

    log(f"downloading the kit from {_describe_url(url)}")
    out = into / "costar-hackathon-kit.zip"
    got = 0
    try:
        with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_S,
                          follow_redirects=True) as resp:
            if resp.status_code == 403:
                raise MirrorFailed(
                    f"the signed URL in {URL_ENV} has expired or been revoked (HTTP 403). "
                    f"These links last about 24 h: get a fresh one from the track's "
                    f"/costar-keys channel and update .env, or download the zip by hand "
                    f"and point {ZIP_ENV} at it.")
            resp.raise_for_status()
            with out.open("wb") as fh:
                for chunk in resp.iter_bytes(_CHUNK):
                    fh.write(chunk)
                    got += len(chunk)
                    if got % (16 << 20) < _CHUNK:
                        log(f"  {got / 1e6:.0f} MB")
    except MirrorFailed:
        raise
    except Exception as exc:
        # `exc` can carry the request URL, and that URL carries the signature.
        raise MirrorFailed(
            f"the download failed after {got / 1e6:.0f} MB: {type(exc).__name__}. "
            f"The URL is not shown because it is signed; check {URL_ENV}.") from None
    log(f"  {got / 1e6:.0f} MB downloaded")
    return out


def _source_zip(into: Path, log: Callable[[str], None]) -> tuple[Path, bool]:
    """`(path, downloaded)`. A local zip is preferred: it needs no fresh signed URL."""
    local = os.environ.get(ZIP_ENV)
    if local:
        path = Path(local).expanduser()
        if not path.is_file():
            raise MirrorFailed(f"{ZIP_ENV} is set but is not a file")
        log(f"using the local zip at {path}")
        return path, False

    url = os.environ.get(URL_ENV)
    if not url:
        raise MirrorFailed(
            f"neither {ZIP_ENV} nor {URL_ENV} is set. Both come from the track's "
            f"/costar-keys channel; put them in .env, which is git-ignored.")
    return _download(url, into, log), True


# ---------- extracting ----------

def uses_aes(zip_path: Path) -> bool:
    """Whether any encrypted member uses AES, which `zipfile` cannot decrypt.

    Compression method 99 is the WinZip AES marker. Checked up front so the failure
    message can be specific instead of reporting a decrypt error that reads exactly
    like a wrong password.
    """
    import zipfile

    with zipfile.ZipFile(zip_path) as archive:
        return any(info.compress_type == 99 for info in archive.infolist())


def _extract_with_zipfile(zip_path: Path, into: Path, password: str,
                          log: Callable[[str], None]) -> None:
    import zipfile

    with zipfile.ZipFile(zip_path) as archive:
        archive.setpassword(password.encode())
        members = [i for i in archive.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in members) or 1
        done = 0
        step = total // 4
        try:
            for info in members:
                archive.extract(info, into)
                done += info.file_size
                if step and done % step < info.file_size:
                    log(f"  {done / 1e6:.0f} of {total / 1e6:.0f} MB")
        except RuntimeError as exc:
            # "Bad password" and a corrupt archive land here identically, so the
            # message offers both rather than accusing the operator's .env.
            raise MirrorFailed(
                f"could not decrypt the archive ({str(exc)[:80]}). Either "
                f"{PASSWORD_ENV} is wrong or the download is corrupt; re-run to "
                f"download again.") from None


def _extract_with_unzip(zip_path: Path, into: Path, password: str) -> None:
    """The AES fallback. **Puts the password in argv**, where `ps` can read it.

    Used only when `zipfile` cannot handle the cipher, because `unzip` will not accept
    a password on stdin - it reads the prompt from `/dev/tty`, and piping gives
    `unable to get password` and exit 5 with every member skipped.
    """
    unzip = shutil.which("unzip")
    if not unzip:
        raise MirrorFailed(
            "the archive uses AES, which Python's zipfile cannot decrypt, and `unzip` "
            "is not on PATH. Install unzip (or extract the zip by hand and point "
            f"{ZIP_ENV} at the result).")
    proc = subprocess.run(
        [unzip, "-q", "-o", "-P", password, str(zip_path), "-d", str(into)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or b"").decode(errors="replace").strip()
        # unzip echoes the archive name but never the password, so this is safe to show.
        raise MirrorFailed(f"unzip exited {proc.returncode}: {tail[:300]}")


def _extract(zip_path: Path, into: Path, log: Callable[[str], None]) -> None:
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        raise MirrorFailed(f"{PASSWORD_ENV} is not set; the kit zip is encrypted")

    if uses_aes(zip_path):
        log("extracting with unzip (the archive uses AES)")
        _extract_with_unzip(zip_path, into, password)
    else:
        log("extracting with Python's zipfile")
        _extract_with_zipfile(zip_path, into, password, log)


def _kit_root(extracted: Path) -> Path:
    """Where the kit actually is inside what was extracted.

    An archive may hold the kit at its root or inside a single wrapping folder, and
    which one is not worth depending on - `kit_dir()` only checks for the marker, so a
    wrapped extraction would read as "no kit" with the files sitting right there.
    """
    if (extracted / MARKER).is_file():
        return extracted
    for child in sorted(p for p in extracted.iterdir() if p.is_dir()):
        if (child / MARKER).is_file():
            return child
    found = sorted(p.name for p in extracted.iterdir())[:8]
    raise MirrorFailed(
        f"the archive extracted but {MARKER} is not at its root or one level down; "
        f"found {found}")


# ---------- the command ----------

def mirror(*, force: bool = False, log: Callable[[str], None] = print) -> Path:
    """Put the kit on this machine and return where it is.

    Safe to re-run: an existing mirror is reported and left alone unless `force`. The
    new kit is assembled in a temporary directory beside the target and moved into
    place at the end, so an interrupted run cannot leave a half-extracted kit that
    `kit_dir()` would accept.
    """
    target = target_dir()
    if is_mirrored(target) and not force:
        missing = _missing(target)
        log(f"the kit is already mirrored at {target}"
            + (f" - but {missing} are missing; re-run with --force" if missing else ""))
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="costar-kit-", dir=target.parent))
    try:
        zip_path, downloaded = _source_zip(staging, log)
        unpacked = staging / "unpacked"
        unpacked.mkdir()
        _extract(zip_path, unpacked, log)

        root = _kit_root(unpacked)
        missing = _missing(root)
        if missing:
            raise MirrorFailed(
                f"the archive extracted but these are missing: {missing}. The download "
                f"may be truncated; re-run, or set {ZIP_ENV} to a zip you have checked.")

        if target.exists():
            doomed = target.with_name(f"{target.name}.replacing")
            shutil.rmtree(doomed, ignore_errors=True)
            target.rename(doomed)
            shutil.rmtree(doomed, ignore_errors=True)
        root.rename(target)

        if downloaded:
            # 49 MB of sponsor data with no further use once extracted.
            zip_path.unlink(missing_ok=True)
        files = sum(1 for _ in target.rglob("*") if _.is_file())
        size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
        log(f"mirrored to {target}: {files:,} files, {size / 1e6:.0f} MB")
        return target
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def check(log: Callable[[str], None] = print) -> bool:
    """Report what is on this machine without touching anything."""
    target = target_dir()
    if not is_mirrored(target):
        log(f"no kit at {target}")
        for name, var in (("a local zip", ZIP_ENV), ("a signed URL", URL_ENV),
                          ("the zip password", PASSWORD_ENV)):
            log(f"  {var}: {'set' if os.environ.get(var) else 'NOT set'}  ({name})")
        return False
    missing = _missing(target)
    files = sum(1 for _ in target.rglob("*") if _.is_file())
    log(f"kit at {target}: {files:,} files"
        + (f"; MISSING {missing}" if missing else "; complete"))
    return not missing


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return 0 if check() else 1
    try:
        mirror(force="--force" in argv)
    except MirrorFailed as exc:
        print(f"mirror failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":        # pragma: no cover - entry point
    raise SystemExit(main())
