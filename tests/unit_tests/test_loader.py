import pytest
from langchain_core.documents import Document

from langchain_mesharc import MeshArcLoader
from tests.fake import FakeMeshArc


def load(**kwargs):
    client = FakeMeshArc()
    docs = MeshArcLoader(client=client, **kwargs).load()
    return docs, client


def test_scrape_one_url():
    docs, client = load(url="https://e.test/pricing")
    assert len(docs) == 1 and isinstance(docs[0], Document)
    doc = docs[0]
    assert doc.page_content.startswith("# Page")
    assert doc.id == "https://e.test/pricing"
    assert doc.metadata["source"] == doc.metadata["url"] == "https://e.test/pricing"
    assert doc.metadata["title"] == "Title of https://e.test/pricing"
    assert doc.metadata["status"] == 200 and doc.metadata["verdict"] == "ok" and doc.metadata["page_status"] == "ok"
    assert doc.metadata["mode"] == "scrape" and doc.metadata["crawled_at"] == "2026-10-15T10:00:00Z"
    assert doc.metadata["credits"] == 1
    assert client.calls == [("scrape", "https://e.test/pricing", {})]


def test_scrape_batch_reads_the_rows_under_pages_and_skips_empty_ones_unless_asked():
    urls = ["https://e.test/a", "https://e.test/blocked", "https://e.test/robots"]
    docs, client = load(url=urls)
    assert [d.metadata["url"] for d in docs] == ["https://e.test/a"]
    assert docs[0].page_content == "Text of https://e.test/a." and docs[0].metadata["status"] == 200
    assert client.calls[0][1] == urls
    docs, _ = load(url=urls, include_empty=True)
    assert [d.metadata["url"] for d in docs] == urls
    blocked, robots = docs[1], docs[2]
    assert blocked.page_content == ""
    assert blocked.metadata["status"] == 403 and blocked.metadata["error_code"] == "BLOCKED"
    assert blocked.metadata["verdict"] == "blocked" and blocked.metadata["page_status"] == "blocked"
    assert robots.metadata["page_status"] == "robots" and "status" not in robots.metadata


def test_params_reach_the_sdk_call():
    _, client = load(url="https://d.test/", mode="crawl", params={"limit": 2, "includePaths": ["/a*"]})
    assert client.calls[0] == ("crawl", "https://d.test/", {"limit": 2, "includePaths": ["/a*"]})


def test_crawl_yields_pages_with_the_crawl_id():
    docs, _ = load(url="https://d.test/", mode="crawl")
    assert [d.metadata["url"] for d in docs] == ["https://d.test/", "https://d.test/a"]
    assert all(d.metadata["crawl_id"] == "crawl_1" and d.metadata["mode"] == "crawl" for d in docs)
    meta = docs[1].metadata
    assert docs[1].page_content == "Page a." and meta["title"] == "Title of https://d.test/a"
    # A crawl's rows give the one-word status only; the HTTP code is not in them.
    assert meta["page_status"] == "ok" and "status" not in meta and "verdict" not in meta
    assert meta["crawled_at"] == "2026-10-15T10:00:00Z" and meta["words"] == 2


def test_crawl_keeps_an_empty_page_when_asked():
    docs, _ = load(url="https://d.test/", mode="crawl", include_empty=True)
    assert docs[2].metadata["url"] == "https://d.test/gone" and docs[2].metadata["page_status"] == "missing"


def test_map_lists_urls_without_fetching():
    docs, client = load(url="https://m.test/", mode="map", params={"search": "a"})
    assert [d.page_content for d in docs] == ["https://m.test/a", "https://m.test/b"]
    assert docs[0].metadata == {"source": "https://m.test/a", "url": "https://m.test/a", "lastmod": "2026-10-01",
                                "section": "/a", "sitemap": "https://m.test/sitemap.xml", "mode": "map"}
    assert "lastmod" not in docs[1].metadata  # None is dropped, never stored
    assert client.calls == [("map", "https://m.test/", {"search": "a"})]


