"""Fail-closed Adult input verification, bounded downloads, and atomic cache writes."""

import hashlib
import io

import pytest


@pytest.fixture
def adult(monkeypatch):
    pytest.importorskip("sklearn")
    from examples import adult_income_audit as module

    monkeypatch.setattr(
        module, "FILES", {"adult.data": hashlib.sha256(b"verified bytes\n").hexdigest()}
    )
    monkeypatch.setattr(module, "MAX_DATA_FILE_BYTES", 64)
    return module


class Response(io.BytesIO):
    def __init__(
        self,
        body,
        length=None,
        url="https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.data",
    ):
        super().__init__(body)
        self.headers = {} if length is None else {"Content-Length": str(length)}
        self.url = url

    def geturl(self):
        return self.url


def download(monkeypatch, adult, response):
    monkeypatch.setattr(adult.urllib.request, "urlopen", lambda url, timeout: response)


def test_mismatched_cache_fails_before_any_training(adult, tmp_path, monkeypatch):
    (tmp_path / "adult.data").write_bytes(b"corrupt")
    monkeypatch.setattr(
        adult, "load_split", lambda path: pytest.fail("must not train unverified input")
    )
    with pytest.raises(adult.DatasetIntegrityError, match="No benchmark will run"):
        adult.run(tmp_path, download=False)
    assert (tmp_path / "adult.data").read_bytes() == b"corrupt"


def test_explicit_unverified_opt_in_is_marked_and_warns(adult, tmp_path, capsys):
    (tmp_path / "adult.data").write_bytes(b"experimental input")
    result = adult.ensure_data(tmp_path, download=False, allow_unverified=True)
    assert result == {"adult.data": "digest-mismatch"}
    assert "experimental results" in capsys.readouterr().err


def test_verified_cached_file_needs_no_network(adult, tmp_path, monkeypatch):
    (tmp_path / "adult.data").write_bytes(b"verified bytes\n")
    monkeypatch.setattr(
        adult.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("unexpected network")
    )
    assert adult.ensure_data(tmp_path) == {"adult.data": "verified"}


def test_downloaded_file_is_verified_then_atomically_published(adult, tmp_path, monkeypatch):
    response = Response(b"verified bytes\n", length=15)
    download(monkeypatch, adult, response)
    assert adult.ensure_data(tmp_path) == {"adult.data": "verified"}
    assert (tmp_path / "adult.data").read_bytes() == b"verified bytes\n"
    assert list(tmp_path.glob("*.part")) == []
    assert list(tmp_path.iterdir()) == [tmp_path / "adult.data"]


@pytest.mark.parametrize(
    "body,length",
    [
        (b"wrong bytes", None),
        (b"x" * 65, None),
        (b"x", 65),
        (b"x", -1),
        (b"x", "invalid"),
        (b"verified bytes\n", 14),
    ],
)
def test_invalid_downloads_do_not_leave_cache_or_partial_files(
    adult, tmp_path, monkeypatch, body, length
):
    download(monkeypatch, adult, Response(body, length))
    with pytest.raises(adult.DatasetIntegrityError):
        adult.ensure_data(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_size_bound_cannot_be_bypassed_with_unverified_opt_in(adult, tmp_path):
    (tmp_path / "adult.data").write_bytes(b"x" * 65)
    with pytest.raises(adult.DatasetIntegrityError, match="size limit"):
        adult.ensure_data(tmp_path, allow_unverified=True)


@pytest.mark.parametrize(
    "url", ["http://archive.ics.uci.edu/file", "https://attacker.example/file"]
)
def test_redirect_cannot_downgrade_or_leave_the_trusted_origin(adult, tmp_path, monkeypatch, url):
    download(monkeypatch, adult, Response(b"verified bytes\n", url=url))
    with pytest.raises(adult.DatasetIntegrityError, match="trusted HTTPS"):
        adult.ensure_data(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_interrupted_read_preserves_an_existing_cache_and_cleans_temporary_file(
    adult, tmp_path, monkeypatch
):
    path = tmp_path / "adult.data"
    path.write_bytes(b"existing cache")

    class Interrupted(Response):
        def read(self, size=-1):
            raise OSError("interrupted")

    download(monkeypatch, adult, Interrupted(b""))
    with pytest.raises(OSError):
        adult._download_verified(path, adult.FILES["adult.data"], False)
    assert path.read_bytes() == b"existing cache"
    assert list(tmp_path.iterdir()) == [path]


def test_cli_requires_explicit_opt_in_for_experimental_cache(adult, tmp_path):
    (tmp_path / "adult.data").write_bytes(b"not pinned")
    with pytest.raises(adult.DatasetIntegrityError):
        adult.main(["--data-dir", str(tmp_path), "--no-download"])
