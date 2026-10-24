"""Pure normalization helpers for graph entities."""
import re
import unicodedata
import ast
from urllib.parse import urlparse


SCHOOL_ALIASES = {
    "uc berkeley": "uc-berkeley", "university of california berkeley": "uc-berkeley",
    "university of california at berkeley": "uc-berkeley",
    "iit bombay": "iit-bombay", "indian institute of technology bombay": "iit-bombay",
    "cmu": "carnegie-mellon-university", "carnegie mellon university": "carnegie-mellon-university",
    "georgia tech": "georgia-institute-of-technology", "georgia institute of technology": "georgia-institute-of-technology",
    "uiuc": "university-of-illinois-urbana-champaign",
    "university of illinois urbana champaign": "university-of-illinois-urbana-champaign",
    "ut austin": "university-of-texas-at-austin", "university of texas at austin": "university-of-texas-at-austin",
    "nyu": "new-york-university", "new york university": "new-york-university",
}
SCHOOL_DISPLAY = {
    "uc-berkeley": "UC Berkeley", "iit-bombay": "IIT Bombay",
    "carnegie-mellon-university": "Carnegie Mellon University",
    "georgia-institute-of-technology": "Georgia Tech",
    "university-of-illinois-urbana-champaign": "UIUC",
    "university-of-texas-at-austin": "UT Austin", "new-york-university": "NYU",
}
JUNK = {"", "-", "self employed", "self-employed", "freelance", "freelancer", "confidential"}
SUFFIXES = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "gmbh", "pvt", "private", "co"}
METROS = {
    "san francisco bay area": "San Francisco", "greater seattle area": "Seattle",
    "greater new york city area": "New York City", "greater boston": "Boston",
    "greater los angeles area": "Los Angeles", "greater london": "London",
    "new york city metropolitan area": "New York City",
    "pune/pimpri-chinchwad area": "Pune", "washington dc-baltimore area": "Washington DC",
    "hong kong sar": "Hong Kong",
}
COUNTRY_CITIES = {"united states", "india", "canada", "brazil", "argentina", "italy", "romania", "sweden", "switzerland", "philippines", "united arab emirates"}
US_STATES = {"california": "CA", "washington": "WA", "new york": "NY", "texas": "TX", "tennessee": "TN", "new jersey": "NJ", "illinois": "IL", "mississippi": "MS", "ohio": "OH", "indiana": "IN", "wisconsin": "WI", "hawaii": "HI", "florida": "FL", "pennsylvania": "PA", "massachusetts": "MA", "north carolina": "NC", "district of columbia": "DC"}
METRO_STATES = {"san francisco": "CA", "seattle": "WA", "new york city": "NY", "los angeles": "CA", "boston": "MA", "washington dc": "DC", "charlotte": "NC"}
METRO_REGIONS = {"bengaluru": "Karnataka", "delhi": "Delhi", "pune": "Maharashtra", "hyderabad": "Telangana", "london": "England", "izmir": "Izmir"}
COUNTRIES = {"US": "United States", "IN": "India", "SG": "Singapore", "CA": "Canada", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "AU": "Australia", "NL": "Netherlands"}


