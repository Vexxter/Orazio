"""News panel: the right headlines for the symbol on the chart, nothing else."""
import pytest

from orazio import news

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Reliance Industries stock slips - Mint</title><link>https://example.com/a</link>
 <pubDate>Wed, 30 Sep 2026 06:30:00 GMT</pubDate><source url="https://mint.example">Mint</source></item>
<item><title>Apple orchards report record harvest - Farm Weekly</title><link>https://example.com/b</link>
 <pubDate>Wed, 30 Sep 2026 07:00:00 GMT</pubDate><source url="https://f.example">Farm Weekly</source></item>
<item><title>Broken date item - X</title><link>https://example.com/c</link><pubDate>garbage</pubDate></item>
<item><title>Reliance Industries stock slips - Mint</title><link>https://example.com/dup</link>
 <pubDate>Wed, 30 Sep 2026 06:31:00 GMT</pubDate><source url="https://mint.example">Mint</source></item>
<item><link>https://example.com/no-title</link><pubDate>Wed, 30 Sep 2026 06:00:00 GMT</pubDate></item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, content=b"", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise news.requests.RequestException("boom")


# ---- parsing ----------------------------------------------------------------
def test_parse_strips_the_publisher_suffix_and_keeps_publisher_separately():
    items = news._parse(RSS)
    first = items[0]
    assert first["title"] == "Reliance Industries stock slips"
    assert first["publisher"] == "Mint" and first["url"] == "https://example.com/a"
    assert isinstance(first["time"], int)


def test_parse_skips_items_with_unparseable_dates_or_no_title():
    titles = [i["title"] for i in news._parse(RSS)]
    assert "Broken date item" not in titles and all(titles)


# ---- relevance --------------------------------------------------------------
def test_mentions_matches_whole_words_only():
    assert news._mentions("Why Ether rallied today", ["ether"])
    assert not news._mentions("Staying together in a crisis", ["ether"])      # "together" must not match
    assert news._mentions("Sensex, Nifty open flat", ["nifty"])
    assert not news._mentions("Unrelated headline", ["nifty"])


def test_index_keywords_are_used_for_rail_indices():
    assert news.keywords_for("^NSEI") == ["nifty"]
    assert "gift nifty" in news.keywords_for("GIFTNIFTY")
    assert "bitcoin" in news.keywords_for("BTC-USD")


def test_stock_keywords_come_from_the_company_name_and_ticker(monkeypatch):
    monkeypatch.setattr(news, "_company_name", lambda s: "Tata Consultancy Services Limited")
    kws = news.keywords_for("TCS.NS")
    assert "tata consultancy services" in kws and "tata" in kws and "tcs" in kws
    assert "services" not in kws and "limited" not in kws          # generic words would match everything


def test_query_for_quotes_company_names_and_adds_stock(monkeypatch):
    monkeypatch.setattr(news, "_company_name", lambda s: "Apple Inc.")
    assert news.query_for("AAPL") == '"Apple" stock'                  # "stock" keeps Apple the company apart from apples
    assert news.query_for("^NSEI") == "Nifty 50"
    monkeypatch.setattr(news, "_company_name", lambda s: None)
    assert news.query_for("XYZ.NS") == "XYZ"


def test_edition_picks_the_indian_feed_for_indian_symbols():
    assert news._edition("RELIANCE.NS") == ("en-IN", "IN")
    assert news._edition("^NSEI") == ("en-IN", "IN")
    assert news._edition("GIFTNIFTY") == ("en-IN", "IN")
    assert news._edition("AAPL") == ("en-US", "US")


# ---- headlines (whole pipeline, network faked) --------------------------------
def test_headlines_filters_irrelevant_items_dedupes_and_sorts_newest_first(monkeypatch):
    monkeypatch.setattr(news, "_company_name", lambda s: "Reliance Industries Limited")
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: FakeResponse(RSS))
    out = news.headlines("RELIANCE.NS")
    assert [i["title"] for i in out] == ["Reliance Industries stock slips"]      # apples gone, duplicate collapsed


def test_headlines_is_none_when_the_source_is_down_so_the_ui_can_say_so(monkeypatch):
    monkeypatch.setattr(news, "_company_name", lambda s: "X")
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: FakeResponse(status=503))
    assert news.headlines("RELIANCE.NS") is None


def test_headlines_is_none_for_a_malformed_feed(monkeypatch):
    monkeypatch.setattr(news, "_company_name", lambda s: "X")
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: FakeResponse(b"<not xml"))
    assert news.headlines("RELIANCE.NS") is None


def test_headlines_are_cached_so_polling_does_not_hammer_google(monkeypatch):
    monkeypatch.setattr(news, "_company_name", lambda s: "Reliance Industries Limited")
    calls = []
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: calls.append(1) or FakeResponse(RSS))
    news.headlines("RELIANCE.NS")
    news.headlines("RELIANCE.NS")
    assert len(calls) == 1
