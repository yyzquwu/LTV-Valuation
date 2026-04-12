from __future__ import annotations

import math
from datetime import datetime

from .address_suggestions import build_address_suggestions
from .algorithms import building_sqft, comps_pipeline, get_lat_lon, haversine_miles, lot_sqft
from .ltv import get_program_ltv, get_service_area_ltv
from .models import BaseCompInput, Property, PropertySummaryRequest, PropertySummaryResponse, RenovatedCompInput, SubjectSnapshot
from .subject_matching import choose_canonical_subject, matches_selected_property_types
from .trestle_client import MLSClient, TrestleClient
from .valuation import calculate_valuations


def _normalize_zip(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:5] if digits else None


def _parse_query(request: PropertySummaryRequest) -> tuple[str, str | None]:
    import re

    raw = (request.address or request.query or "").strip()
    zipcode = _normalize_zip(request.zipcode or raw)
    address = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", raw).rstrip(", ").strip()
    return address, zipcode


def _select_fields() -> list[str]:
    return [
        "ListingKey","UnparsedAddress","PostalCode","City","StateOrProvince","PropertyType","PropertySubType","StructureType",
        "StandardStatus","MlsStatus","ParcelNumber","CloseDate","ClosePrice","ModificationTimestamp","OnMarketDate","ListingContractDate",
        "OnMarketTimestamp","CurrentPrice","ListPrice","LivingArea","BuildingAreaTotal","LotSizeSquareFeet","LotSizeArea","LotSizeAcres",
        "Latitude","Longitude","BedroomsTotal","BathroomsTotalInteger","BathroomsFull","BathroomsHalf","BathroomsThreeQuarter","YearBuilt","YearBuiltEffective",
    ]


def _fetch_properties_for_radius(client: MLSClient, lat: float, lon: float, radius_miles: float, max_records: int = 5000) -> list[Property]:
    dlat = radius_miles / 69.0
    lon_divisor_raw = math.cos(math.radians(lat)) * 69.172
    lon_divisor = lon_divisor_raw if abs(lon_divisor_raw) > 1e-6 else 69.172
    dlon = radius_miles / lon_divisor
    filter_expression = f"Latitude ge {lat - dlat} and Latitude le {lat + dlat} and Longitude ge {lon - dlon} and Longitude le {lon + dlon}"
    properties = client.list_properties(filter=filter_expression, select=_select_fields(), orderby="OnMarketTimestamp desc, ModificationTimestamp desc, ListingKey desc", top=1000, max_records=max_records)
    return [prop for prop in properties if (haversine_miles(lat, lon, *(get_lat_lon(prop))) or 9999) <= radius_miles]


def _ensure_positive(value: float | None) -> float | None:
    return value if value is not None and value > 0 else None


def _map_comp_inputs(subject: Property, comps: list[Property], fallback_building: float, fallback_lot: float):
    sold: list[BaseCompInput] = []
    listed: list[BaseCompInput] = []
    off_market: list[BaseCompInput] = []
    renovated: list[RenovatedCompInput] = []
    subj_lat, subj_lon = get_lat_lon(subject)
    for comp in comps:
        building = _ensure_positive(building_sqft(comp)) or fallback_building
        lot = _ensure_positive(lot_sqft(comp)) or fallback_lot
        comp_lat, comp_lon = get_lat_lon(comp)
        distance = haversine_miles(subj_lat, subj_lon, comp_lat, comp_lon)
        base_kwargs = {
            "id": comp.ListingKey,
            "price": comp.ClosePrice or comp.CurrentPrice or comp.ListPrice or 0,
            "buildingSqft": building,
            "lotSqft": lot,
            "distanceMiles": distance,
        }
        status = ((comp.StandardStatus or comp.MlsStatus) or "").lower()
        if status in {"sold", "closed"} and comp.CloseDate:
            sold.append(BaseCompInput(**base_kwargs, eventDate=comp.CloseDate))
            off_market.append(BaseCompInput(**base_kwargs, eventDate=comp.CloseDate))
        else:
            listed.append(BaseCompInput(**base_kwargs, eventDate=comp.OnMarketDate or comp.ModificationTimestamp or datetime.utcnow().isoformat()))
        if comp.FlipAcquiredPrice and comp.FlipResalePrice and comp.FlipAcquiredDate and comp.FlipResaleDate:
            renovated.append(
                RenovatedCompInput(
                    **base_kwargs,
                    purchasePrice=comp.FlipAcquiredPrice,
                    purchaseDate=comp.FlipAcquiredDate,
                    resalePrice=comp.FlipResalePrice,
                    resaleDate=comp.FlipResaleDate,
                    eventDate=comp.FlipResaleDate,
                    price=comp.FlipAcquiredPrice,
                )
            )
    return sold, listed, off_market, renovated


