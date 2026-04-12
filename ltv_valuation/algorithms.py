from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .models import CompSet, CompsResult, Property, PropertyWithDeltas


def haversine_miles(lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * (2 * math.asin(math.sqrt(a)))


def get_lat_lon(prop: Property) -> tuple[float | None, float | None]:
    return (
        prop.Latitude or prop.GeoLatitude or prop.LatitudeDecimal,
        prop.Longitude or prop.GeoLongitude or prop.LongitudeDecimal,
    )


def building_sqft(prop: Property) -> float | None:
    return prop.LivingArea or prop.BuildingAreaTotal


def lot_sqft(prop: Property) -> float | None:
    if prop.LotSizeSquareFeet:
        return prop.LotSizeSquareFeet
    acres = prop.LotSizeArea or prop.LotSizeAcres
    return acres * 43560 if acres else None


def close_date(prop: Property) -> datetime | None:
    raw = prop.CloseDate or prop.ModificationTimestamp or prop.OnMarketDate or prop.ListingContractDate
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(f"{raw}T00:00:00+00:00")
        except ValueError:
            return None


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", text.lower())).strip()


def tokens(text: str) -> set[str]:
    return set(normalize(text).split())


def extract_house_num_and_street(query: str) -> tuple[str | None, list[str]]:
    parts = normalize(query).split()
    if not parts:
        return None, []
    house = parts[0] if parts[0].isdigit() else None
    street_tokens = [part for part in parts if not part.isdigit()]
    return house, street_tokens


def core_street_tokens(text: str) -> set[str]:
    suffixes = {
        "st": "street",
        "street": "street",
        "rd": "road",
        "road": "road",
        "ave": "avenue",
        "avenue": "avenue",
        "blvd": "boulevard",
        "boulevard": "boulevard",
        "ln": "lane",
        "lane": "lane",
        "dr": "drive",
        "drive": "drive",
        "ct": "court",
        "court": "court",
    }
    directionals = {"n", "s", "e", "w", "ne", "nw", "se", "sw"}
    out: list[str] = []
    for token in normalize(text).split():
        if token.isdigit() or token in directionals:
            continue
        out.append(suffixes.get(token, token))
    return set(out)


def similarity_ratio(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(a=normalize(a), b=normalize(b)).ratio()


def _filter_property_type(props: list[Property], wanted: list[str]) -> list[Property]:
    if not wanted:
        return props
    wanted_lower = {item.strip().lower() for item in wanted}
    return [prop for prop in props if (prop.PropertyType or "").strip().lower() in wanted_lower]


def _filter_close_date_range(props: list[Property], min_days: int, max_days: int, require_sold_status: bool = True) -> list[Property]:
    now = datetime.now(timezone.utc)
    results: list[Property] = []
    for prop in props:
        status = ((prop.StandardStatus or prop.MlsStatus) or "").strip().lower()
        if require_sold_status and status not in {"sold", "closed"}:
            continue
        closed = close_date(prop)
        if not closed:
            continue
        days = (now - closed.astimezone(timezone.utc)).days
        if min_days <= days <= max_days:
            results.append(prop)
    return results


def _filter_size_diff(props: list[Property], subject: Property, building_diff_max: float, lot_diff_max: float) -> list[Property]:
    sb = building_sqft(subject)
    sl = lot_sqft(subject)
    if sb is None or sl is None:
        return []
    results: list[Property] = []
    for prop in props:
        cb = building_sqft(prop)
        cl = lot_sqft(prop)
        if cb is None or cl is None:
            continue
        if abs(sb - cb) < building_diff_max and abs(sl - cl) < lot_diff_max:
            results.append(prop)
    return results


def _format_comp_row(prop: Property, subject: Property, is_active: bool) -> PropertyWithDeltas:
    sb = building_sqft(subject)
    sl = lot_sqft(subject)
    cb = building_sqft(prop)
    cl = lot_sqft(prop)
    bdiff = cb - sb if sb is not None and cb is not None else None
    ldiff = cl - sl if sl is not None and cl is not None else None
    subj_lat, subj_lon = get_lat_lon(subject)
    comp_lat, comp_lon = get_lat_lon(prop)
    dist = haversine_miles(subj_lat, subj_lon, comp_lat, comp_lon)
    row = PropertyWithDeltas.model_validate(prop.model_dump())
    row.delta_building_sqft = f"{bdiff:+.0f}" if bdiff is not None else None
    row.delta_lot_sqft = f"{ldiff:+.0f}" if ldiff is not None else None
    row.delta_distance = round(dist, 1) if dist is not None else None
    row.SoldPrice = None if is_active else (prop.ClosePrice or prop.CurrentPrice)
    row.LotSqft = cl
    row.FixFlipDuplicate = bool(prop.FixFlipDuplicate)
    return row


def _process_comp_set(comps: list[Property], subject: Property, name: str, is_active: bool, max_comps: int | None, per_type_max: int | None) -> CompSet:
    def sort_key(prop: Property):
        if is_active:
            raw = prop.ModificationTimestamp or prop.OnMarketTimestamp or ""
        else:
            raw = (close_date(prop) or datetime.min.replace(tzinfo=timezone.utc)).isoformat()
        return raw

    comps = sorted(comps, key=sort_key, reverse=True)
    if per_type_max is not None:
        seen: dict[str, int] = {}
        limited: list[Property] = []
        for prop in comps:
            key = (prop.PropertyType or "Unknown").strip()
            count = seen.get(key, 0)
            if count < per_type_max:
                limited.append(prop)
                seen[key] = count + 1
        comps = limited
    if max_comps is not None:
        comps = comps[:max_comps]
    preview = [_format_comp_row(prop, subject, is_active) for prop in comps]
    price_values = [item.SoldPrice if not is_active else item.CurrentPrice for item in preview]
    valid = [value for value in price_values if value is not None]
    avg_price = sum(valid) / len(valid) if valid else None
    return CompSet(name=name, comps=comps, df_preview=preview, avg_price=avg_price, count=len(comps))


def _build_fix_flip_comps(candidates: list[Property], subject_listing_key: str, min_hold_days: int, max_hold_days: int, min_roi: float) -> tuple[list[Property], int]:
    groups: dict[str, list[Property]] = {}
    for prop in candidates:
        if prop.ListingKey == subject_listing_key:
            continue
        status = ((prop.StandardStatus or prop.MlsStatus) or "").strip().lower()
        if status not in {"sold", "closed"}:
            continue
        key = f"{normalize(prop.UnparsedAddress)}__{(prop.PostalCode or '').lower()}"
        groups.setdefault(key, []).append(prop)
    flips: list[Property] = []
    dupes = 0
    for props in groups.values():
        if len(props) < 2:
            continue
        props = sorted(props, key=lambda prop: close_date(prop) or datetime.min.replace(tzinfo=timezone.utc))
        acquisition, resale = props[-2], props[-1]
        acq_date = close_date(acquisition)
        resale_date = close_date(resale)
        if not acq_date or not resale_date or resale.ClosePrice is None or acquisition.ClosePrice is None:
            continue
        hold_days = (resale_date - acq_date).days
        if not (min_hold_days <= hold_days <= max_hold_days):
            continue
        roi = (resale.ClosePrice - acquisition.ClosePrice) / acquisition.ClosePrice
        if roi < min_roi:
            continue
        enriched = resale.model_copy(deep=True)
        enriched.FlipAcquiredDate = acquisition.CloseDate
        enriched.FlipAcquiredPrice = acquisition.ClosePrice
        enriched.FlipResaleDate = resale.CloseDate
        enriched.FlipResalePrice = resale.ClosePrice
        enriched.FlipHoldDays = hold_days
        enriched.FlipRoiPercent = roi
        flips.append(enriched)
    return flips, dupes


def comps_pipeline(
    properties_in_radius: list[Property],
    subject_listing_key: str,
    wanted_types: list[str],
    min_days: int = 0,
    max_days: int = 365,
    building_diff_max: float = 500,
    lot_diff_max: float = 1000,
    max_comps: int | None = None,
    per_type_max: int | None = None,
    fix_flip_min_hold_days: int = 30,
    fix_flip_max_hold_days: int = 365,
    fix_flip_min_roi: float = 0.1,
    enable_fix_flip: bool = True,
) -> tuple[Property, CompsResult, dict]:
    subject = next(prop for prop in properties_in_radius if prop.ListingKey == subject_listing_key)
    candidates = [prop for prop in properties_in_radius if prop.ListingKey != subject_listing_key]
    typed = _filter_property_type(candidates, wanted_types)
    sold_candidates = _filter_size_diff(typed, subject, building_diff_max, lot_diff_max)
    recent = _filter_close_date_range(sold_candidates, 0, 183, True)
    older = _filter_close_date_range(sold_candidates, 184, max(184, max_days), True)
    active = [
        prop
        for prop in _filter_size_diff(typed, subject, building_diff_max * 2, lot_diff_max * 2)
        if ((prop.StandardStatus or prop.MlsStatus) or "").strip().lower() not in {"sold", "closed"}
    ]
    fix_flip, dupes = _build_fix_flip_comps(typed, subject_listing_key, fix_flip_min_hold_days, fix_flip_max_hold_days, fix_flip_min_roi) if enable_fix_flip else ([], 0)
    result = CompsResult(
        recent=_process_comp_set(recent, subject, "Recent (≤6 months)", False, max_comps, per_type_max),
        older=_process_comp_set(older, subject, "Older (>6 months)", False, max_comps, per_type_max),
        active=_process_comp_set(active, subject, "Active Listings", True, max_comps, per_type_max),
        fixFlip=_process_comp_set(fix_flip, subject, "Fix & Flip", False, max_comps, per_type_max),
    )
    return subject, result, {"fixFlipDuplicateCount": dupes}
