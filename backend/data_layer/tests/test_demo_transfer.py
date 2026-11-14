"""D-lane: packing and installing the private demo cache between teammates' laptops.

The point of these tests is that the archive is complete enough to light up the demo on a
laptop that has never fetched anything, and that the tool cannot be used in the one way that
would hurt us: writing sponsor imagery somewhere git would pick it up.
"""

import tarfile
from pathlib import Path

import pytest

from backend.data_layer import demo_transfer as dt


SIDS = ("zvKHR9DHNjJ", "ZSPaQbkGcJJ", "L3266YcPPvd")


@pytest.fixture
def source_cache(tmp_path, monkeypatch):
    """A cache that looks like a laptop which has fetched everything."""
    root = tmp_path / "source"
    for sid in SIDS:
        (root / sid).mkdir(parents=True)
        (root / sid / "bundle.json").write_text('{"bundle": {"sid": "%s"}, "rule": 5}' % sid)
        for name in ("ortho", "oblique-north", "oblique-south", "oblique-east", "oblique-west"):
            d = root / "vexcel-image" / f"{sid}-{name}"
            d.mkdir(parents=True)
            (d / "aabbccdd.jpg").write_bytes(b"\xff\xd8\xff\xe0 not-a-real-jpeg")
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(root))
    return root


def test_pack_then_install_reproduces_every_file(source_cache, tmp_path, monkeypatch):
    archive = tmp_path / "out" / "demo-cache.tgz"
    packed = dt.pack(archive, sids=SIDS)
    assert packed.is_file()

    target = tmp_path / "target"
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(target))
    report = dt.install(packed)

    for sid in SIDS:
        assert (target / sid / "bundle.json").is_file()
        for name in ("ortho", "oblique-north", "oblique-south", "oblique-east", "oblique-west"):
            assert list((target / "vexcel-image" / f"{sid}-{name}").glob("*.jpg"))
    assert report["files"] == 3 * 6          # one bundle + five image dirs, each one file
    assert sorted(report["sids"]) == sorted(SIDS)


def test_pack_refuses_to_write_inside_the_repository(source_cache):
    """Sponsor imagery is hackathon-licensed and this repository is public. An archive inside
    the working tree is one `git add -A` away from being published, so the tool will not make
    one - this is the whole reason the check exists rather than a note in a README."""
    inside = Path(dt.__file__).resolve().parents[2] / "demo-cache.tgz"
    with pytest.raises(ValueError, match="inside the repository"):
        dt.pack(inside, sids=SIDS)
    assert not inside.exists()


def test_check_names_the_features_that_each_missing_piece_disables(source_cache, tmp_path, monkeypatch):
    full = dt.check(sids=SIDS)
    assert full["ready"] is True
    assert full["missing"] == []

    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(empty))
    bare = dt.check(sids=SIDS)
    assert bare["ready"] is False
    # It must say what breaks, not merely that something is absent: a teammate reading this is
    # trying to work out why a tab is missing on their screen.
    joined = " ".join(bare["missing"])
    assert "oblique" in joined.lower() and "aerial" in joined.lower()
    for sid in SIDS:
        assert sid in joined


def test_a_redirected_cache_is_called_out_by_name(tmp_path, monkeypatch):
    """The failure it prevents: obliques are found by cache key and still appear, while the
    orthophoto is a stored repository-relative path and silently does not - so a redirected
    cache costs exactly one tab, which is a baffling thing to debug under time pressure."""
    monkeypatch.delenv("DATA_LAYER_CACHE_DIR", raising=False)
    assert dt.redirect_warning() is None
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "elsewhere"))
    warning = dt.redirect_warning()
    assert warning and "Aerial" in warning and "elsewhere" in warning


def test_install_rejects_paths_that_escape_the_cache(tmp_path, monkeypatch):
    """A tar entry may name `../../.ssh/authorized_keys`. We build these archives ourselves,
    but an archive arrives over AirDrop or a USB stick and is the kind of file that gets
    forwarded, so it is treated as untrusted input."""
    hostile = tmp_path / "hostile.tgz"
    victim = tmp_path / "escaped.txt"
    with tarfile.open(hostile, "w:gz") as tar:
        payload = tmp_path / "payload.txt"
        payload.write_text("owned")
        tar.add(payload, arcname=f"../{victim.name}")

    target = tmp_path / "target"
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(target))
    with pytest.raises(ValueError, match="outside the cache"):
        dt.install(hostile)
    assert not victim.exists()


def test_pack_skips_a_property_with_nothing_cached_and_says_so(source_cache, tmp_path):
    archive = tmp_path / "out" / "partial.tgz"
    dt.pack(archive, sids=(*SIDS, "neverFetched1"))
    listed = dt.contents(archive)
    assert not any("neverFetched1" in name for name in listed)
    assert any("zvKHR9DHNjJ" in name for name in listed)
