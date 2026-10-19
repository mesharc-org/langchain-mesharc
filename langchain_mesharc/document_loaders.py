"""MeshArcLoader: pages from MeshArc as LangChain Documents."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Literal, Optional, Sequence, Union

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from . import _core


class MeshArcLoader(BaseLoader):
    """Load web pages through MeshArc as Documents of clean markdown.

    Modes:
        * ``scrape``: one URL, or a list of URLs read as one batch.
        * ``crawl``: a one-shot crawl of a site, pages yielded as they land.
        * ``map``: the URLs the site declares in its sitemaps, one Document
          per URL whose text is the URL itself. Nothing is fetched.
        * ``changes``: what changed in a MeshArc project's latest run (or
          ``run_id``) against the run before it (or ``against``). Each
          added or modified page is a Document of the page as it is now.

    Metadata: ``source``/``url``, ``title``, ``page_status`` (one word:
    ok, missing, blocked, captcha, ...), ``crawled_at`` and ``mode``;
    scraped and changed pages add ``status`` (the HTTP status), scraped
    pages ``verdict`` and ``credits``, crawls ``crawl_id``, and changes
    ``project_id``, ``run_id``, ``previous_run_id``, ``changed_at``,
    ``change`` (added, modified, removed or fields) and
    ``words_before``/``words_after``.

    Pages that came back without content (blocked, a 404) are skipped
    unless ``include_empty`` is set; their ``page_status`` and
    ``error_code`` then say why. ``params`` are passed to the MeshArc SDK call as they are,
    for example ``{"limit": 50, "includePaths": ["/blog/*"]}`` for a crawl
    or ``{"search": "pricing"}`` for a map.

    Example:
        .. code-block:: python

            from langchain_mesharc import MeshArcLoader

            docs = MeshArcLoader("https://example.com/pricing").load()
            docs = MeshArcLoader("https://docs.example.com", mode="crawl",
                                 params={"limit": 50}).load()
            changed = MeshArcLoader(mode="changes", project_id="<project id>").load()
    """

    def __init__(
        self,
        url: Union[str, Sequence[str], None] = None,
        *,
        mode: Literal["scrape", "crawl", "map", "changes"] = "scrape",
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        against: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        include_empty: bool = False,
        include_removed: bool = False,
        api_key: Optional[str] = None,
        client: Any = None,
    ) -> None:
        """
        Args:
            url: The URL (or, for ``scrape``, a list of URLs). Not used by ``changes``.
            mode: ``scrape``, ``crawl``, ``map`` or ``changes``.
            project_id: The MeshArc project, for ``changes``.
            run_id: For ``changes``: the run to report on; the latest finished one by default.
            against: For ``changes``: compare with this run instead of the one before.
            params: Extra arguments for the MeshArc SDK call.
            include_empty: Also yield pages that came back without content.
            include_removed: For ``changes``: also yield removed pages, with no text.
            api_key: A MeshArc API key; ``MESHARC_API_KEY`` is used when omitted.
            client: A ``mesharc.MeshArc`` client to use instead of making one.
        """
        _core.check(mode, url, project_id)
        self.url = url
        self.mode = mode
        self.project_id = project_id
        self.run_id = run_id
        self.against = against
        self.params = dict(params or {})
        self.include_empty = include_empty
        self.include_removed = include_removed
        self._client = _core.make_client(api_key, client)

    def lazy_load(self) -> Iterator[Document]:
        for record in _core.load(
            self._client,
            self.mode,
            url=self.url,
            project_id=self.project_id,
            run_id=self.run_id,
            against=self.against,
            params=self.params,
            include_empty=self.include_empty,
            include_removed=self.include_removed,
        ):
            yield Document(page_content=record["text"], metadata=record["metadata"], id=record["id"])
