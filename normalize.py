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
# ISO 3166-1 alpha-2 display names (249 assigned codes).
COUNTRIES = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AG": "Antigua and Barbuda", "AI": "Anguilla", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica",
    "AR": "Argentina", "AS": "American Samoa", "AT": "Austria",
    "AU": "Australia", "AW": "Aruba", "AX": "Åland Islands",
    "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BB": "Barbados",
    "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso",
    "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi",
    "BJ": "Benin", "BL": "Saint Barthélemy", "BM": "Bermuda",
    "BN": "Brunei", "BO": "Bolivia", "BQ": "Bonaire, Sint Eustatius and Saba",
    "BR": "Brazil", "BS": "Bahamas", "BT": "Bhutan",
    "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus",
    "BZ": "Belize", "CA": "Canada", "CC": "Cocos Islands",
    "CD": "Democratic Republic of the Congo", "CF": "Central African Republic", "CG": "Republic of the Congo",
    "CH": "Switzerland", "CI": "Côte d'Ivoire", "CK": "Cook Islands",
    "CL": "Chile", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba",
    "CV": "Cabo Verde", "CW": "Curaçao", "CX": "Christmas Island",
    "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica",
    "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara",
    "ER": "Eritrea", "ES": "Spain", "ET": "Ethiopia",
    "FI": "Finland", "FJ": "Fiji", "FK": "Falkland Islands",
    "FM": "Micronesia", "FO": "Faroe Islands", "FR": "France",
    "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada",
    "GE": "Georgia", "GF": "French Guiana", "GG": "Guernsey",
    "GH": "Ghana", "GI": "Gibraltar", "GL": "Greenland",
    "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea", "GR": "Greece", "GS": "South Georgia and the South Sandwich Islands",
    "GT": "Guatemala", "GU": "Guam", "GW": "Guinea-Bissau",
    "GY": "Guyana", "HK": "Hong Kong", "HM": "Heard Island and McDonald Islands",
    "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IM": "Isle of Man", "IN": "India",
    "IO": "British Indian Ocean Territory", "IQ": "Iraq", "IR": "Iran",
    "IS": "Iceland", "IT": "Italy", "JE": "Jersey",
    "JM": "Jamaica", "JO": "Jordan", "JP": "Japan",
    "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia",
    "KI": "Kiribati", "KM": "Comoros", "KN": "Saint Kitts and Nevis",
    "KP": "North Korea", "KR": "South Korea", "KW": "Kuwait",
    "KY": "Cayman Islands", "KZ": "Kazakhstan", "LA": "Laos",
    "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein",
    "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "LY": "Libya", "MA": "Morocco", "MC": "Monaco",
    "MD": "Moldova", "ME": "Montenegro", "MF": "Saint Martin (French part)",
    "MG": "Madagascar", "MH": "Marshall Islands", "MK": "North Macedonia",
    "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia",
    "MO": "Macao", "MP": "Northern Mariana Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta",
    "MU": "Mauritius", "MV": "Maldives", "MW": "Malawi",
    "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique",
    "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger",
    "NF": "Norfolk Island", "NG": "Nigeria", "NI": "Nicaragua",
    "NL": "Netherlands", "NO": "Norway", "NP": "Nepal",
    "NR": "Nauru", "NU": "Niue", "NZ": "New Zealand",
    "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PM": "Saint Pierre and Miquelon",
    "PN": "Pitcairn Islands", "PR": "Puerto Rico", "PS": "Palestine",
    "PT": "Portugal", "PW": "Palau", "PY": "Paraguay",
    "QA": "Qatar", "RE": "Réunion", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi Arabia", "SB": "Solomon Islands", "SC": "Seychelles",
    "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SH": "Saint Helena, Ascension and Tristan da Cunha", "SI": "Slovenia", "SJ": "Svalbard and Jan Mayen",
    "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino",
    "SN": "Senegal", "SO": "Somalia", "SR": "Suriname",
    "SS": "South Sudan", "ST": "Sao Tome and Principe", "SV": "El Salvador",
    "SX": "Sint Maarten (Dutch part)", "SY": "Syria", "SZ": "Eswatini",
    "TC": "Turks and Caicos Islands", "TD": "Chad", "TF": "French Southern Territories",
    "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan",
    "TK": "Tokelau", "TL": "Timor-Leste", "TM": "Turkmenistan",
    "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey",
    "TT": "Trinidad and Tobago", "TV": "Tuvalu", "TW": "Taiwan",
    "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "United States Minor Outlying Islands", "US": "United States", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VA": "Vatican City", "VC": "Saint Vincent and the Grenadines",
    "VE": "Venezuela", "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands",
    "VN": "Vietnam", "VU": "Vanuatu", "WF": "Wallis and Futuna",
    "WS": "Samoa", "YE": "Yemen", "YT": "Mayotte",
    "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}
THE_COUNTRIES = {
    "United Kingdom",
    "United States",
    "United Arab Emirates",
    "Netherlands",
    "Philippines",
    "Cayman Islands",
    "Bahamas",
    "Gambia",
    "Czech Republic",
    "Dominican Republic",
    "Central African Republic",
    "Comoros",
    "Maldives",
    "Marshall Islands",
    "Solomon Islands",
    "Falkland Islands",
    "Faroe Islands",
    "British Virgin Islands",
    "U.S. Virgin Islands",
    "Cook Islands",
    "Turks and Caicos Islands",
    "Northern Mariana Islands",
    "Cocos Islands",
    "Vatican City",
    "Seychelles",
    "Åland Islands",
    "Democratic Republic of the Congo",
    "Republic of the Congo",
    "Pitcairn Islands",
    "Isle of Man",
    "British Indian Ocean Territory",
    "French Southern Territories",
    "United States Minor Outlying Islands",
    "South Georgia and the South Sandwich Islands",
    "Heard Island and McDonald Islands",
}


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


def field_names(value):
    """Fields of study from one LinkedIn education entry: "Data Science & Analytics, Statistics" -> two fields."""
    if not isinstance(value, str):
        return []
    result = []
    for part in re.split(r"[,;/|]", value):
        name = " ".join(part.replace("&", " and ").split()).strip(" .-")
        if not re.search(r"[A-Za-z]{2}", name):  # keeps AI, CS, UX; drops "B.S." and "-"
            continue
        if len(name) <= 4 and " " not in name:
            name = name.upper() if name.islower() else name
        elif name.islower() or name.isupper():
            name = name.title()
        if slug(name) and slug(name) not in {slug(n) for n in result}:
            result.append(name)
    return result


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
    """Return the full website host, ignoring only a leading www."""
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip() if "://" in value else "https://" + value.strip())
    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if "." not in host or not all(host.split(".")):
        return None
    return host


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
