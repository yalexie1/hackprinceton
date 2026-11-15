"""get_pano_faces: cache first, fetch and cache on a miss, never store a URL."""
import pytest

from backend.data_layer import api, matterport

SID = "SID123"


def _reply(pano="p1", status="available", n=6):
    return {"data": {"model": {"locations": [{"id": "l", "panos": [
        {"id": pano, "skyboxes": [{"resolution": "2k", "status": status,
                                   "children": [f"https://cdn.example/{pano}/{i}.jpg?sig=x" for i in range(n)]}]}]}]}}}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_ROOT", tmp_path)
    monkeypatch.setattr(api, "_CACHE", tmp_path / "data" / "cache")
    return tmp_path


def test_a_miss_downloads_six_faces_caches_them_and_the_next_call_makes_no_request(root):
    calls = []
    post = lambda q, v: calls.append(("post", v)) or _reply()
    get = lambda url: calls.append(("get", url)) or url.encode()
    faces = api.get_pano_faces(SID, "p1", post=post, download=get)
    assert faces == [f"https://cdn.example/p1/{i}.jpg?sig=x".encode() for i in range(6)]
    assert [c[0] for c in calls] == ["post"] + ["get"] * 6 and calls[0][1] == {"id": SID}
    for i in range(6):
        assert (root / matterport.pano_face_paths(SID, "p1")[i]).read_bytes() == faces[i]
    calls.clear()
    assert api.get_pano_faces(SID, "p1", post=post, download=get) == faces and calls == []


def test_no_url_is_stored_in_the_cache(root):
    api.get_pano_faces(SID, "p1", post=lambda q, v: _reply(), download=lambda u: b"jpegbytes")
    for f in (root / "data" / "cache").rglob("*"):
        if f.is_file():
            assert b"https://" not in f.read_bytes() and f.suffix == ".jpg"


@pytest.mark.parametrize("reply", [_reply(pano="other"), _reply(status="processing"), _reply(n=4),
                                   {"data": {"model": {"locations": []}}}])
def test_a_missing_or_unready_panorama_is_a_lookup_error_and_nothing_is_written(root, reply):
    with pytest.raises(LookupError):
        api.get_pano_faces(SID, "p1", post=lambda q, v: reply, download=lambda u: b"x")
    assert not list((root / "data").rglob("*.jpg"))


def test_an_empty_download_is_refused_and_a_refused_query_raises(root):
    with pytest.raises(LookupError):
        api.get_pano_faces(SID, "p1", post=lambda q, v: _reply(), download=lambda u: b"")
    with pytest.raises(LookupError):
        api.get_pano_faces(SID, "p1", post=lambda q, v: {"errors": [{"message": "no"}]}, download=lambda u: b"x")


def test_defurnished_faces_are_not_offered(root):
    with pytest.raises(LookupError):
        api.get_pano_faces(SID, "p1", True, post=lambda q, v: _reply(), download=lambda u: b"x")