def test_changes_reads_each_changed_page_as_it_is_now():
    docs, client = load(mode="changes", project_id="prj_1")
    assert [(d.metadata["change"], d.metadata["url"]) for d in docs] == [
        ("added", "https://s.test/new"), ("modified", "https://s.test/price")]
    doc = docs[1]
    assert doc.page_content == "Now: https://s.test/price"
    assert doc.id == "run_2:https://s.test/price"
    assert doc.metadata["run_id"] == "run_2" and doc.metadata["previous_run_id"] == "run_1"
    assert doc.metadata["changed_at"] == "2026-10-15T09:00:00Z"
    assert doc.metadata["words_before"] == 80 and doc.metadata["words_after"] == 95
    assert doc.metadata["project_id"] == "prj_1" and doc.metadata["title"] == "Current"
    # A stored page gives its HTTP code as `status` and the word as `pageStatus`.
    assert doc.metadata["status"] == 200 and doc.metadata["page_status"] == "ok"
    assert doc.metadata["crawled_at"] == "2026-10-15T08:59:00Z"
    assert ("page", "prj_1", "https://s.test/price", "run_2") in client.calls
    assert not any(c[0] == "page" and c[2] == "https://s.test/old" for c in client.calls)


def test_changes_can_include_removed_pages():
    docs, _ = load(mode="changes", project_id="prj_1", run_id="run_2", against="run_0", include_removed=True)
    removed = [d for d in docs if d.metadata["change"] == "removed"]
    assert len(removed) == 1 and removed[0].page_content == ""
    assert removed[0].metadata["url"] == "https://s.test/old" and removed[0].metadata["title"] == "Old"


def test_changes_skips_a_page_whose_copy_is_gone_but_not_other_errors():
    from mesharc import MeshArcError

    class Pruned(FakeMeshArc):
        def page(self, project_id, url, run_id=None):
            if url.endswith("/new"):
                raise MeshArcError(404, "Not Found", "not_found")
            return super().page(project_id, url, run_id)

    docs = MeshArcLoader(mode="changes", project_id="prj_1", client=Pruned()).load()
    assert [d.metadata["url"] for d in docs] == ["https://s.test/price"]
    docs = MeshArcLoader(mode="changes", project_id="prj_1", client=Pruned(), include_empty=True).load()
    assert docs[0].metadata["url"] == "https://s.test/new" and docs[0].page_content == ""

    class Down(FakeMeshArc):
        def page(self, project_id, url, run_id=None):
            raise MeshArcError(503, "Service Unavailable", "unavailable")

    with pytest.raises(MeshArcError):
        MeshArcLoader(mode="changes", project_id="prj_1", client=Down()).load()


def test_changes_passes_run_and_against():
    _, client = load(mode="changes", project_id="prj_1", run_id="run_2", against="run_0")
    assert client.calls[0] == ("changes", "prj_1", "run_2", "run_0")


def test_no_change_record_loads_nothing():
    client = FakeMeshArc()
    client.changes = lambda *a, **k: {"runs": [], "change": None}
    assert MeshArcLoader(mode="changes", project_id="prj_1", client=client).load() == []


def test_lazy_load_is_lazy():
    client = FakeMeshArc()
    loader = MeshArcLoader("https://d.test/", mode="crawl", client=client)
    assert client.calls == []
    next(loader.lazy_load())
    assert client.calls[0][0] == "crawl"


async def test_async_load():
    docs = await MeshArcLoader("https://e.test/", client=FakeMeshArc()).aload()
    assert docs[0].metadata["url"] == "https://e.test/"


@pytest.mark.parametrize("kwargs, message", [
    ({"url": "https://e.test/", "mode": "nope"}, "mode must be one of"),
    ({"mode": "scrape"}, "needs url"),
    ({"mode": "changes"}, "needs project_id"),
    ({"url": ["https://a.test/", "https://b.test/"], "mode": "crawl"}, "takes one url"),
    ({"url": ["https://a.test/"], "mode": "map"}, "takes one url"),
])
def test_bad_arguments_are_refused_before_any_request(kwargs, message):
    client = FakeMeshArc()
    with pytest.raises(ValueError, match=message):
        MeshArcLoader(client=client, **kwargs)
    assert client.calls == []


def test_api_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("MESHARC_API_KEY", "mesharc_test")
    loader = MeshArcLoader("https://e.test/")
    assert type(loader._client).__name__ == "MeshArc"


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("MESHARC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API key"):
        MeshArcLoader("https://e.test/")
