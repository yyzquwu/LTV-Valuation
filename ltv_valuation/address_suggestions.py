from __future__ import annotations

from .algorithms import core_street_tokens, extract_house_num_and_street, normalize, similarity_ratio, tokens
from .models import Property


def build_address_suggestions(properties: list[Property], address: str) -> list[dict]:
    query_house, _ = extract_house_num_and_street(address)
    query_core_tokens = list(core_street_tokens(address))
    subset = properties
    if query_house:
        subset = [prop for prop in subset if query_house in tokens(prop.UnparsedAddress)]
    if query_core_tokens:
        filtered: list[Property] = []
        for prop in subset:
            prop_tokens = core_street_tokens(prop.UnparsedAddress)
            if all(
                any(candidate == token or candidate.startswith(token) or token.startswith(candidate) for candidate in prop_tokens)
                for token in query_core_tokens
            ):
                filtered.append(prop)
        subset = filtered
    normalized_query = normalize(address)
    scored = sorted(
        [{"property": prop.model_dump(), "score": similarity_ratio(normalized_query, normalize(prop.UnparsedAddress))} for prop in subset],
        key=lambda item: item["score"],
        reverse=True,
    )
    return scored[:10]