def generate_property_summary(config: dict, request: PropertySummaryRequest, client: MLSClient | None = None) -> PropertySummaryResponse:
    client = client or TrestleClient(**config)
    address, zipcode = _parse_query(request)
    suggestions: list[dict] = []
    selected_suggestion: dict | None = None
    if request.listingKey:
        subject_property = client.property_by_listing_key(request.listingKey, select=_select_fields())
    else:
        if not zipcode or not address:
            raise ValueError("Provide a zipcode and address or a listingKey.")
        candidates = client.list_properties(filter=f"PostalCode eq '{zipcode}'", select=_select_fields(), orderby="ModificationTimestamp desc", top=1000, max_records=5000)
        suggestions = build_address_suggestions(candidates, address)
        selected_suggestion = suggestions[0] if suggestions else None
        subject_property = Property.model_validate(selected_suggestion["property"]) if selected_suggestion else None
    if not subject_property:
        raise ValueError("No matching property was found.")
    lat, lon = get_lat_lon(subject_property)
    if lat is None or lon is None:
        raise ValueError("Selected subject property does not include valid coordinates.")
    base_raw_properties = _fetch_properties_for_radius(client, lat, lon, request.radiusMiles)
    subject_for_pipeline = choose_canonical_subject(subject_property, base_raw_properties)
    properties_matching_types = [prop for prop in base_raw_properties if matches_selected_property_types(prop, request.propertyTypes)]
    properties_for_pipeline = base_raw_properties if any(prop.ListingKey == subject_for_pipeline.ListingKey for prop in base_raw_properties) else [subject_for_pipeline, *base_raw_properties]
    subject, results, metadata = comps_pipeline(
        properties_for_pipeline,
        subject_property.ListingKey,
        request.propertyTypes,
        request.minDays,
        request.maxDays,
        request.buildingDiffMax,
        request.lotDiffMax,
        request.maxComps,
        request.perTypeMax,
        request.fixFlipMinHoldDays,
        request.fixFlipMaxHoldDays,
        request.fixFlipMinRoi,
        request.includeFixFlip,
    )
    subject_snapshot = SubjectSnapshot(buildingSqft=_ensure_positive(building_sqft(subject)) or 0, lotSqft=_ensure_positive(lot_sqft(subject)) or 0, condition=request.propertyCondition)
    sold, listed, off_market, renovated = _map_comp_inputs(subject, results.recent.comps + results.active.comps + results.older.comps + results.fixFlip.comps, subject_snapshot.buildingSqft, subject_snapshot.lotSqft)
    service_area_ltv = get_service_area_ltv(subject.PostalCode)
    program_ltv = get_program_ltv(request.loanProgram)
    effective_ltv_max = min(program_ltv or 1, (service_area_ltv or {}).get("LTV", 1), 0.75)
    valuation = calculate_valuations(subject_snapshot, sold, listed, off_market, renovated, request.avmEstimates, effective_ltv_max)
    diagnostics = {
        "radiusMiles": request.radiusMiles,
        "propertyTypes": request.propertyTypes,
        "basePropertyCount": len({prop.ListingKey for prop in results.recent.comps + results.older.comps + results.active.comps}),
        "fixFlipExpansionEnabled": False,
        "fixFlipExpansionUsed": False,
        "fixFlipExpandedPropertyCount": 0,
        "expansionBasePropertyCount": len(properties_matching_types),
        "fixFlipThresholds": {"minHoldDays": request.fixFlipMinHoldDays, "maxHoldDays": request.fixFlipMaxHoldDays, "minRoi": request.fixFlipMinRoi},
        "fixFlipCount": results.fixFlip.count,
        "fixFlipDuplicateCount": metadata["fixFlipDuplicateCount"],
    }
    return PropertySummaryResponse(
        meta={"generatedAt": datetime.utcnow().isoformat(), "dataSource": "live_trestle"},
        query={"address": address, "zipcode": zipcode, "listingKey": request.listingKey},
        subject=subject,
        selectedSuggestion=selected_suggestion,
        suggestions=suggestions,
        rawProperties=base_raw_properties,
        rawPropertiesHitCap=len(base_raw_properties) >= 5000,
        results=results,
        diagnostics=diagnostics,  # type: ignore[arg-type]
        valuation=valuation,
        ltv={"loanProgram": request.loanProgram, "programLtv": program_ltv, "serviceAreaLtv": service_area_ltv, "effectiveLtvMax": effective_ltv_max},
        media=client.list_media_by_listing_key(subject.ListingKey),
    )
