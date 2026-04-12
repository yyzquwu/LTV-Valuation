from __future__ import annotations

import re

from .algorithms import core_street_tokens, extract_house_num_and_street, get_lat_lon, haversine_miles
from .models import Property


def _normalize_address(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\b(unit|apt|ste|#)\s*\w+", "", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _same_house_number(a: str, b: str) -> bool:
    house_a, _ = extract_house_num_and_street(a)
    house_b, _ = extract_house_num_and_street(b)
    return not house_a or not house_b or house_a == house_b


def _within_distance_feet(subject: Property, candidate: Property, feet: float) -> bool:
    subject_lat, subject_lon = get_lat_lon(subject)
    cand_lat, cand_lon = get_lat_lon(candidate)
    miles = haversine_miles(subject_lat, subject_lon, cand_lat, cand_lon)
    return (miles or 9999) * 5280 <= feet


def choose_canonical_subject(subject: Property, properties_in_radius: list[Property]) -> Property:
    chosen = subject
    subject_norm = _normalize_address(subject.UnparsedAddress)
    subject_tokens = core_street_tokens(subject.UnparsedAddress)
    for candidate in properties_in_radius:
        candidate_norm = _normalize_address(candidate.UnparsedAddress)
        candidate_tokens = core_street_tokens(candidate.UnparsedAddress)
        same_street = subject_norm == candidate_norm or subject_norm in candidate_norm or candidate_norm in subject_norm
        street_match = all(token in candidate_tokens for token in subject_tokens) if subject_tokens else False
        if _same_house_number(subject.UnparsedAddress, candidate.UnparsedAddress) and (same_street or street_match or _within_distance_feet(subject, candidate, 105)):
            chosen = candidate
    return chosen


def matches_selected_property_types(property_: Property, selected: list[str]) -> bool:
    if not selected:
        return True
    prop_type = (property_.PropertyType or "").strip().lower()
    return prop_type in {item.lower() for item in selected}
