from ltv_valuation.models import Property, PropertySummaryRequest
from ltv_valuation.property_summary import generate_property_summary


class MockClient:
    def __init__(self) -> None:
        self.subject = Property(
            ListingKey="subj-1",
            UnparsedAddress="123 Main St, Anaheim, CA 92801",
            PostalCode="92801",
            City="Anaheim",
            StateOrProvince="CA",
            PropertyType="Residential",
            StandardStatus="Active",
            LivingArea=2000,
            LotSizeSquareFeet=5000,
            Latitude=33.84,
            Longitude=-117.91,
            ModificationTimestamp="2026-04-01T00:00:00Z",
        )
        self.props = [
            self.subject,
            Property(ListingKey="sold-1", UnparsedAddress="125 Main St, Anaheim, CA 92801", PostalCode="92801", City="Anaheim", StateOrProvince="CA", PropertyType="Residential", StandardStatus="Sold", CloseDate="2026-03-01T00:00:00Z", ClosePrice=750000, LivingArea=1950, LotSizeSquareFeet=4800, Latitude=33.8405, Longitude=-117.9095),
            Property(ListingKey="active-1", UnparsedAddress="127 Main St, Anaheim, CA 92801", PostalCode="92801", City="Anaheim", StateOrProvince="CA", PropertyType="Residential", StandardStatus="Active", CurrentPrice=770000, LivingArea=2050, LotSizeSquareFeet=5100, OnMarketDate="2026-03-10T00:00:00Z", Latitude=33.841, Longitude=-117.909),
            Property(ListingKey="off-1", UnparsedAddress="129 Main St, Anaheim, CA 92801", PostalCode="92801", City="Anaheim", StateOrProvince="CA", PropertyType="Residential", StandardStatus="Closed", CloseDate="2026-02-20T00:00:00Z", ClosePrice=740000, LivingArea=1980, LotSizeSquareFeet=4900, Latitude=33.8415, Longitude=-117.9085),
        ]

    def list_properties(self, **kwargs):
        return self.props

    def property_by_listing_key(self, listing_key: str, select=None):
        return self.subject if listing_key == self.subject.ListingKey else None

    def list_media_by_listing_key(self, listing_key: str):
        return [{"mediaUrl": "https://example.com/photo.jpg", "order": 1}] if listing_key == self.subject.ListingKey else []


def test_generate_property_summary() -> None:
    summary = generate_property_summary(
        {"base_uri": "", "token_url": "", "client_id": "", "client_secret": "", "scope": "api"},
        PropertySummaryRequest(listingKey="subj-1", loanProgram="Standard"),
        client=MockClient(),
    )
    assert summary.subject.ListingKey == "subj-1"
    assert summary.results.recent.count >= 1
    assert summary.valuation.finalEstimatedValue is not None
