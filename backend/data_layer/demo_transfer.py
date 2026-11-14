"""Move the private demo cache from one teammate's laptop to another.

Why this exists. The three demonstration properties only show their real imagery - the side
angles, the overhead orthophoto - on a laptop that has fetched them. A teammate who clones the
repository and pulls `main` gets the code and nothing else, because sponsor payloads are
hackathon-licensed and this repository is public, so `data/cache/` is git-ignored and must stay
that way. The result on their screen is a property card with only the basemap, and a view
toggle missing its Side angle and Aerial tabs. That looks like a bug and is not one.

So the bytes have to travel outside the repository: laptop to laptop over AirDrop, a USB stick
or a direct transfer, deleted after the event. That is the lead's rule and this tool does not
work around it - it only makes the hand-off repeatable instead of a sequence of `cp` commands
someone types differently each time.

    python -m backend.data_layer.demo_transfer check
    python -m backend.data_layer.demo_transfer pack ~/leto-demo-cache.tgz
    python -m backend.data_layer.demo_transfer install ~/leto-demo-cache.tgz

`check` reports what is present and, for anything missing, which feature it disables. `pack`
refuses to write inside the working tree. `install` treats the archive as untrusted input,
because a file that arrives over AirDrop is a file that gets forwarded.

It never reads, writes or prints a credential. The Matterport SDK key that the 3D model tab
needs lives in `.env`, which is personal; it is not cache and this tool does not touch it.
"""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path
from typing import Iterable, Optional, Sequence

from backend.data_layer.cache import cache_root

#: The three properties the demo shows. Overridable, so this is useful after the event too.
DEMO_SIDS: tuple[str, ...] = ("zvKHR9DHNjJ", "ZSPaQbkGcJJ", "L3266YcPPvd")

#: What each cached artefact is for, in the words a teammate needs when a tab is missing.
_FEATURE = {
    "bundle": "the Aerial tab, and the parcel that cached obliques are keyed on",
    "ortho": "the Aerial tab (the Vexcel orthophoto) and the roof view's base image",
    "oblique": "the Side angle tab (four directions)",
}

_REPO = Path(__file__).resolve().parents[2]


def _entries(root: Path, sid: str) -> list[Path]:
    """Every cached file this property needs, relative to the cache root."""
    found: list[Path] = []
    bundle = root / sid / "bundle.json"
    if bundle.is_file():
        found.append(bundle)
    images = root / "vexcel-image"
    if images.is_dir():
        for folder in sorted(images.glob(f"{sid}-*")):
            found.extend(p for p in sorted(folder.rglob("*")) if p.is_file())
    return found


def check(sids: Sequence[str] = DEMO_SIDS, root: Optional[Path] = None) -> dict:
    """What is here, and what each absence costs on screen."""
    root = Path(root) if root else cache_root()
    missing: list[str] = []
    present: dict[str, int] = {}
    for sid in sids:
        files = _entries(root, sid)
        present[sid] = len(files)
        names = [p.name for p in files]
        if not (root / sid / "bundle.json").is_file():
            missing.append(f"{sid}: no cached bundle - disables {_FEATURE['bundle']}")
        if not any("-ortho" in str(p.parent) for p in files):
            missing.append(f"{sid}: no orthophoto - disables {_FEATURE['ortho']}")
        directions = {
            d for d in ("north", "south", "east", "west")
            if any(f"-oblique-{d}" in str(p.parent) for p in files)
        }
        if len(directions) < 4:
            have = ", ".join(sorted(directions)) or "none"
            missing.append(
                f"{sid}: {len(directions)} of 4 obliques ({have}) - disables {_FEATURE['oblique']}"
            )
        del names
    return {"root": str(root), "ready": not missing, "missing": missing, "files": present}


def pack(archive: Path | str, sids: Sequence[str] = DEMO_SIDS,
         root: Optional[Path] = None) -> Path:
    """Collect the cached imagery for `sids` into a gzipped tar, outside the repository.

    A property with nothing cached is skipped rather than written as an empty folder: the
    archive should describe what the sending laptop actually holds.
    """
    archive = Path(archive).expanduser().resolve()
    try:
        archive.relative_to(_REPO)
    except ValueError:
        pass
    else:
        raise ValueError(
            f"{archive} is inside the repository ({_REPO}). Sponsor imagery is "
            "hackathon-licensed and this repository is public; write the archive to a path "
            "outside the working tree and hand it over directly."
        )
    root = Path(root) if root else cache_root()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for sid in sids:
            for path in _entries(root, sid):
                tar.add(path, arcname=str(path.relative_to(root)))
    return archive


