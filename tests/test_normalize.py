import json
from pathlib import Path

from build_graph import prepare
from normalize import city_id, city_name, country, display_name, entity_slug, language_name, linkedin_slug


FIXTURES = Path(__file__).parent / "fixtures"


def test_aliases_slugs_and_junk():
    assert entity_slug("UC Berkeley", "school") == entity_slug("University of California, Berkeley", "school") == "uc-berkeley"
    assert entity_slug("IIT Bombay", "school") == entity_slug("Indian Institute of Technology, Bombay", "school")
    assert entity_slug("CMU", "school") == entity_slug("Carnegie Mellon University", "school")
    assert entity_slug("The Orbit, Inc.", "company") == "orbit"
    assert entity_slug("Acme LLC", "company") == entity_slug("Acme GmbH", "company")
    assert entity_slug("Stealth Startup", "company") == entity_slug("Stealth", "company") == "stealth"
    for junk in ["Self-employed", "Freelancer", "Confidential", "-", ""]:
        assert entity_slug(junk, "company") is None
    assert entity_slug("Different Name", "company", link="https://www.linkedin.com/company/orbit/") == "orbit"


def test_location_language_and_linkedin():
    assert city_name("San Francisco Bay Area") == "San Francisco, CA"
    assert city_name("Greater Seattle Area") == "Seattle, WA"
    assert city_name("Pune, Maharashtra, India") == "Pune"
    assert country("US") is None
    assert country("in") == ("IN", "India")
    assert language_name("ENGLISH") is None
    assert language_name("hINDI") == "Hindi"
    assert linkedin_slug("/in/ada-one") == "ada-one"
    assert linkedin_slug("/company/ada-one") is None
    assert linkedin_slug("/in/") is None
    assert linkedin_slug("random free text") is None


def test_fixture_join_and_tolerant_records():
    luma = json.loads((FIXTURES / "luma_sample.json").read_text())
    linkedin = json.loads((FIXTURES / "linkedin_sample.json").read_text())
    people, entities, edges, matched = prepare(luma, linkedin)
    assert len(people) == matched == 12
    assert len([e for e in edges["school"] if e["id"] == "uc-berkeley"]) == 4
    assert len([e for e in edges["company"] if e["id"] == "stripe"]) == 3
    assert all(e["id"] != "freelance" for e in edges["company"])
    assert len([e for e in edges["city"] if e["id"] == "seattle-wa"]) == 3


def test_accent_folded_ids_and_most_common_school_display():
    assert entity_slug("San José State University", "school") == entity_slug("San Jose State University", "school")
    luma = [{"api_id": f"u{i}", "linkedin_handle": f"/in/u{i}"} for i in range(3)]
    linkedin = [{"linkedin_id": f"u{i}", "education": [{"title": title}]} for i, title in enumerate(("San José State University", "San Jose State University", "San José State University"))]
    _, entities, _, _ = prepare(luma, linkedin)
    assert {x["name"] for x in entities["School"]} == {"San José State University"}


def test_current_company_id_name_merge_and_stealth():
    luma = [{"api_id": f"u{i}", "linkedin_handle": f"/in/u{i}"} for i in range(3)]
    linkedin = [
        {"linkedin_id": "u0", "current_company": {"name": "Mote", "company_id": "marshell-labs", "link": "https://www.linkedin.com/company/marshell-labs"}},
        {"linkedin_id": "u1", "current_company": {"name": "Mote", "company_id": "mote"}},
        {"linkedin_id": "u2", "current_company": {"name": "Mote", "company_id": "marshell-labs"}},
    ]
    _, _, edges, _ = prepare(luma, linkedin)
    assert {e["id"] for e in edges["company"]} == {"marshell-labs"}
    assert all(e["current"] for e in edges["company"])
    _, _, preferred_edges, _ = prepare(luma, [
        {"linkedin_id": "u0", "current_company": {"name": "Mote", "company_id": "marshell-labs"}},
        {"linkedin_id": "u1", "experience": [{"company": "Mote", "company_id": "mote"}]},
        {"linkedin_id": "u2", "experience": [{"company": "Mote", "company_id": "mote"}]},
    ])
    assert {e["id"] for e in preferred_edges["company"]} == {"marshell-labs"}
    for name in ("Stealth", "Stealth Startup", "Stealth AI Startup", "Stealth Mode", "Stealth Investment Firm"):
        assert entity_slug(name, "company") == "stealth"
        assert display_name(name, "company", "stealth") == "a stealth startup"


def test_school_fallback_when_education_has_no_title():
    luma = [{"api_id": "u", "linkedin_handle": "/in/u"}]
    linkedin = [{"linkedin_id": "u", "education": [{"degree": "Founder"}, {"title": "  "}], "educations_details": "Y Combinator"}]
    _, _, edges, _ = prepare(luma, linkedin)
    assert [e["id"] for e in edges["school"]] == ["y-combinator"]


def test_metros_countries_and_disambiguated_city_ids():
    for name in ("United States", "India", "Canada", "Brazil", "Argentina", "Italy", "Romania", "Sweden", "Switzerland", "Philippines", "United Arab Emirates"):
        assert city_name(name) is None
    pairs = [
        ("Greater Bengaluru Area", "Bengaluru, Karnataka, India", "IN"),
        ("Greater Delhi Area", "New Delhi, Delhi, India", "IN"),
        ("Pune/Pimpri-Chinchwad Area", "Pune, Maharashtra, India", "IN"),
        ("New York City Metropolitan Area", "New York, New York, United States", "US"),
        ("San Francisco Bay Area", "San Francisco, California, United States", "US"),
        ("Greater Hyderabad Area", "Hyderabad, Telangana, India", "IN"),
        ("Greater London", "London, England, United Kingdom", "GB"),
    ]
    for metro, full, code in pairs:
        assert city_name(metro, code) == city_name(full, code)
        assert city_id(metro, code) == city_id(full, code)
    assert city_name("Washington DC-Baltimore Area", "US") == "Washington DC, DC"
    assert city_name("Charlotte Metro", "US") == "Charlotte, NC"
    assert city_name("Hong Kong SAR", "HK") == "Hong Kong"
    assert city_name("Fremont, California, United States", "US") == "Fremont, CA"
    assert city_name("Dublin, California, United States", "US") == "Dublin, CA"
    assert city_name("London, England, United Kingdom", "GB") == "London"
    assert city_id("Dublin, California, United States", "US") != city_id("Dublin, Ohio, United States", "US")
    assert city_id("London, England, United Kingdom", "GB") != city_id("London, Ontario, Canada", "CA")
    assert city_id("Sunnyvale, California, United States", "US") != city_id("San Francisco Bay Area", "US")


def test_language_variants_and_fixed_cause_values():
    assert language_name("English") is None
    assert language_name("chinese (mandarin)") == language_name("Mandarin Chinese") == "Mandarin"
    assert language_name("sANSKRIT") == "Sanskrit"
    luma = [{"api_id": "u", "linkedin_handle": "/in/u"}]
    linkedin = [{"linkedin_id": "u", "languages": [{"title": "English"}, {"title": "Kannada"}], "volunteer_experience": [{"subtitle": "Shelter", "cause": "Animal Welfare"}]}]
    _, _, edges, _ = prepare(luma, linkedin)
    assert [e["id"] for e in edges["language"]] == ["kannada"]
    assert [e["id"] for e in edges["cause"]] == ["animal-welfare"]
