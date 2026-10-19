# Changelog

## 0.1.1

Documentation only; no change to the code.

- The package's documentation link on PyPI points at the full guide, [mesharc.dev/docs/langchain](https://mesharc.dev/docs/langchain), and the README links to it.
- The README's `changes` example no longer shows a `prj_` project id; MeshArc project ids have no prefix.

## 0.1.0

The first release.

- `MeshArcLoader` loads web pages through MeshArc as LangChain Documents. It has four modes:
  - `scrape`: one URL, or many as a batch;
  - `crawl`: a site, with pages yielded as they land;
  - `map`: the sitemap's URLs;
  - `changes`: the pages a project's run added or modified.
- `MeshArcSearch` (`mesharc_search`) searches the web, optionally reading each result's page.
- `MeshArcScrape` (`mesharc_scrape`) reads 1 to 20 pages as markdown.
- Both tools return the content for the model and MeshArc's full response as the artifact.
