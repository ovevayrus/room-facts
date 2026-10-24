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
COUNTRIES = {
    "AE": "United Arab Emirates", "AL": "Albania", "AR": "Argentina", "AT": "Austria", "AU": "Australia",
    "BD": "Bangladesh", "BE": "Belgium", "BG": "Bulgaria", "BR": "Brazil",
    "CA": "Canada", "CH": "Switzerland", "CL": "Chile", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark",
    "EG": "Egypt", "ES": "Spain", "FI": "Finland", "FR": "France",
    "GB": "United Kingdom", "GR": "Greece", "HK": "Hong Kong", "HU": "Hungary",
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IN": "India",
    "IT": "Italy", "JP": "Japan", "KE": "Kenya", "KR": "South Korea",
    "KY": "Cayman Islands", "LK": "Sri Lanka", "LT": "Lithuania", "LU": "Luxembourg", "MX": "Mexico", "MY": "Malaysia",
    "NL": "Netherlands", "NO": "Norway", "NZ": "New Zealand", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "RU": "Russia", "SA": "Saudi Arabia", "SE": "Sweden", "SG": "Singapore",
    "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan", "UA": "Ukraine",
    "US": "United States", "VN": "Vietnam", "ZA": "South Africa",
}
THE_COUNTRIES = {"United Kingdom", "United States", "United Arab Emirates", "Netherlands", "Philippines"}


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
    name = COUNTRIES.get(code)
    return (code, name) if name else None


def country_phrase(name):
    """Add the article only where a country is used in a sentence."""
    return f"the {name}" if name in THE_COUNTRIES else name


def language_name(value):
    name = str(value or "").strip()
    if not name or name.lower() == "english":
        return None
    if name.lower() in {"chinese (mandarin)", "mandarin chinese"}:
        return "Mandarin"
    return name.title()


GENERIC_HASHTAGS = set("ai artificialintelligence machinelearning tech technology innovation startups startup hiring career learning linkedin opentowork jobsearch software softwareengineering programming coding datascience genai generativeai".split())
GENERIC_IG_HASHTAGS = GENERIC_HASHTAGS | set("fyp foryou instadaily instalike instagram instagood love viral sf sanfrancisco bayarea business entrepreneur photooftheday explore reels trending".split())


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


def hashtags(value, skip=None):
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
            if re.fullmatch(r"[a-z0-9_]+", tag) and tag not in (skip if skip is not None else GENERIC_HASHTAGS):
                result.append(tag)
    return list(dict.fromkeys(result))


def instagram_handle(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    match = re.fullmatch(r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]+)(?:/)?(?:[?#].*)?", value, re.I)
    if match:
        return match.group(1).lower()
    return value.lstrip("@").lower() if re.fullmatch(r"@?[A-Za-z0-9._]+", value) else None


def root_domain(value):
    """Compare website hosts, ignoring www and ordinary subdomains."""
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip() if "://" in value else "https://" + value.strip())
    host = (parsed.hostname or "").lower().strip(".")
    parts = host.split(".")
    if len(parts) < 2 or not all(parts):
        return None
    if len(parts) >= 3 and ".".join(parts[-2:]) in {"github.io", "vercel.app", "netlify.app", "wordpress.com"}:
        return ".".join(parts[-3:])
    if len(parts) >= 3 and parts[-1] in {"uk", "au", "jp", "nz", "za", "br", "in"} and parts[-2] in {"co", "com", "org", "net", "ac"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def funding_stage(value):
    """Keep only funding round names that describe a useful startup stage."""
    if not isinstance(value, str):
        return None
    name = re.sub(r"\s+round$", "", re.sub(r"\s+", " ", value.strip()), flags=re.I).strip()
    folded = slug(name)
    if folded == "pre-seed":
        return "Pre-Seed"
    if folded == "seed":
        return "Seed"
    match = re.fullmatch(r"series-([a-z])", folded)
    return f"Series {match.group(1).upper()}" if match else None
