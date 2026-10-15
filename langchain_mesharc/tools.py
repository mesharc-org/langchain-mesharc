"""MeshArc tools for LangChain agents: search the web, and read pages."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Type

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, Field, PrivateAttr, SecretStr, model_validator

from . import _core

DEFAULT_MAX_CHARS = 8000


def _error(exc: Exception) -> ToolException:
    """A refused request, as a message the model can act on."""
    code = getattr(exc, "code", "")
    return ToolException(f"MeshArc refused the request{f' ({code})' if code else ''}: {exc}")


def _clip(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[:limit].rstrip() + f"\n\n[... cut at {limit} characters]"
    return text


class _MeshArcTool(BaseTool):
    """What both tools share: the API key and the client."""

    api_key: Optional[SecretStr] = Field(default=None, exclude=True)
    """A MeshArc API key; ``MESHARC_API_KEY`` is used when omitted."""
    client: Any = Field(default=None, exclude=True)
    """A ``mesharc.MeshArc`` client to use instead of making one."""
    max_chars_per_page: int = DEFAULT_MAX_CHARS
    """How much of each page's markdown goes to the model; 0 for all of it."""
    handle_tool_error: bool = True  # type: ignore[assignment]
    response_format: str = "content_and_artifact"  # type: ignore[assignment]

    _client: Any = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _connect(self) -> "_MeshArcTool":
        key = self.api_key.get_secret_value() if self.api_key else None
        self._client = _core.make_client(key, self.client)
        return self


class MeshArcSearchInput(BaseModel):
    query: str = Field(description="What to search the web for, as you would type it into a search engine.")
    limit: int = Field(default=5, ge=1, le=10, description="How many results to return, 1 to 10.")
    read_pages: bool = Field(
        default=False,
        description="Also read each result's page and return its text. Slower and costs more credits; "
        "use it when the snippets are not enough to answer.",
    )


class MeshArcSearch(_MeshArcTool):
    """Search the web through MeshArc.

    Returns the organic results (title, URL, snippet) of a web search, and
    with ``read_pages`` the text of each result's page. The content sent to
    the model is a numbered list; the artifact is MeshArc's full response.

    Example:
        .. code-block:: python

            from langchain_mesharc import MeshArcSearch

            tool = MeshArcSearch()
            tool.invoke({"query": "rail funding consultation 2026", "limit": 3})
    """

    name: str = "mesharc_search"
    description: str = (
        "Search the web. Returns the top results with title, URL and snippet; set read_pages to also get "
        "the text of each result's page. Use for current events, facts to verify, or finding pages to read."
    )
    args_schema: Type[BaseModel] = MeshArcSearchInput

    def _run(self, query: str, limit: int = 5, read_pages: bool = False,
             run_manager: Optional[CallbackManagerForToolRun] = None) -> Tuple[str, Dict[str, Any]]:
        try:
            out = self._client.web_search(query, limit=limit, scrape=True if read_pages else None)
        except Exception as exc:  # the SDK's MeshArcError, a timeout or a network failure
            raise _error(exc) from exc
        if out.get("status") == "blocked":
            return "The search engines refused this search; nothing was charged. Try again later.", out
        hits = out.get("data") or []
        if not hits:
            return f"No results for {query!r}.", out
        blocks: List[str] = []
        for hit in hits:
            lines = [f"{hit.get('position', len(blocks) + 1)}. {hit.get('title') or hit.get('url')}",
                     f"   {hit.get('url', '')}"]
            if hit.get("snippet"):
                lines.append(f"   {hit['snippet']}")
            page = hit.get("page") or {}
            if read_pages and page.get("markdown"):
                lines.append("")
                lines.append(_clip(page["markdown"], self.max_chars_per_page))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks), out


class MeshArcScrapeInput(BaseModel):
    urls: List[str] = Field(
        min_length=1, max_length=20,
        description="The full URLs (with https://) of the pages to read, 1 to 20.",
    )


class MeshArcScrape(_MeshArcTool):
    """Read web pages through MeshArc as clean markdown.

    Reads each URL (past bot walls when needed) and returns its text. The
    content sent to the model is each page's title, URL and markdown, cut at
    ``max_chars_per_page``; the artifact is the list of MeshArc page rows.

    Example:
        .. code-block:: python

            from langchain_mesharc import MeshArcScrape

            tool = MeshArcScrape()
            tool.invoke({"urls": ["https://example.com/pricing"]})
    """

    name: str = "mesharc_scrape"
    description: str = (
        "Read web pages and return their main text as markdown. Give the full URLs. "
        "Use when you know which pages you need; use mesharc_search first to find them."
    )
    args_schema: Type[BaseModel] = MeshArcScrapeInput

    def _run(self, urls: List[str],
             run_manager: Optional[CallbackManagerForToolRun] = None) -> Tuple[str, List[Dict[str, Any]]]:
        try:
            if len(urls) == 1:
                rows = [self._client.scrape(urls[0])]
            else:
                rows = _core.batch_rows(self._client.scrape(list(urls)))
        except Exception as exc:
            raise _error(exc) from exc
        blocks: List[str] = []
        for row in rows:
            meta = _core.page_metadata(row, "scrape")
            if row.get("markdown"):
                head = f"# {meta['title']}\n" if meta["title"] else ""
                blocks.append(f"{head}URL: {meta['url']}\n\n{_clip(row['markdown'], self.max_chars_per_page)}")
            else:
                why = (row.get("reason") or row.get("error") or meta["error_code"] or meta["page_status"]
                       or meta["verdict"] or "no content")
                blocks.append(f"URL: {meta['url']}\nNot read: {why}.")
        return "\n\n---\n\n".join(blocks) or "Nothing came back.", rows
