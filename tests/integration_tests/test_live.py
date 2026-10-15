"""Against the real API. Skipped unless MESHARC_API_KEY is set; each run spends a few credits.

    MESHARC_API_KEY=mesharc_... python -m pytest tests/integration_tests -q
"""

import os

import pytest
from langchain_tests.integration_tests import ToolsIntegrationTests

from langchain_mesharc import MeshArcLoader, MeshArcScrape, MeshArcSearch

pytestmark = pytest.mark.skipif(not os.environ.get("MESHARC_API_KEY"), reason="MESHARC_API_KEY is not set")


class TestLiveScrape(ToolsIntegrationTests):
    @property
    def tool_constructor(self):
        return MeshArcScrape

    @property
    def tool_invoke_params_example(self):
        return {"urls": ["https://example.com/"]}


class TestLiveSearch(ToolsIntegrationTests):
    @property
    def tool_constructor(self):
        return MeshArcSearch

    @property
    def tool_invoke_params_example(self):
        return {"query": "example domain iana", "limit": 2}


def test_live_scrape_loader():
    docs = MeshArcLoader("https://example.com/").load()
    assert len(docs) == 1
    assert "Example Domain" in docs[0].page_content
    assert docs[0].metadata["status"] == 200


def test_live_map_loader():
    docs = MeshArcLoader("https://mesharc.dev/", mode="map", params={"limit": 5}).load()
    assert docs and all(d.page_content.startswith("https://") for d in docs)
