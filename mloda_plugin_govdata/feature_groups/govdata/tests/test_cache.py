"""Level 1: content-addressed download cache and conditional GET."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest
import respx

from mloda_plugin_govdata.feature_groups.govdata.core.cache import CacheMissError, DownloadCache

URL = "https://example.org/data.csv"
BODY = b"Stichtag;Wert\r\n30.06.2020;1\r\n"
ETAG = '"v1"'


@respx.mock
def test_download_and_store(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=BODY, headers={"ETag": ETAG}))
    with DownloadCache(tmp_path) as cache:
        cached = cache.get_or_download(URL)
    assert cached.path.read_bytes() == BODY
    assert cached.sha256 == hashlib.sha256(BODY).hexdigest()
    assert cached.etag == ETAG


@respx.mock
def test_conditional_get_reuses_on_304(tmp_path: Path) -> None:
    calls: dict[str, int] = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.headers.get("If-None-Match") == ETAG:
            return httpx.Response(304)
        return httpx.Response(200, content=BODY, headers={"ETag": ETAG})

    respx.get(URL).mock(side_effect=handler)
    with DownloadCache(tmp_path) as cache:
        first = cache.get_or_download(URL)
        second = cache.get_or_download(URL)
    assert calls["n"] == 2  # second call revalidated and got a 304
    assert first.sha256 == second.sha256
    assert second.path.read_bytes() == BODY


@respx.mock
def test_corrupted_cache_redownloads(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=BODY, headers={"ETag": ETAG}))
    with DownloadCache(tmp_path) as cache:
        first = cache.get_or_download(URL)
        first.path.write_bytes(b"corrupted")  # tamper the stored body
        second = cache.get_or_download(URL)
    assert second.path.read_bytes() == BODY


@respx.mock
def test_unreadable_metadata_redownloads(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=BODY, headers={"ETag": ETAG}))
    with DownloadCache(tmp_path) as cache:
        cache.get_or_download(URL)
        cache._meta_path(URL).write_text("{ not valid json", encoding="utf-8")  # truncated write
        second = cache.get_or_download(URL)
    assert second.path.read_bytes() == BODY


@respx.mock
def test_offline_read_makes_no_request(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=BODY, headers={"ETag": ETAG}))
    with DownloadCache(tmp_path) as cache:
        first = cache.get_or_download(URL)
        second = cache.get_or_download(URL, revalidate=False)
    assert second.sha256 == first.sha256
    assert second.path == first.path
    assert respx.calls.call_count == 1


@respx.mock
def test_offline_miss_raises_naming_url(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=BODY, headers={"ETag": ETAG}))
    with DownloadCache(tmp_path) as cache, pytest.raises(CacheMissError) as excinfo:
        cache.get_or_download(URL, revalidate=False)
    assert URL in str(excinfo.value)
    assert respx.calls.call_count == 0


@respx.mock
def test_meta_without_retrieved_at_is_a_miss(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=BODY, headers={"ETag": ETAG})

    respx.get(URL).mock(side_effect=handler)
    with DownloadCache(tmp_path) as cache:
        cache.get_or_download(URL)
        meta_path = cache._meta_path(URL)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        del meta["retrieved_at"]
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        with pytest.raises(CacheMissError):
            cache.get_or_download(URL, revalidate=False)

        second = cache.get_or_download(URL)
    assert len(calls) == 2  # missing timestamp forces a real re-download, not a revalidation
    assert "If-None-Match" not in calls[1].headers
    assert second.path.read_bytes() == BODY


@respx.mock
def test_retrieved_at_stored_and_kept_on_304(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers.get("If-None-Match") == ETAG:
            return httpx.Response(304)
        return httpx.Response(200, content=BODY, headers={"ETag": ETAG})

    respx.get(URL).mock(side_effect=handler)
    with DownloadCache(tmp_path) as cache:
        first = cache.get_or_download(URL)
        second = cache.get_or_download(URL)
    assert first.retrieved_at.tzinfo is not None
    assert second.retrieved_at == first.retrieved_at
    assert calls[1].headers.get("If-None-Match") == ETAG


@respx.mock
def test_meta_data_file_is_not_trusted(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=BODY, headers={"ETag": ETAG}))
    with DownloadCache(tmp_path) as cache:
        first = cache.get_or_download(URL)
        sha = first.sha256
        meta_path = cache._meta_path(URL)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["data_file"] = "../outside.bin"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        second = cache.get_or_download(URL, revalidate=False)
        assert second.path.parent == tmp_path
        assert second.path.name == f"{sha}.bin"

        meta["sha256"] = "not-a-hash"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with pytest.raises(CacheMissError):
            cache.get_or_download(URL, revalidate=False)
    assert respx.calls.call_count == 1  # only the initial download; no extra HTTP calls


@respx.mock
def test_naive_retrieved_at_is_a_miss(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=BODY, headers={"ETag": ETAG}))
    with DownloadCache(tmp_path) as cache:
        cache.get_or_download(URL)
        meta_path = cache._meta_path(URL)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["retrieved_at"] = "2026-01-01T00:00:00"  # no offset: naive
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with pytest.raises(CacheMissError):
            cache.get_or_download(URL, revalidate=False)
