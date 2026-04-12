from __future__ import annotations

import math
from datetime import UTC, date, datetime

from .models import (
    BaseCompInput,
    CategoryComputation,
    CompComputation,
    CompWeightComponents,
    DiscountFactorResult,
    RenovatedCategoryComputation,
    RenovatedCompInput,
    SubjectSnapshot,
    ValuationBreakdown,
)


COMP_WEIGHTS = {"sold": 0.6, "listed": 0.25, "offMarket": 0.15}
DECAY_PARAMS = {"alpha": 0.231, "theta": 1.416, "buildingSizePenalty": 0.00139, "lotSizePenalty": 0.000693}
POWER_EXPONENTS = {"distance": 0.25, "time": 0.2, "buildingSize": 0.4, "lotSize": 0.15}
CONDITION_DISCOUNTS = {
    "New Construction": {"primary": 0.02, "fallback": 0.05},
    "Normal Condition": {"primary": 0.03, "fallback": 0.05},
    "Below Average Condition": {"primary": 0.05, "fallback": 0.075},
    "Unlivable Condition": {"primary": 0.1, "fallback": 0.15},
    "Developed Land": {"primary": 0.1, "fallback": 0.15},
}


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return (ordered[mid - 1] + ordered[mid]) / 2 if len(ordered) % 2 == 0 else ordered[mid]


