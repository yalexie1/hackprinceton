"""D17: the one-command CoStar kit mirror.

The kit is **sponsor data under a hackathon licence**, the zip is password-protected
and `COSTAR_KIT_URL` is a signed S3 URL whose query string carries an AWS credential
and signature. **This repo is public.** So the first tests here are not about
mirroring at all - they are about making sure neither secret can reach stdout, a log
line or an exception message, including on the failure paths, which are exactly where
a URL normally gets echoed back.

The archive itself is never committed, so the end-to-end tests build their own zip.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from backend.data_layer import mirror

#: Shaped like the real thing - same query parameters, same ordering - with invented
#: values. If `_describe_url` ever stops stripping the query, these strings appear in
#: the output and the tests below fail.
SIGNED = (
    "https://mp-app-qa.s3.amazonaws.com/hackprinceton2026/doc/costar-hackathon-kit.zip"
    "?response-content-disposition=attachment"
    "&X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=NOTAREALKEYID000000%2F20261114%2Fus-east-1%2Fs3%2Faws4_request"
    "&X-Amz-Signature=deadbeefcafe0000deadbeefcafe0000deadbeefcafe0000deadbeefcafe0000"
)
SECRETS = ("X-Amz-Signature", "X-Amz-Credential", "NOTAREALKEYID", "deadbeefcafe",
           "not-the-real-password")


# ---------- secrets ----------

def test_a_signed_url_is_described_without_its_query():
    described = mirror._describe_url(SIGNED)
    assert described == ("https://mp-app-qa.s3.amazonaws.com/hackprinceton2026/doc/"
                         "costar-hackathon-kit.zip")
    for secret in SECRETS:
        assert secret not in described


def test_the_query_is_stripped_however_the_url_is_shaped():
    """A `split("?")` would be enough for the real URL and would miss a signature in a
    fragment, so `urlsplit` is used. These are the shapes that would slip through a
    looser implementation."""
    for url in (
        "https://h/p?X-Amz-Signature=deadbeefcafe",
        "https://h/p#X-Amz-Signature=deadbeefcafe",
        "https://h/p?a=1#X-Amz-Signature=deadbeefcafe",
        "https://user:deadbeefcafe@h/p",          # credentials in the authority
    ):
        assert "deadbeefcafe" not in mirror._describe_url(url)


def test_a_port_survives_but_credentials_in_the_authority_do_not():
    """`netloc` would keep `user:password@`; `hostname` drops it. No kit URL has
    looked like that, which is why it would have gone unnoticed."""
    assert mirror._describe_url("https://user:deadbeefcafe@h:8443/p") == "https://h:8443/p"


def test_a_download_failure_never_echoes_the_url(monkeypatch, tmp_path):
    """The usual way a signed URL leaks: an httpx error carries `request.url`, and the
    handler puts `exc` in the message. So the handler must not."""
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError(f"connect failed for {SIGNED}")

    monkeypatch.setitem(__import__("sys").modules, "httpx",
                        type("m", (), {"stream": Boom})())
    with pytest.raises(mirror.MirrorFailed) as caught:
        mirror._download(SIGNED, tmp_path, log=lambda _m: None)
    for secret in SECRETS:
        assert secret not in str(caught.value)


def test_a_missing_password_names_the_variable_not_a_value(monkeypatch, tmp_path):
    monkeypatch.delenv(mirror.PASSWORD_ENV, raising=False)
    zip_path = _make_zip(tmp_path / "k.zip", {"commercial-properties.csv": "a\n"})
    with pytest.raises(mirror.MirrorFailed) as caught:
        mirror._extract(zip_path, tmp_path / "out", log=lambda _m: None)
    assert mirror.PASSWORD_ENV in str(caught.value)


def test_no_message_in_the_module_interpolates_a_secret():
    """A grep that cannot be argued with: nothing in the source may format the password
    or the raw URL into a string. `_describe_url(url)` is the only way a URL is
    allowed to appear, and the password may only be passed as an argument."""
    source = Path(mirror.__file__).read_text()
    for forbidden in ('{password}', '{url}', 'environ.get(PASSWORD_ENV)}',
                      'f"{os.environ'):
        assert forbidden not in source, f"{forbidden} would print a secret"


# ---------- where the kit goes ----------

def test_the_target_matches_what_costar_looks_for(monkeypatch, tmp_path):
    """Two resolutions of "where the kit is" that could drift apart, and if they did,
    the mirror would report success while `kit_dir()` still raised `KitMissing`."""
    from backend.data_layer import costar

    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path))
    assert mirror.target_dir() == tmp_path
    (tmp_path / mirror.MARKER).write_text("a\n")
    assert mirror.is_mirrored() is True
    assert costar.kit_dir() == tmp_path


def test_the_default_target_is_the_one_costar_documents(monkeypatch):
    monkeypatch.delenv(mirror.DIR_ENV, raising=False)
    assert mirror.target_dir().parts[-4:] == ("data", "cache", "costar", "kit")


def test_the_marker_is_the_same_file_costar_checks():
    from backend.data_layer import costar

    assert mirror.MARKER in Path(costar.__file__).read_text()


# ---------- the archive shape ----------

def _make_zip(path: Path, files: dict[str, str], prefix: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(f"{prefix}{name}", text)
    return path


def _complete() -> dict[str, str]:
    return {mirror.MARKER: "PropertyId\n1\n", "residential-listings.csv": "ListingId\n1\n",
            "schemas/enums.json": "{}", "models/x.md": "#", "data/x.jsonl": "{}\n"}


def test_a_kit_at_the_archive_root_is_found(tmp_path):
    out = tmp_path / "unpacked"
    out.mkdir()
    (out / mirror.MARKER).write_text("a\n")
    assert mirror._kit_root(out) == out


def test_a_kit_inside_one_wrapping_folder_is_found(tmp_path):
    """`kit_dir()` only checks for the marker, so a wrapped extraction would read as
    "no kit" with every file sitting one directory below it."""
    out = tmp_path / "unpacked"
    (out / "costar-hackathon-kit").mkdir(parents=True)
    (out / "costar-hackathon-kit" / mirror.MARKER).write_text("a\n")
    assert mirror._kit_root(out).name == "costar-hackathon-kit"


def test_an_archive_without_the_marker_is_refused(tmp_path):
    out = tmp_path / "unpacked"
    (out / "something" / "deep").mkdir(parents=True)
    with pytest.raises(mirror.MirrorFailed) as caught:
        mirror._kit_root(out)
    assert mirror.MARKER in str(caught.value)


def test_aes_is_detected_rather_than_reported_as_a_bad_password(tmp_path):
    """Measured on the real kit: it is ZipCrypto (method 8), which `zipfile` handles.
    An AES archive fails identically to a wrong password, so it is checked up front."""
    plain = _make_zip(tmp_path / "plain.zip", {"a.txt": "x"})
    assert mirror.uses_aes(plain) is False

    with zipfile.ZipFile(plain) as z:
        infos = z.infolist()
    assert infos[0].compress_type != 99


# ---------- mirroring, end to end ----------

def test_a_complete_archive_mirrors_and_verifies(tmp_path, monkeypatch):
    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv(mirror.ZIP_ENV,
                       str(_make_zip(tmp_path / "k.zip", _complete())))
    monkeypatch.setenv(mirror.PASSWORD_ENV, "not-the-real-password")

    said: list[str] = []
    where = mirror.mirror(log=said.append)
    assert where == tmp_path / "kit"
    assert (where / mirror.MARKER).is_file()
    assert not mirror._missing(where)
    assert any("mirrored to" in m for m in said)
    for secret in SECRETS:
        assert not any(secret in m for m in said)


def test_a_wrapped_archive_is_flattened_into_place(tmp_path, monkeypatch):
    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv(mirror.ZIP_ENV, str(_make_zip(
        tmp_path / "k.zip", _complete(), prefix="costar-hackathon-kit/")))
    monkeypatch.setenv(mirror.PASSWORD_ENV, "not-the-real-password")

    where = mirror.mirror(log=lambda _m: None)
    assert (where / mirror.MARKER).is_file(), "the wrapper folder was not flattened"


def test_a_truncated_archive_is_refused_rather_than_half_mirrored(tmp_path, monkeypatch):
    """A download that stops early can still contain the marker, and would then read as
    mirrored and fail later one dataset at a time, inside the demo."""
    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv(mirror.ZIP_ENV, str(_make_zip(
        tmp_path / "k.zip", {mirror.MARKER: "PropertyId\n"})))
    monkeypatch.setenv(mirror.PASSWORD_ENV, "not-the-real-password")

    with pytest.raises(mirror.MirrorFailed) as caught:
        mirror.mirror(log=lambda _m: None)
    assert "missing" in str(caught.value)
    assert not (tmp_path / "kit").exists(), "nothing may be left behind"


def test_an_existing_mirror_is_left_alone_unless_forced(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    kit.mkdir()
    for name in mirror.EXPECTED:
        (kit / name).write_text("original\n")
    monkeypatch.setenv(mirror.DIR_ENV, str(kit))
    monkeypatch.setenv(mirror.ZIP_ENV, str(_make_zip(tmp_path / "k.zip", _complete())))
    monkeypatch.setenv(mirror.PASSWORD_ENV, "not-the-real-password")

    said: list[str] = []
    mirror.mirror(log=said.append)
    assert (kit / mirror.MARKER).read_text() == "original\n", "it re-extracted"
    assert any("already mirrored" in m for m in said)

    mirror.mirror(force=True, log=lambda _m: None)
    assert (kit / mirror.MARKER).read_text() == "PropertyId\n1\n", "--force did nothing"


def test_a_local_zip_is_used_without_any_network(tmp_path, monkeypatch):
    """`COSTAR_KIT_ZIP` exists so a machine with an expired signed URL can still
    mirror. Any socket here means the local path is not really local."""
    import socket

    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv(mirror.ZIP_ENV, str(_make_zip(tmp_path / "k.zip", _complete())))
    monkeypatch.setenv(mirror.PASSWORD_ENV, "not-the-real-password")
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: pytest.fail("the mirror opened a socket"))

    assert mirror.mirror(log=lambda _m: None).is_dir()


def test_neither_source_set_says_which_variables_to_set(tmp_path, monkeypatch):
    monkeypatch.delenv(mirror.ZIP_ENV, raising=False)
    monkeypatch.delenv(mirror.URL_ENV, raising=False)
    with pytest.raises(mirror.MirrorFailed) as caught:
        mirror._source_zip(tmp_path, log=lambda _m: None)
    message = str(caught.value)
    assert mirror.ZIP_ENV in message and mirror.URL_ENV in message


def test_a_zip_env_pointing_nowhere_is_a_clear_failure(tmp_path, monkeypatch):
    monkeypatch.setenv(mirror.ZIP_ENV, str(tmp_path / "absent.zip"))
    with pytest.raises(mirror.MirrorFailed) as caught:
        mirror._source_zip(tmp_path, log=lambda _m: None)
    assert mirror.ZIP_ENV in str(caught.value)


# ---------- check ----------

def test_check_reports_an_absent_kit_without_naming_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path / "nothing"))
    monkeypatch.setenv(mirror.PASSWORD_ENV, "not-the-real-password")
    monkeypatch.setenv(mirror.URL_ENV, SIGNED)

    said: list[str] = []
    assert mirror.check(log=said.append) is False
    blob = "\n".join(said)
    assert "NOT set" in blob or "set" in blob
    for secret in SECRETS:
        assert secret not in blob, "check() leaked a value while reporting it is set"


def test_check_reports_an_incomplete_kit_as_incomplete(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / mirror.MARKER).write_text("a\n")
    monkeypatch.setenv(mirror.DIR_ENV, str(kit))

    said: list[str] = []
    assert mirror.check(log=said.append) is False, "the marker alone is not a kit"
    assert "MISSING" in "\n".join(said)


def test_main_exits_nonzero_when_there_is_nothing_to_report(tmp_path, monkeypatch):
    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path / "nothing"))
    assert mirror.main(["--check"]) == 1


def test_main_reports_a_failure_as_an_exit_code_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(mirror.DIR_ENV, str(tmp_path / "nothing"))
    monkeypatch.delenv(mirror.ZIP_ENV, raising=False)
    monkeypatch.delenv(mirror.URL_ENV, raising=False)
    assert mirror.main([]) == 1
    assert "mirror failed" in capsys.readouterr().err


# ---------- live ----------

@pytest.mark.skipif(os.environ.get("RUN_LIVE_NETWORK") != "1",
                    reason="set RUN_LIVE_NETWORK=1")
def test_a_bundle_without_the_kit_still_knows_its_state(monkeypatch, tmp_path):
    """The whole point of D17's first half. Measured 2026-11-14 with the kit hidden:
    the Houston office resolves TX and its real 0.0896 USD/kWh commercial price, where
    the old hard-coded "CA" default gave 0.3002 and net metering in a state with no
    export regime at all.

    **`DATA_LAYER_CACHE_DIR` is not optional here.** The first version of this test
    omitted it and wrote a *kit-less* bundle into the real cache, overwriting the good
    Houston entry - which then made two D16 tests fail with 4,164 m2 instead of
    1,104 m2, because with no kit there is no floor plate to pick the building by. Any
    test that assembles live must point the cache somewhere temporary.
    """
    from backend.data_layer import api, costar, index

    monkeypatch.setenv("DATA_LAYER_LIVE", "1")
    monkeypatch.setenv("COSTAR_KIT_DIR", "/nonexistent-kit")
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path))
    # These are `lru_cache`d on the kit's contents, so hiding the kit has no effect
    # until they are cleared - and leaving them cleared is what keeps the *next* test
    # from inheriting a kit-less index.
    for cached in (costar.enums, costar.rows_by_model, index.by_sid, index.summaries):
        cached.cache_clear()
    try:
        bundle = api.get_property_bundle("L3266YcPPvd", live=True, refresh=True)
    finally:
        for cached in (costar.enums, costar.rows_by_model, index.by_sid, index.summaries):
            cached.cache_clear()

    assert bundle.summary.state == "TX", "the Census geocoder did not fill the state"
    assert bundle.summary.city == "Houston"
    assert bundle.tariff.electricity_usd_per_kwh < 0.15, "a Texas commercial price"
    assert bundle.tariff.export_regime in (None, "none")

    kinds = {n.what for n in bundle.provenance}
    assert "census/state" in kinds and "summary:segment" in kinds
