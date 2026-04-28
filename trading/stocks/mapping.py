"""ISM-to-GICS industry mapping and company match scoring helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ISMIndustryMappingRule:
    """Curated mapping from an ISM industry label to likely public-company groups."""

    sector: str
    gics_industries: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


ISM_INDUSTRY_MAPPING: dict[str, ISMIndustryMappingRule] = {
    # Manufacturing: keep these rules conservative. It is better to drop a
    # company than to assign it to the wrong ISM theme with false precision.
    "apparel, leather & allied products": ISMIndustryMappingRule(
        sector="Consumer Discretionary",
        gics_industries=("Apparel, Accessories & Luxury Goods", "Footwear"),
        keywords=("apparel", "footwear", "luxury", "leather"),
    ),
    "chemical products": ISMIndustryMappingRule(
        sector="Materials",
        gics_industries=("Specialty Chemicals", "Commodity Chemicals"),
        keywords=("chemical", "chemicals", "fertilizer", "industrial gas"),
    ),
    "computer & electronic products": ISMIndustryMappingRule(
        sector="Information Technology",
        gics_industries=(
            "Semiconductors & Semiconductor Equipment",
            "Technology Hardware, Storage & Peripherals",
            "Electronic Equipment, Instruments & Components",
            "Communications Equipment",
        ),
        keywords=(
            "semiconductor",
            "chip",
            "hardware",
            "electronic",
            "electronics",
            "computer",
            "storage",
            "communications",
        ),
    ),
    "electrical equipment, appliances & components": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=("Electrical Components & Equipment", "Heavy Electrical Equipment"),
        keywords=("electrical", "power equipment", "components", "appliance"),
    ),
    "fabricated metal products": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=("Industrial Machinery & Supplies & Components",),
        keywords=("metal", "fabricated", "machinery", "components"),
    ),
    "food, beverage & tobacco products": ISMIndustryMappingRule(
        sector="Consumer Staples",
        gics_industries=(
            "Packaged Foods & Meats",
            "Brewers",
            "Soft Drinks & Non-alcoholic Beverages",
            # FMP taxonomy variants
            "Packaged Foods",
            "Food Confectioners",
            "Beverages - Non-Alcoholic",
            "Beverages - Brewers",
            "Tobacco",
        ),
        keywords=("food", "beverage", "tobacco", "consumer staples"),
    ),
    "furniture & related products": ISMIndustryMappingRule(
        sector="Consumer Discretionary",
        gics_industries=(
            "Home Furnishings",
            "Home Improvement Retail",
            # FMP taxonomy variant
            "Furnishings, Fixtures & Appliances",
        ),
        keywords=("furniture", "home", "furnishings", "improvement"),
    ),
    "machinery": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=(
            "Industrial Machinery & Supplies & Components",
            "Agricultural & Farm Machinery",
            "Construction Machinery & Heavy Transportation Equipment",
        ),
        keywords=("machinery", "industrial", "farm", "construction", "equipment"),
    ),
    "miscellaneous manufacturing": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=("Industrial Machinery & Supplies & Components",),
        keywords=("manufacturing", "industrial", "components"),
    ),
    "nonmetallic mineral products": ISMIndustryMappingRule(
        sector="Materials",
        gics_industries=("Construction Materials",),
        keywords=("cement", "glass", "mineral", "construction materials"),
    ),
    "paper products": ISMIndustryMappingRule(
        sector="Materials",
        gics_industries=("Paper Products", "Paper Packaging"),
        keywords=("paper", "packaging", "containerboard"),
    ),
    "petroleum & coal products": ISMIndustryMappingRule(
        sector="Energy",
        gics_industries=("Integrated Oil & Gas", "Oil & Gas Refining & Marketing"),
        keywords=("petroleum", "refining", "oil", "gas", "coal"),
    ),
    "plastics & rubber products": ISMIndustryMappingRule(
        sector="Materials",
        gics_industries=(
            "Commodity Chemicals",
            "Specialty Chemicals",
            # FMP taxonomy variants
            "Chemicals - Specialty",
            "Chemicals",
        ),
        keywords=("plastic", "rubber", "polymer", "resin"),
    ),
    "primary metals": ISMIndustryMappingRule(
        sector="Materials",
        gics_industries=("Steel", "Aluminum", "Diversified Metals & Mining"),
        keywords=("metal", "steel", "aluminum", "mining", "copper"),
    ),
    "printing & related support activities": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=("Commercial Printing",),
        keywords=("printing", "print", "labels", "packaging print", "publishing services"),
    ),
    "textile mills": ISMIndustryMappingRule(
        sector="Consumer Discretionary",
        gics_industries=("Textiles",),
        keywords=("textile", "fabrics", "mills"),
    ),
    # Transportation equipment is broad in ISM, but it should still match
    # actual transport-related industries rather than unrelated industrials.
    "transportation equipment": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=(
            "Aerospace & Defense",
            "Construction Machinery & Heavy Transportation Equipment",
            "Agricultural & Farm Machinery",
            "Automobile Manufacturers",
            "Automotive Parts & Equipment",
        ),
        keywords=(
            "transport",
            "aerospace",
            "defense",
            "aircraft",
            "aviation",
            "jet",
            "truck",
            "automotive",
            "machinery",
        ),
    ),
    "wood products": ISMIndustryMappingRule(
        sector="Materials",
        gics_industries=("Forest Products", "Building Products"),
        keywords=("wood", "forest", "lumber", "timber", "building products"),
    ),
    # Services
    "accommodation & food services": ISMIndustryMappingRule(
        sector="Consumer Discretionary",
        gics_industries=("Hotels, Resorts & Cruise Lines", "Restaurants"),
        keywords=("hotel", "restaurant", "lodging", "travel"),
    ),
    "arts, entertainment & recreation": ISMIndustryMappingRule(
        sector="Communication Services",
        gics_industries=("Movies & Entertainment", "Interactive Media & Services"),
        keywords=("entertainment", "media", "recreation", "gaming"),
    ),
    "construction": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=("Construction & Engineering", "Construction Machinery & Heavy Transportation Equipment"),
        keywords=("construction", "engineering", "infrastructure"),
    ),
    "finance & insurance": ISMIndustryMappingRule(
        sector="Financials",
        gics_industries=("Diversified Banks", "Investment Banking & Brokerage", "Property & Casualty Insurance"),
        keywords=("bank", "insurance", "financial", "brokerage", "payments"),
    ),
    "health care & social assistance": ISMIndustryMappingRule(
        sector="Health Care",
        gics_industries=("Pharmaceuticals", "Health Care Equipment", "Managed Health Care"),
        keywords=("health", "pharma", "medical", "care"),
    ),
    "information": ISMIndustryMappingRule(
        sector="Communication Services",
        gics_industries=("Interactive Media & Services", "Advertising", "Integrated Telecommunication Services"),
        keywords=("information", "internet", "telecom", "media"),
    ),
    "professional, scientific & technical services": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=("Research & Consulting Services",),
        keywords=("consulting", "scientific", "technical", "research", "services"),
    ),
    "real estate, rental & leasing": ISMIndustryMappingRule(
        sector="Real Estate",
        gics_industries=("Industrial REITs", "Specialized REITs", "Retail REITs"),
        keywords=("reit", "real estate", "leasing", "rental"),
    ),
    "retail trade": ISMIndustryMappingRule(
        sector="Consumer Discretionary",
        gics_industries=("Broadline Retail", "Home Improvement Retail", "Apparel Retail"),
        keywords=("retail", "ecommerce", "store", "consumer"),
    ),
    "utilities": ISMIndustryMappingRule(
        sector="Utilities",
        gics_industries=("Electric Utilities", "Multi-Utilities", "Water Utilities"),
        keywords=("utility", "electric", "water", "power"),
    ),
    "wholesale trade": ISMIndustryMappingRule(
        sector="Industrials",
        gics_industries=("Trading Companies & Distributors",),
        keywords=("wholesale", "distribution", "distributor"),
    ),
}

_NON_SIGNAL_TOKENS = {
    "and",
    "related",
    "support",
    "activities",
    "products",
    "services",
    "equipment",
    "components",
    "goods",
    "allied",
}


def normalize_label(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# Normalized lookups so all callers work regardless of whether the label uses
# "&" or "and" — ISM press-release text normalizes to "and" after stripping HTML.
GICS_MAPPING: dict[str, str] = {
    normalize_label(key): rule.sector for key, rule in ISM_INDUSTRY_MAPPING.items()
}

# Rule lookup keyed by normalized ISM industry label.  Used by
# company_industry_match_confidence so that _rule_match_score fires for
# industries whose raw key contains "&" (e.g. "food, beverage & tobacco products").
_NORMALIZED_ISM_MAPPING: dict[str, ISMIndustryMappingRule] = {
    normalize_label(key): rule for key, rule in ISM_INDUSTRY_MAPPING.items()
}


def sector_for_ism_industry(industry: str | None) -> str | None:
    return GICS_MAPPING.get(normalize_label(industry))


def best_ism_match(
    company_industry: str | None,
    rankings: Iterable[object],
) -> tuple[str | None, float]:
    best_industry: str | None = None
    best_confidence = 0.0
    for item in rankings:
        ism_industry = getattr(item, "industry", None)
        if not isinstance(ism_industry, str):
            continue
        confidence = company_industry_match_confidence(company_industry, ism_industry)
        if confidence > best_confidence:
            best_confidence = confidence
            best_industry = ism_industry
    return best_industry, best_confidence


def company_industry_match_confidence(
    company_industry: str | None,
    ism_industry: str | None,
) -> float:
    company = normalize_label(company_industry)
    ism = normalize_label(ism_industry)
    if not company or not ism:
        return 0.0

    rule = _NORMALIZED_ISM_MAPPING.get(ism)
    scores = [
        _lexical_overlap_score(company, ism),
    ]
    if rule is not None:
        scores.append(_rule_match_score(company, rule))
    return max(0.0, min(1.0, max(scores)))


def _rule_match_score(company: str, rule: ISMIndustryMappingRule) -> float:
    exact_matches = [normalize_label(value) for value in rule.gics_industries]
    if company in exact_matches:
        return 1.0
    if any(value and (value in company or company in value) for value in exact_matches):
        return 0.95

    keyword_hits = sum(1 for keyword in rule.keywords if normalize_label(keyword) in company)
    if keyword_hits >= 2:
        return min(0.95, 0.75 + 0.08 * (keyword_hits - 1))
    if keyword_hits == 1:
        return 0.78

    reference_tokens: set[str] = set()
    for value in (*rule.gics_industries, *rule.keywords):
        reference_tokens.update(_meaningful_tokens(value))
    overlap = reference_tokens & _meaningful_tokens(company)
    if overlap:
        return min(0.85, 0.55 + 0.1 * len(overlap))
    return 0.1


def _lexical_overlap_score(company: str, ism: str) -> float:
    company_tokens = _meaningful_tokens(company)
    ism_tokens = _meaningful_tokens(ism)
    if not company_tokens or not ism_tokens:
        return 0.0
    overlap = company_tokens & ism_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / max(1, len(ism_tokens))
    return min(0.8, 0.4 + 0.4 * coverage)


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_label(value).split()
        if token and token not in _NON_SIGNAL_TOKENS
    }