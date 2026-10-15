import pytest
from langchain_core.messages import ToolMessage
from langchain_tests.integration_tests import ToolsIntegrationTests
from langchain_tests.unit_tests import ToolsUnitTests

from langchain_mesharc import MeshArcScrape, MeshArcSearch
from tests.fake import FakeMeshArc


class TestMeshArcSearchStandard(ToolsUnitTests):
    @property
    def tool_constructor(self):
        return MeshArcSearch

    @property
    def tool_constructor_params(self):
        return {"api_key": "mesharc_test"}

    @property
    def tool_invoke_params_example(self):
        return {"query": "web scraping api", "limit": 3}

    @property
    def init_from_env_params(self):
        return {"MESHARC_API_KEY": "mesharc_env"}, {}, {}


class TestMeshArcScrapeStandard(ToolsUnitTests):
    @property
    def tool_constructor(self):
        return MeshArcScrape

    @property
    def tool_constructor_params(self):
        return {"api_key": "mesharc_test"}

    @property
    def tool_invoke_params_example(self):
        return {"urls": ["https://example.com/"]}

    @property
    def init_from_env_params(self):
        return {"MESHARC_API_KEY": "mesharc_env"}, {}, {}


class TestMeshArcSearchInvoke(ToolsIntegrationTests):
    """LangChain's invoke checks, run offline against the stand-in client."""

    @property
    def tool_constructor(self):
        return MeshArcSearch

    @property
    def tool_constructor_params(self):
        return {"client": FakeMeshArc()}

    @property
    def tool_invoke_params_example(self):
        return {"query": "web scraping api", "limit": 3}


class TestMeshArcScrapeInvoke(ToolsIntegrationTests):
    @property
    def tool_constructor(self):
        return MeshArcScrape

    @property
    def tool_constructor_params(self):
        return {"client": FakeMeshArc()}

    @property
    def tool_invoke_params_example(self):
        return {"urls": ["https://example.com/", "https://example.com/about"]}


def call(tool, args):
    """Invoke as an agent does, with a ToolCall, and return the ToolMessage."""
    return tool.invoke({"name": tool.name, "args": args, "id": "call_1", "type": "tool_call"})


def test_search_lists_results_and_keeps_the_full_response():
    client = FakeMeshArc()
    msg = call(MeshArcSearch(client=client), {"query": "q", "limit": 2})
    assert isinstance(msg, ToolMessage)
    assert msg.content.splitlines()[:3] == ["1. Result 1", "   https://r1.test/", "   About 1"]
    assert "2. Result 2" in msg.content
    assert msg.artifact["id"] == "s1" and len(msg.artifact["data"]) == 2
    assert client.calls == [("web_search", "q", 2, None)]


def test_search_can_read_each_page_and_cuts_long_text():
    client = FakeMeshArc()
    msg = call(MeshArcSearch(client=client, max_chars_per_page=100), {"query": "q", "limit": 1, "read_pages": True})
    assert client.calls[0][3] is True
    assert "Full text" in msg.content and "[... cut at 100 characters]" in msg.content
    assert len(msg.artifact["data"][0]["page"]["markdown"]) > 100  # the artifact keeps it whole


def test_search_refused_by_every_engine_is_said_plainly():
    msg = call(MeshArcSearch(client=FakeMeshArc()), {"query": "refused"})
    assert "refused this search" in msg.content


def test_scrape_one_and_many():
    client = FakeMeshArc()
    msg = call(MeshArcScrape(client=client), {"urls": ["https://e.test/p"]})
    assert msg.content.startswith("# Title of https://e.test/p\nURL: https://e.test/p\n\n# Page")
    assert client.calls[0][1] == "https://e.test/p"  # one URL is a single scrape, not a batch
    urls = ["https://e.test/a", "https://e.test/blocked", "https://e.test/robots"]
    msg = call(MeshArcScrape(client=client), {"urls": urls})
    assert client.calls[1][1] == urls  # many URLs are one batch
    assert "# Title of https://e.test/a\nURL: https://e.test/a\n\nText of https://e.test/a." in msg.content
    assert "URL: https://e.test/blocked\nNot read: refused by the site." in msg.content
    assert "URL: https://e.test/robots\nNot read: disallowed by robots.txt." in msg.content
    assert [r["url"] for r in msg.artifact] == urls


def test_scrape_limits_the_url_count():
    tool = MeshArcScrape(client=FakeMeshArc())
    with pytest.raises(Exception):
        tool.invoke({"urls": []})
    with pytest.raises(Exception):
        tool.invoke({"urls": [f"https://e.test/{i}" for i in range(21)]})


def test_a_refused_request_reaches_the_agent_as_a_message():
    class Refusing(FakeMeshArc):
        def scrape(self, urls, **params):
            from mesharc import MeshArcError
            raise MeshArcError(402, "Not enough credits.", "insufficient_credits")

    msg = call(MeshArcScrape(client=Refusing()), {"urls": ["https://e.test/"]})
    assert msg.status == "error"
    assert "MeshArc refused the request (insufficient_credits)" in msg.content


def test_the_api_key_is_never_shown():
    tool = MeshArcSearch(api_key="mesharc_secret_value")
    assert "mesharc_secret_value" not in repr(tool)
    assert "mesharc_secret_value" not in str(tool.model_dump())
