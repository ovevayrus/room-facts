import json
import socket

import pytest

import add_guest
import build_graph


@pytest.fixture
def data(monkeypatch, tmp_path):
    (tmp_path / "luma_guests.json").write_text(json.dumps([{"api_id": "g1", "first_name": "Ada", "last_name": "One", "linkedin_handle": "/in/ada-one"}]))
    monkeypatch.setattr(add_guest, "DATA", tmp_path)
    monkeypatch.setattr(add_guest, "EXTRA", tmp_path / "extra_guests.json")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "test-key")
    calls = []

    def fake_scrape(records):
        def scrape(inputs, params, headers):
            calls.append((inputs, params))
            return records
        monkeypatch.setattr(add_guest, "scrape", scrape)
    return tmp_path, calls, fake_scrape


def test_existing_guest_is_skipped_without_scraping(data):
    path, calls, fake_scrape = data
    fake_scrape([])
    assert add_guest.main(["Ada One", "--linkedin", "https://www.linkedin.com/in/someone-else"]) == 0
    assert add_guest.main(["Somebody New", "--linkedin", "linkedin.com/in/ada-one/"]) == 0
    assert calls == [] and not (path / "extra_guests.json").exists()


def test_new_guest_scrapes_only_their_profile(data):
    path, calls, fake_scrape = data
    (path / "linkedin_raw.json").write_text(json.dumps([{"linkedin_id": "ada-one", "name": "Ada One"}]))
    fake_scrape([{"input": {"url": "https://www.linkedin.com/in/new-person"}, "linkedin_id": "new-person", "name": "New Person"}])
    assert add_guest.main(["New Person", "--linkedin", "https://www.linkedin.com/in/New-Person/"]) == 0
    assert calls == [([{"url": "https://www.linkedin.com/in/new-person"}], {})]
    extra = json.loads((path / "extra_guests.json").read_text())
    assert extra == [{"api_id": "extra-new-person", "first_name": "New", "last_name": "Person", "linkedin_handle": "/in/new-person",
                      "twitter_handle": "", "avatar_url": "", "source": "manual"}]
    assert [r["linkedin_id"] for r in json.loads((path / "linkedin_raw.json").read_text())] == ["ada-one", "new-person"]
    assert add_guest.main(["New Person", "--linkedin", "/in/new-person"]) == 0
    assert len(json.loads((path / "extra_guests.json").read_text())) == 1


def test_discovery_keeps_the_one_profile_at_the_company(data):
    path, calls, fake_scrape = data
    fake_scrape([{"linkedin_id": "liz-a", "name": "Liz Zhang", "current_company": {"name": "Other Corp"}},
                 {"linkedin_id": "liz-b", "name": "Liz Zhang", "current_company": {"name": "FalkorDB"}}])
    assert add_guest.main(["Liz Zhang", "--company", "falkordb"]) == 0
    assert calls[0][0] == [{"first_name": "Liz", "last_name": "Zhang"}] and calls[0][1]["discover_by"] == "name"
    assert json.loads((path / "extra_guests.json").read_text())[0]["linkedin_handle"] == "/in/liz-b"


def test_ambiguous_discovery_adds_nobody(data):
    path, calls, fake_scrape = data
    fake_scrape([{"linkedin_id": f"liz-{i}", "current_company": {"name": "FalkorDB"}} for i in range(2)])
    with pytest.raises(SystemExit):
        add_guest.main(["Liz Zhang", "--company", "falkordb"])
    assert not (path / "extra_guests.json").exists() and not (path / "linkedin_raw.json").exists()


def test_rebuild_merges_extra_guests(tmp_path):
    try:
        socket.create_connection(("localhost", 6379), timeout=0.5).close()
    except OSError:
        pytest.skip("FalkorDB at localhost:6379 is unreachable")
    luma = tmp_path / "luma.json"
    luma.write_text(json.dumps([{"api_id": "g1", "first_name": "Ada", "last_name": "One"}]))
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps([{"api_id": "extra-new", "first_name": "New", "last_name": "Person"},
                                 {"api_id": "g1", "first_name": "Dup", "last_name": "Row"}]))
    build_graph.rebuild(luma, tmp_path / "missing.json", "roomfacts_extra_test", *[tmp_path / "missing.json"] * 6, extra_path=extra)
    graph = build_graph.graph_client("roomfacts_extra_test")
    try:
        assert sorted(r[0] for r in graph.ro_query("MATCH (p:Person) RETURN p.id").result_set) == ["extra-new", "g1"]
    finally:
        graph.delete()
