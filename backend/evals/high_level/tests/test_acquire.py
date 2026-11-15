import hashlib
from io import BytesIO

import pytest

from backend.evals.high_level.acquire_bdg2 import Input, acquire


def spec(content=b"actual,data\n1,2\n"):
    return Input("metadata.csv", "metadata/metadata.csv", len(content), hashlib.sha256(content).hexdigest())


def test_only_verified_bytes_are_published_to_cache(tmp_path):
    data = b"actual,data\n1,2\n"
    result = acquire(spec(data), tmp_path, lambda *a, **kw: BytesIO(data))
    assert result["status"] == "verified"
    assert (tmp_path / "metadata.csv").read_bytes() == data


@pytest.mark.parametrize("data", [b"truncated", b"x" * 1000, b"wrong!,data\n1,2\n"])
def test_bad_size_hash_or_pointer_cannot_be_cached_as_real_data(tmp_path, data):
    with pytest.raises(ValueError):
        acquire(spec(), tmp_path, lambda *a, **kw: BytesIO(data))
    assert not list(tmp_path.iterdir())


def test_wrong_existing_data_is_not_overwritten_or_trusted(tmp_path):
    path = tmp_path / "metadata.csv"
    path.write_bytes(b"not the delivered dataset")
    with pytest.raises(ValueError):
        acquire(spec(), tmp_path, lambda *a, **kw: pytest.fail("must not fetch"))
    assert path.read_bytes() == b"not the delivered dataset"
