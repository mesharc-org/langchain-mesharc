"""A stand-in for ``mesharc.MeshArc`` that answers offline with the API's real shapes.

Each shape follows the code that builds it in the MeshArc API:

* ``stored_page``: ``shapes.page_content``, a stored page. The HTTP code is
  ``status``, the one-word status is ``pageStatus``, and there is no
  ``verdict`` or ``httpStatus``. ``GET /projects/{id}/pages/content`` returns it.
* a crawl row: ``verbs.pages_page``, a stored page whose ``status`` is
  overwritten with the one-word status.
* ``scrape_page``: ``scrape.page_of`` and ``batch.row``, a stored page plus
  ``httpStatus``, ``verdict`` and ``credits``, with ``status`` the word.
* a batch: ``batch.row``, whose rows are under ``pages`` (it has no ``data``).
"""

from typing import Any, Dict, List


def stored_page(url: str, markdown: str = "", http: int = 200, word: str = "ok", **fields: Any) -> Dict[str, Any]:
    row = {"url": url, "kind": None, "status": http, "words": len(markdown.split()), "htmlBytes": 0,
           "markdownBytes": len(markdown), "errorCode": "OK" if http == 200 else "BLOCKED", "tier": "fetch",
           "method": "fetch", "signals": [], "markdown": markdown, "language": "en",
           "head": {"title": f"Title of {url}"}, "runId": "run_x", "crawledAt": "2026-10-15T10:00:00Z",
           "pageStatus": word, "reason": "" if http == 200 else f"http {http}"}
    row.update(fields)
    return row


def crawl_row(url: str, markdown: str = "", http: int = 200, word: str = "ok") -> Dict[str, Any]:
    row = stored_page(url, markdown, http, word)
    row["status"] = row["pageStatus"]
    return row


def scrape_page(url: str, markdown: str = "", http: int = 200, word: str = "ok", verdict: str = "ok",
                **fields: Any) -> Dict[str, Any]:
    row = stored_page(url, markdown, http, word, **fields)
    row.update({"httpStatus": http, "status": row["pageStatus"], "verdict": verdict, "credits": 1})
    return row


class FakeCrawl:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.id = "crawl_1"
        self._rows = rows

    def pages(self, **_: Any):
        yield from self._rows


class FakeMeshArc:
    def __init__(self) -> None:
        self.calls: List[tuple] = []

    def scrape(self, urls: Any, **params: Any) -> Dict[str, Any]:
        self.calls.append(("scrape", urls, params))
        if isinstance(urls, str):
            return scrape_page(urls, f"# Page\n\nText of {urls}.")
        rows: List[Dict[str, Any]] = []
        for u in urls:
            if "blocked" in u:
                rows.append(scrape_page(u, "", http=403, word="blocked", verdict="blocked",
                                        reason="refused by the site"))
            elif "robots" in u:
                rows.append({"url": u, "status": "robots", "error": "disallowed by robots.txt", "credits": 0})
            else:
                rows.append(scrape_page(u, f"Text of {u}."))
        return {"id": "batch_1", "status": "done", "urls": len(rows), "done": len(rows), "creditsUsed": len(rows),
                "runs": [], "pages": rows}

    def crawl(self, url: str, **params: Any) -> FakeCrawl:
        self.calls.append(("crawl", url, params))
        return FakeCrawl([crawl_row(url, "Home."), crawl_row(url + "a", "Page a."),
                          crawl_row(url + "gone", "", http=404, word="missing")])

    def map(self, url: str, **params: Any) -> List[Dict[str, Any]]:
        self.calls.append(("map", url, params))
        return [{"url": url + "a", "lastmod": "2026-10-01", "changefreq": "", "source": "sitemap",
                 "file": url + "sitemap.xml", "section": "/a"},
                {"url": url + "b", "lastmod": None, "changefreq": "weekly", "source": "sitemap",
                 "file": url + "sitemap.xml", "section": "/b"}]

    def changes(self, project_id: str, run_id: Any = None, against: Any = None) -> Dict[str, Any]:
        self.calls.append(("changes", project_id, run_id, against))
        feed = [
            {"path": "/new", "url": "https://s.test/new", "kind": "added", "added": "+120", "removed": "− 0",
             "wordsBefore": 0, "wordsAfter": 120, "section": "New", "fields": [], "reviewed": False},
            {"path": "/price", "url": "https://s.test/price", "kind": "modified", "added": "+20", "removed": "− 5",
             "wordsBefore": 80, "wordsAfter": 95, "section": "", "fields": [], "reviewed": False},
            {"path": "/old", "url": "https://s.test/old", "kind": "removed", "added": "+0", "removed": "− 40",
             "wordsBefore": 40, "wordsAfter": 0, "section": "Old", "fields": [], "reviewed": False},
        ]
        return {"runs": [], "change": {"id": "chg_1", "runId": "run_2", "prevRunId": "run_1", "baseline": False,
                                       "createdAt": "2026-10-15T09:00:00Z", "feed": feed, "fields": []}}

    def page(self, project_id: str, url: str, run_id: Any = None) -> Dict[str, Any]:
        self.calls.append(("page", project_id, url, run_id))
        return stored_page(url, f"Now: {url}", head={"title": "Current"}, runId=run_id,
                           crawledAt="2026-10-15T08:59:00Z", versions=[])

    def web_search(self, query: str, limit: Any = None, scrape: Any = None, **_: Any) -> Dict[str, Any]:
        self.calls.append(("web_search", query, limit, scrape))
        if query == "refused":
            return {"id": "s1", "kind": "search", "status": "blocked", "data": [], "attempts": []}
        hits = [{"position": i, "url": f"https://r{i}.test/", "title": f"Result {i}", "snippet": f"About {i}",
                 "source": "web", "engine": "google"} for i in range(1, (limit or 5) + 1)]
        if scrape:
            for hit in hits:
                hit["page"] = scrape_page(hit["url"], "Full text " * 3000)
        return {"id": "s1", "kind": "search", "status": "done", "data": hits}
