# langchain-mesharc

The LangChain integration for [MeshArc](https://mesharc.dev), the web crawler that turns sites into clean markdown and records what changed between crawls.

- **`MeshArcLoader`** loads web pages as LangChain `Document`s, in four modes: scrape, crawl, map and changes.
- **`MeshArcSearch`** and **`MeshArcScrape`** are tools an agent can call to search the web and read pages.

The full guide, with every option, the metadata on each Document and how to keep a vector store current, is at **[mesharc.dev/docs/langchain](https://mesharc.dev/docs/langchain)**.

```bash
pip install langchain-mesharc
```

You need a MeshArc API key. Make one under **Settings → API keys** at [mesharc.dev](https://mesharc.dev); the free plan includes 1,000 credits with no card. Set it as `MESHARC_API_KEY`, or pass `api_key=`. Reading pages and searching need a key with **write** access.

## Document loader

```python
from langchain_mesharc import MeshArcLoader

# One page, or many read as one batch
docs = MeshArcLoader("https://example.com/pricing").load()
docs = MeshArcLoader(["https://example.com/", "https://example.com/about"]).load()

# A whole site, or a section of it; pages arrive as they are read
loader = MeshArcLoader("https://docs.example.com", mode="crawl",
                       params={"limit": 100, "includePaths": ["/guides/*"]})
for doc in loader.lazy_load():
    print(doc.metadata["url"], len(doc.page_content))

# The URLs a site declares in its sitemaps, without fetching them
urls = MeshArcLoader("https://docs.example.com", mode="map").load()

# What changed on a watched site since the last crawl
changed = MeshArcLoader(mode="changes", project_id="<project id>").load()
```

| Mode | Input | Each Document |
|---|---|---|
| `scrape` | a URL or a list of URLs | the page's markdown |
| `crawl` | a site's URL; `params` takes `limit`, `maxDepth`, `includePaths`, `excludePaths` and the rest of the [crawl options](https://mesharc.dev/docs/api) | one per page read |
| `map` | a site's URL; `params` takes `search` and `limit` | one per URL in the sitemaps, with the URL as its text |
| `changes` | `project_id`, and optionally `run_id` and `against` | one per added or modified page, holding the page as it is now |

**Metadata** on every page: `source` and `url`, `title`, `page_status` (one word: `ok`, `missing`, `blocked`, `captcha`, …), `crawled_at` and `mode`.
- Scraped and changed pages also have `status`, the HTTP status. A crawl's pages don't, because the API leaves it out of crawl results.
- Scraped pages also have `verdict` and `credits`.
- A crawl adds `crawl_id`.
- Changes add `project_id`, `run_id`, `previous_run_id`, `changed_at`, `change` (`added`, `modified`, `removed` or `fields`), `words_before` and `words_after`.

Values are always strings, numbers or booleans, so any vector store accepts them.

Pages that came back with no content (blocked, or a 404) are left out. Pass `include_empty=True` to keep them; their `page_status` and `error_code` say why. In `changes` mode, removed pages are left out unless `include_removed=True`.

`changes` mode keeps a vector store current: load it after each run of a [MeshArc project](https://mesharc.dev/docs), and re-embed only the pages that changed. Each Document's `id` is `run_id:url`.

## Tools

```python
from langchain_mesharc import MeshArcScrape, MeshArcSearch

tools = [MeshArcSearch(), MeshArcScrape()]
```

| Tool | The agent gives | It gets back |
|---|---|---|
| `mesharc_search` (`MeshArcSearch`) | `query`, `limit` (1–10), `read_pages` | a numbered list of results (title, URL, snippet), and with `read_pages` each result's page text |
| `mesharc_scrape` (`MeshArcScrape`) | `urls` (1–20) | each page's title, URL and markdown, or why a page could not be read |

Both tools return `content_and_artifact`:
- the **content** is the text sent to the model, with each page cut at `max_chars_per_page` (8,000 by default; 0 for no limit);
- the **artifact** is MeshArc's full response.

A refused request, such as one with too few credits left, comes back to the agent as an error message rather than stopping it.

## Cost

Requests are billed in MeshArc credits, the same as any other API call:
- a plain page read costs 1 credit, and blocked pages and 404s cost nothing;
- a web search costs what reading its results page costs;
- a sitemap read costs 1 credit per sitemap file.

See [pricing](https://mesharc.dev/pricing).

## Links

- [The LangChain guide](https://mesharc.dev/docs/langchain), [MeshArc docs](https://mesharc.dev/docs) and [API reference](https://mesharc.dev/docs/api)
- [The Python SDK](https://github.com/mesharc-org/mesharc-python), which this package uses
- [Questions](https://github.com/orgs/mesharc-org/discussions) · security reports to security@mesharc.dev

## License

MIT