def _trimmed_mean(values: list[float], trim_fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    trim_count = math.floor(len(values) * trim_fraction)
    trimmed = ordered[trim_count : len(values) - trim_count]
    return _mean(trimmed or ordered)


def _std_dev(values: list[float], reference_mean: float | None = None) -> float | None:
    if not values:
        return None
    avg = reference_mean if reference_mean is not None else _mean(values)
    if avg is None:
        return None
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _to_datetime(value: str | datetime | date) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        try:
            return datetime.fromisoformat(f"{value}T00:00:00+00:00")
        except ValueError:
            return None


def calculate_discount_factor(property_condition: str, avm_estimates: list[float], comp_prices: list[float], k_range: float = 0.1) -> DiscountFactorResult:
    valid_avms = [value for value in avm_estimates if isinstance(value, (int, float)) and math.isfinite(value)]
    valid_prices = [value for value in comp_prices if isinstance(value, (int, float)) and math.isfinite(value)]
    measures: list[float] = []
    used_fallback = False
    if valid_avms:
        for measure in (_mean(valid_avms), _trimmed_mean(valid_avms, 0.1), _median(valid_avms)):
            if measure is not None:
                measures.append(measure)
    if not measures and valid_prices:
        comp_mean = _mean(valid_prices)
        if comp_mean is not None:
            measures.append(comp_mean)
    average = _mean(measures)
    deviation = _std_dev(valid_avms + valid_prices, _mean(valid_avms + valid_prices)) if (valid_avms or valid_prices) else None
    df1 = ((deviation / average) * k_range) if (average and deviation and average != 0) else 0
    if average is None or deviation is None:
        used_fallback = True
    df2 = CONDITION_DISCOUNTS[property_condition]["primary"]
    discount = 1 - (df1 + df2)
    if not math.isfinite(discount):
        discount = 1 - CONDITION_DISCOUNTS[property_condition]["fallback"]
        used_fallback = True
    discount = min(1.0, max(0.75, discount))
    return DiscountFactorResult(discountFactor=discount, df1=df1, df2=df2, usedFallback=used_fallback)


def _average_price_per_sqft(sold: list[BaseCompInput], listed: list[BaseCompInput], off_market: list[BaseCompInput], renovated: list[RenovatedCompInput]) -> tuple[float | None, float | None]:
    price_values: list[float] = []
    building_values: list[float] = []
    lot_values: list[float] = []
    for comp in sold + listed + off_market:
        price_values.append(comp.price)
        building_values.append(comp.buildingSqft)
        lot_values.append(comp.lotSqft)
    for comp in renovated:
        price_values.append(comp.purchasePrice)
        building_values.append(comp.buildingSqft)
        lot_values.append(comp.lotSqft)
    avg_price = _mean(price_values)
    avg_building = _mean(building_values)
    avg_lot = _mean(lot_values)
    return ((avg_price / avg_building) if avg_price and avg_building else None, (avg_price / avg_lot) if avg_price and avg_lot else None)


def _adjust_comp(comp: BaseCompInput, subject: SubjectSnapshot, avg_building: float | None, avg_lot: float | None):
    building_diff = subject.buildingSqft - comp.buildingSqft
    lot_diff = subject.lotSqft - comp.lotSqft
    price_per_building = comp.price / comp.buildingSqft if comp.buildingSqft else None
    price_per_lot = comp.price / comp.lotSqft if comp.lotSqft else None
    ratio_denom = (price_per_building or 0) + (price_per_lot or 0)
    building_ratio = (price_per_building / ratio_denom) if ratio_denom and price_per_building is not None else 0.5
    lot_ratio = 1 - building_ratio
    building_adjustment = (avg_building or 0) * building_diff
    lot_adjustment = (avg_lot or 0) * lot_diff * lot_ratio
    weighted = comp.price + building_ratio * building_adjustment + lot_ratio * lot_adjustment
    return weighted, building_diff, lot_diff


def _weight_component(distance_miles: float | None, days_since_event: int | None, building_diff: float | None, lot_diff: float | None, use_power: bool) -> CompWeightComponents:
    distance_base = math.exp(-DECAY_PARAMS["alpha"] * max(distance_miles or 0, 0))
    time_base = math.exp(-(DECAY_PARAMS["theta"] * max(days_since_event or 0, 0)) / 365)
    distance = distance_base ** POWER_EXPONENTS["distance"] if use_power else distance_base
    time = time_base ** POWER_EXPONENTS["time"] if use_power else time_base
    building_size = (min(1, math.exp(-DECAY_PARAMS["buildingSizePenalty"] * abs(building_diff or 0))) ** POWER_EXPONENTS["buildingSize"]) if building_diff is not None else 1
    lot_size = (min(1, math.exp(-DECAY_PARAMS["lotSizePenalty"] * abs(lot_diff or 0))) ** POWER_EXPONENTS["lotSize"]) if lot_diff is not None else 1
    return CompWeightComponents(distance=distance, time=time, buildingSize=building_size, lotSize=lot_size, combined=distance * time * building_size * lot_size)


def _compute_category(comps: list[BaseCompInput], subject: SubjectSnapshot, avg_building: float | None, avg_lot: float | None, reference_date: datetime, use_power: bool) -> CategoryComputation:
    entries: list[CompComputation] = []
    for comp in comps:
        event = _to_datetime(comp.eventDate)
        days = (reference_date - event).days if event else None
        weighted, building_diff, lot_diff = _adjust_comp(comp, subject, avg_building, avg_lot)
        weights = _weight_component(comp.distanceMiles, days, building_diff, lot_diff, use_power)
        adjusted_amount = weighted * weights.combined if weighted is not None else None
        entries.append(
            CompComputation(
                comp=comp,
                weightedEstimatedValue=weighted,
                adjustedAmount=adjusted_amount,
                weights=weights,
                buildingSqftDiff=building_diff,
                lotSqftDiff=lot_diff,
                daysSinceEvent=days,
            )
        )
    numerator = sum(entry.adjustedAmount or 0 for entry in entries)
    denominator = sum(entry.weights.combined for entry in entries)
    average = numerator / denominator if denominator > 0 else _mean([entry.weightedEstimatedValue for entry in entries if entry.weightedEstimatedValue is not None])
    return CategoryComputation(average=average, combinedWeight=denominator, entries=entries)


def _compute_renovated_category(comps: list[RenovatedCompInput], subject: SubjectSnapshot, avg_building: float | None, avg_lot: float | None, reference_date: datetime) -> RenovatedCategoryComputation:
    entries: list[CompComputation] = []
    for comp in comps:
        resale_date = _to_datetime(comp.resaleDate)
        days = (reference_date - resale_date).days if resale_date else None
        renovation_value = ((comp.resalePrice - comp.purchasePrice) * (subject.buildingSqft / comp.buildingSqft)) if comp.buildingSqft else 0
        base = BaseCompInput(id=comp.id, price=comp.purchasePrice, buildingSqft=comp.buildingSqft, lotSqft=comp.lotSqft, distanceMiles=comp.distanceMiles, eventDate=comp.resaleDate)
        weighted, building_diff, lot_diff = _adjust_comp(base, subject, avg_building, avg_lot)
        weighted_value = (weighted + renovation_value) if weighted is not None else None
        weights = _weight_component(comp.distanceMiles, days, building_diff, lot_diff, False)
        weights.combined = weights.distance * weights.time
        entries.append(
            CompComputation(
                comp=base,
                weightedEstimatedValue=weighted_value,
                adjustedAmount=(weighted_value * weights.combined) if weighted_value is not None else None,
                weights=weights,
                buildingSqftDiff=building_diff,
                lotSqftDiff=lot_diff,
                daysSinceEvent=days,
            )
        )
    return RenovatedCategoryComputation(average=_mean([entry.weightedEstimatedValue for entry in entries if entry.weightedEstimatedValue is not None]), entries=entries)


def calculate_valuations(subject: SubjectSnapshot, sold: list[BaseCompInput], listed: list[BaseCompInput], off_market: list[BaseCompInput], renovated: list[RenovatedCompInput], avm_estimates: list[float] | None = None, ltv_area_max: float = 0.75, reference_date: datetime | None = None) -> ValuationBreakdown:
    avm_estimates = avm_estimates or []
    reference_date = reference_date or datetime.now(UTC)
    avg_building, avg_lot = _average_price_per_sqft(sold, listed, off_market, renovated)
    sold_category = _compute_category(sold, subject, avg_building, avg_lot, reference_date, True)
    listed_category = _compute_category(listed, subject, avg_building, avg_lot, reference_date, True)
    off_market_category = _compute_category(off_market, subject, avg_building, avg_lot, reference_date, False)
    renovated_category = _compute_renovated_category(renovated, subject, avg_building, avg_lot, reference_date)
    discount = calculate_discount_factor(subject.condition, avm_estimates, [comp.price for comp in sold + listed + off_market] + [comp.purchasePrice for comp in renovated])
    category_values: list[float] = []
    sold_contrib = COMP_WEIGHTS["sold"] * sold_category.average if sold_category.average is not None else None
    if sold_category.average is not None:
        category_values.append(sold_category.average)
    listed_adjusted = listed_category.average * discount.discountFactor if listed_category.average is not None else None
    if listed_adjusted is not None:
        category_values.append(listed_adjusted)
    off_adjusted = off_market_category.average * discount.discountFactor if off_market_category.average is not None else None
    if off_adjusted is not None:
        category_values.append(off_adjusted)
    as_is = sold_contrib + COMP_WEIGHTS["listed"] * listed_adjusted + COMP_WEIGHTS["offMarket"] * off_adjusted if sold_contrib is not None and listed_adjusted is not None and off_adjusted is not None else _mean(category_values)
    avm_avg = _mean(avm_estimates)
    initial = avm_avg * discount.discountFactor if avm_avg is not None else None
    average_est = ((initial + as_is) / 2) if (initial is not None and as_is is not None) else (initial if initial is not None else as_is)
    after_repair = renovated_category.average * discount.discountFactor if renovated_category.average is not None else None
    final = ((average_est + after_repair * ltv_area_max) / 2) if (average_est is not None and after_repair is not None) else average_est
    return ValuationBreakdown(
        discountFactor=discount,
        sold=sold_category,
        listed=listed_category,
        offMarket=off_market_category,
        renovated=renovated_category,
        asIsValue=as_is,
        initialEstimatedValue=initial,
        averageEstimatedValue=average_est,
        afterRepairValue=after_repair,
        finalEstimatedValue=final,
    )