def contents(archive: Path | str) -> list[str]:
    with tarfile.open(Path(archive).expanduser(), "r:gz") as tar:
        return tar.getnames()


def install(archive: Path | str, root: Optional[Path] = None) -> dict:
    """Unpack into the cache root, refusing any entry that would land outside it.

    We build these archives ourselves, but one travels by AirDrop or USB and is exactly the
    kind of file that gets forwarded a second time, so every member is checked before any is
    written - a `../../.ssh/authorized_keys` entry aborts the whole install.
    """
    archive = Path(archive).expanduser()
    root = (Path(root) if root else cache_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    written, sids = 0, set()
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            target = (root / member.name).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise ValueError(
                    f"archive entry {member.name!r} resolves outside the cache "
                    f"({target}); refusing to install any of it"
                ) from None
            if member.issym() or member.islnk():
                raise ValueError(f"archive entry {member.name!r} is a link; refusing to install")
        for member in members:
            tar.extract(member, root, filter="data")
            if member.isfile():
                written += 1
                head = Path(member.name).parts[0]
                sids.add(head if head != "vexcel-image" else Path(member.name).parts[1].split("-")[0])
    return {"root": str(root), "files": written, "sids": sorted(sids)}


def redirect_warning() -> Optional[str]:
    """`DATA_LAYER_CACHE_DIR` set on a demo laptop is a trap, so say so.

    A cached bundle stores its orthophoto as a repository-relative path,
    `data/cache/vexcel-image/<sid>-ortho/<hash>.jpg`, and `get_asset` resolves it against the
    repository root and then refuses anything outside the *configured* cache directory. Point
    the cache elsewhere and that path resolves outside it: the obliques still appear, because
    they are looked up by cache key rather than by a stored path, but the Aerial tab silently
    goes missing. That is a confusing way to lose one tab, so check for it by name.
    """
    import os

    override = os.environ.get("DATA_LAYER_CACHE_DIR")
    if not override:
        return None
    return (
        f"DATA_LAYER_CACHE_DIR is set to {override}. Bundles store the orthophoto as a "
        "repository-relative 'data/cache/...' path, so with the cache redirected the Aerial "
        "tab disappears while the Side angle tab still works. Unset it for the demo."
    )


def _report(result: dict) -> int:
    print(f"cache root: {result['root']}")
    warning = redirect_warning()
    if warning:
        print(f"warning: {warning}")
    for sid, n in result.get("files", {}).items():
        print(f"  {sid}: {n} cached file(s)")
    if result["ready"]:
        print("ready: the three properties have their bundle, orthophoto and four obliques.")
        return 0
    print("\nmissing, and what it costs on screen:")
    for line in result["missing"]:
        print(f"  - {line}")
    print(
        "\nThese are sponsor payloads and cannot come through the repository. Ask a teammate "
        "whose laptop has them to run:\n"
        "    python -m backend.data_layer.demo_transfer pack ~/leto-demo-cache.tgz\n"
        "and hand the file over directly (AirDrop, USB), then:\n"
        "    python -m backend.data_layer.demo_transfer install ~/leto-demo-cache.tgz\n"
        "Delete it after the event. The 3D model tab additionally needs MATTERPORT_SDK_KEY in "
        "your own .env; it is a credential, not cache, and this tool does not move it."
    )
    return 1


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="what is cached, and what any absence disables")
    p = sub.add_parser("pack", help="collect the demo cache into an archive outside the repo")
    p.add_argument("archive")
    i = sub.add_parser("install", help="unpack an archive into this laptop's cache")
    i.add_argument("archive")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "check":
        return _report(check())
    if args.command == "pack":
        out = pack(args.archive)
        print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
        print("Hand it over directly - never through the repository, a link or cloud storage - "
              "and delete it after the event.")
        return 0
    result = install(args.archive)
    print(f"installed {result['files']} file(s) into {result['root']}")
    return _report(check())


if __name__ == "__main__":
    raise SystemExit(main())
