from ltv_valuation.models import BaseCompInput, SubjectSnapshot
from ltv_valuation.valuation import calculate_valuations


def test_calculate_valuations_returns_point_estimate() -> None:
    result = calculate_valuations(
        subject=SubjectSnapshot(buildingSqft=2000, lotSqft=5000, condition="Normal Condition"),
        sold=[BaseCompInput(price=500000, buildingSqft=1900, lotSqft=4800, eventDate="2025-01-01")],
        listed=[BaseCompInput(price=520000, buildingSqft=2050, lotSqft=5100, eventDate="2025-02-01")],
        off_market=[BaseCompInput(price=510000, buildingSqft=1950, lotSqft=4900, eventDate="2025-03-01")],
        renovated=[],
        avm_estimates=[505000, 515000],
    )
    assert result.finalEstimatedValue is not None
    assert result.discountFactor.discountFactor > 0.74
