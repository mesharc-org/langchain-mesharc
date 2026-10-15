"""MeshArc results as plain document records, independent of any framework.

langchain-mesharc and llama-index-readers-mesharc carry this same file; each
wraps the records in its own Document class. Keep the two copies identical.

A record is ``{"id": str, "text": str, "metadata": dict}``. Metadata values
are str, int or bool only, never None, so every vector store accepts them.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, Optional, Union

MODES = ("scrape", "crawl", "map", "changes")
CHANGE_KINDS = ("added", "modified", "removed", "fields")

Record = Dict[str, Any]


def make_client(api_key: Optional[str] = None, client: Any = None) -> Any:
    """The client to call: the one given, or a MeshArc client for ``api_key``
    (falling back to the ``MESHARC_API_KEY`` environment variable)."""
    if client is not None:
        return client
    from mesharc import MeshArc

    return MeshArc(api_key)


def _clean(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Drop empty values; keep str, int and bool as they are, anything else as str."""
    out: Dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None or value == "":
            continue
        out[key] = value if isinstance(value, (str, int, bool)) else str(value)
    return out


def page_metadata(row: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """What a page row says about itself, under the names every mode shares.

    The API returns pages in two shapes. A scrape's rows carry the HTTP code
    as ``httpStatus``, the engine's ``verdict`` and the one-word page status
    as ``status``. A stored page (a crawl's rows, a project's page) carries
    the HTTP code as ``status`` and the word as ``pageStatus`` -- and a
    crawl's rows then overwrite ``status`` with the word. Both read alike here.
    """
    head = row.get("head") or {}
    url = row.get("url") or ""
    raw_status = row.get("status")
    http = row.get("httpStatus")
    if http is None and isinstance(raw_status, int) and not isinstance(raw_status, bool):
        http = raw_status
    word = row.get("pageStatus") or (raw_status if isinstance(raw_status, str) else "")
    return {
        "source": url,
        "url": url,
        "title": row.get("title") or head.get("title") or "",
        "status": int(http or 0) or None,
        "page_status": word,
        "verdict": row.get("verdict") or "",
        "error_code": row.get("errorCode") or "",
        "words": int(row.get("words") or 0) or None,
        "language": row.get("language") or "",
        "crawled_at": row.get("crawledAt") or "",
        "credits": row.get("credits"),
        "mode": mode,
    }


def page_record(row: Dict[str, Any], mode: str, **extra: Any) -> Record:
    metadata = page_metadata(row, mode)
    metadata.update(extra)
    url = row.get("url") or ""
    return {"id": url, "text": row.get("markdown") or "", "metadata": _clean(metadata)}


def batch_rows(batch: Optional[Dict[str, Any]]) -> list:
    """The rows of a finished batch: one per URL, under ``pages`` (a batch
    is not an envelope, so it has no ``data``)."""
    return list((batch or {}).get("pages") or [])


def scrape(client: Any, urls: Union[str, Iterable[str]], params: Dict[str, Any],
           include_empty: bool = False) -> Iterator[Record]:
    """One URL, or many as one batch. Each page row becomes a record."""
    if isinstance(urls, str):
        rows = [client.scrape(urls, **params)]
    else:
        rows = batch_rows(client.scrape(list(urls), **params))
    for row in rows:
        record = page_record(row, "scrape")
        if record["text"] or include_empty:
            yield record


def crawl(client: Any, url: str, params: Dict[str, Any], include_empty: bool = False) -> Iterator[Record]:
    """A one-shot crawl of a site. Pages are yielded as they land."""
    job = client.crawl(url, **params)
    for row in job.pages():
        record = page_record(row, "crawl", crawl_id=job.id)
        if record["text"] or include_empty:
            yield record


def site_map(client: Any, url: str, params: Dict[str, Any]) -> Iterator[Record]:
    """The URLs a site declares in its sitemaps. The text is the URL; nothing is fetched."""
    for row in client.map(url, **params):
        page_url = row.get("url") or ""
        metadata = {
            "source": page_url,
            "url": page_url,
            "lastmod": row.get("lastmod") or "",
            "changefreq": row.get("changefreq") or "",
            "section": row.get("section") or "",
            "sitemap": row.get("file") or "",
            "mode": "map",
        }
        yield {"id": page_url, "text": page_url, "metadata": _clean(metadata)}


def changes(client: Any, project_id: str, run_id: Optional[str] = None, against: Optional[str] = None,
            include_removed: bool = False, include_empty: bool = False) -> Iterator[Record]:
    """What changed in a project's run against the run before it (or against
    ``against``). Each added, modified or fields-only page becomes a record
    holding the page as it is now; a removed page has no text and is
    yielded only with ``include_removed``."""
    change = (client.changes(project_id, run_id=run_id, against=against) or {}).get("change")
    if not change:
        return
    run = change.get("runId") or run_id or ""
    shared = {
        "project_id": project_id,
        "run_id": run,
        "previous_run_id": change.get("prevRunId") or "",
        "changed_at": change.get("createdAt") or "",
    }
    for entry in change.get("feed") or []:
        kind = entry.get("kind") or ""
        url = entry.get("url") or ""
        about = dict(shared, change=kind, words_before=int(entry.get("wordsBefore") or 0),
                     words_after=int(entry.get("wordsAfter") or 0))
        if kind == "removed":
            if include_removed:
                metadata = dict(about, source=url, url=url, title=entry.get("section") or "", mode="changes")
                yield {"id": f"{run}:{url}", "text": "", "metadata": _clean(metadata)}
            continue
        try:
            page = client.page(project_id, url, run_id=run or None)
        except Exception as exc:
            # The stored copy is gone (pruned by the project's retention, or
            # the run deleted): skip the page rather than end the whole load.
            if getattr(exc, "status", None) != 404:
                raise
            if include_empty:
                metadata = dict(about, source=url, url=url, title=entry.get("section") or "", mode="changes")
                yield {"id": f"{run}:{url}", "text": "", "metadata": _clean(metadata)}
            continue
        record = page_record(dict(page, url=page.get("url") or url), "changes", **about)
        record["id"] = f"{run}:{url}"
        if record["text"] or include_empty:
            yield record


def load(client: Any, mode: str, url: Union[str, Iterable[str], None] = None, project_id: Optional[str] = None,
         run_id: Optional[str] = None, against: Optional[str] = None, params: Optional[Dict[str, Any]] = None,
         include_empty: bool = False, include_removed: bool = False) -> Iterator[Record]:
    """Records for one of the four modes."""
    check(mode, url, project_id)
    extra = dict(params or {})
    if mode == "scrape":
        return scrape(client, url, extra, include_empty)  # type: ignore[arg-type]
    if mode == "crawl":
        return crawl(client, url, extra, include_empty)  # type: ignore[arg-type]
    if mode == "map":
        return site_map(client, url, extra)  # type: ignore[arg-type]
    return changes(client, project_id, run_id, against, include_removed, include_empty)  # type: ignore[arg-type]


def check(mode: str, url: Union[str, Iterable[str], None], project_id: Optional[str]) -> None:
    """Refuse a combination that cannot work, before any request is made."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}, not {mode!r}")
    if mode == "changes":
        if not project_id:
            raise ValueError("mode 'changes' needs project_id: the MeshArc project whose changes to load")
        return
    if not url:
        raise ValueError(f"mode {mode!r} needs url")
    if mode in ("crawl", "map") and not isinstance(url, str):
        raise ValueError(f"mode {mode!r} takes one url, a string")