def slug(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def linkedin_slug(value):
    """Accept only a complete /in/<slug> path (or a bare linkedin_id)."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if "/" not in value and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        return value.lower()
    match = re.search(r"(?:^|/)in/([A-Za-z0-9][A-Za-z0-9_-]*)(?:[/?#]|$)", value, re.I)
    return match.group(1).lower() if match else None


def entity_slug(value, kind, link=None, company_id=None):
    name = str(value or "").strip()
    if not name or name.lower() in JUNK:
        return None
    if kind == "company" and slug(name) in {"stealth", "stealth-startup", "stealth-ai-startup", "stealth-mode", "stealth-investment-firm"}:
        return "stealth"
    normal = slug(name)
    if kind == "school":
        alias = SCHOOL_ALIASES.get(normal.replace("-", " "))
        if alias:
            return alias
    if kind == "company" and company_id:
        candidate = slug(company_id)
        if candidate:
            return candidate
    if link:
        path = urlparse(str(link)).path
        part = "school" if kind == "school" else "company"
        match = re.search(rf"(?:^|/){part}/([^/]+)", path, re.I)
        if match:
            candidate = slug(match.group(1))
            if kind == "school" and candidate in SCHOOL_ALIASES.values():
                return candidate
            return candidate
    words = normal.split("-")
    if words and words[0] == "the":
        words.pop(0)
    if kind == "company":
        while words and words[-1] in SUFFIXES:
            words.pop()
    return "-".join(words) or None


def display_name(name, kind, entity_id):
    if kind == "company" and entity_id == "stealth":
        return "a stealth startup"
    if kind == "school" and entity_id in SCHOOL_DISPLAY:
        return SCHOOL_DISPLAY[entity_id]
    return str(name or "").strip()


def city_parts(value, country_code=None):
    if not isinstance(value, str) or not value.strip():
        return None
    parts = [part.strip() for part in value.split(",")]
    first = parts[0]
    if first.lower() in COUNTRY_CITIES:
        return None
    if first.lower() == "new delhi":
        first = "Delhi"
    elif first.lower() == "new york" and len(parts) > 1 and parts[1].lower() == "new york":
        first = "New York City"
    else:
        first = METROS.get(first.lower(), first)
        first = re.sub(r"^Greater (.+?)(?: Area)?$", r"\1", first, flags=re.I)
        first = re.sub(r"^(.+?)(?: Metropolitan Area| Metro)$", r"\1", first, flags=re.I)
    if first.lower() == "new york city":
        first = "New York City"
    if first.lower() == "bengaluru":
        first = "Bengaluru"
    state = US_STATES.get(parts[1].lower()) if len(parts) > 1 else None
    state = state or (METRO_STATES.get(first.lower()) if len(parts) == 1 else None)
    is_us = str(country_code or "").upper() == "US" or (len(parts) > 2 and parts[-1].lower() == "united states") or bool(state)
    return first, state, is_us


def city_name(value, country_code=None):
    parts = city_parts(value, country_code)
    if not parts:
        return None
    name, state, is_us = parts
    return f"{name}, {state}" if is_us and state else name


def city_id(value, country_code=None):
    parts = city_parts(value, country_code)
    if not parts:
        return None
    name, state, is_us = parts
    region = value.split(",")[1].strip() if "," in value else ""
    region = region or METRO_REGIONS.get(name.lower(), "")
    return slug(f"{name}-{state or region or 'US'}" if is_us else f"{name}-{region}-{str(country_code or '').upper() or (value.split(',')[-1].strip() if ',' in value else '')}")


def country(value):
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code) or code == "US":
        return None
    return code, COUNTRIES.get(code, code)


def language_name(value):
    name = str(value or "").strip()
    if not name or name.lower() == "english":
        return None
    if name.lower() in {"chinese (mandarin)", "mandarin chinese"}:
        return "Mandarin"
    return name.title()


GENERIC_HASHTAGS = set("ai artificialintelligence machinelearning tech technology innovation startups startup hiring career learning linkedin opentowork jobsearch software softwareengineering programming coding datascience genai generativeai".split())


def linkedin_org_slug(value, kind):
    if not isinstance(value, str):
        return None
    match = re.search(rf"(?:^|/){kind}/([^/?#]+)", value, re.I)
    return slug(match.group(1)) if match else None


def x_handle(value):
    if not isinstance(value, str):
        return None
    value = value.strip().rstrip("/")
    match = re.search(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)(?:$|[?#])", value, re.I)
    if match:
        return match.group(1).lower()
    return value.lstrip("@").lower() if re.fullmatch(r"@?[A-Za-z0-9_]+", value) else None


def hashtags(value):
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            value = [value]
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            tag = item.strip().lstrip("#").lower()
            if re.fullmatch(r"[a-z0-9_]+", tag) and tag not in GENERIC_HASHTAGS:
                result.append(tag)
    return list(dict.fromkeys(result))
