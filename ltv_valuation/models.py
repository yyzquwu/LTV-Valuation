from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


PropertyCondition = Literal[
    "New Construction",
    "Normal Condition",
    "Below Average Condition",
    "Unlivable Condition",
    "Developed Land",
]


class Property(BaseModel):
    ListingKey: str
    UnparsedAddress: str
    PostalCode: str | None = None
    City: str | None = None
    StateOrProvince: str | None = None
    PropertyType: str | None = None
    PropertySubType: str | None = None
    StructureType: str | None = None
    StandardStatus: str | None = None
    MlsStatus: str | None = None
    ParcelNumber: str | None = None
    CloseDate: str | None = None
    ClosePrice: float | None = None
    CurrentPrice: float | None = None
    ListPrice: float | None = None
    OnMarketDate: str | None = None
    OnMarketTimestamp: str | None = None
    ModificationTimestamp: str | None = None
    ListingContractDate: str | None = None
    LivingArea: float | None = None
    BuildingAreaTotal: float | None = None
    LotSizeSquareFeet: float | None = None
    LotSizeArea: float | None = None
    LotSizeAcres: float | None = None
    Latitude: float | None = None
    Longitude: float | None = None
    GeoLatitude: float | None = None
    GeoLongitude: float | None = None
    LatitudeDecimal: float | None = None
    LongitudeDecimal: float | None = None
    BedroomsTotal: int | None = None
    BathroomsTotalInteger: float | None = None
    BathroomsFull: float | None = None
    BathroomsHalf: float | None = None
    BathroomsThreeQuarter: float | None = None
    YearBuilt: int | None = None
    YearBuiltEffective: int | None = None
    FlipAcquiredDate: str | None = None
    FlipAcquiredPrice: float | None = None
    FlipResaleDate: str | None = None
    FlipResalePrice: float | None = None
    FlipHoldDays: int | None = None
    FlipRoiPercent: float | None = None
    FixFlipDuplicate: bool | None = None


class PropertyWithDeltas(Property):
    delta_building_sqft: str | None = Field(default=None, alias="ΔBuildingSqft")
    delta_lot_sqft: str | None = Field(default=None, alias="ΔLotSqft")
    delta_distance: float | None = Field(default=None, alias="ΔDist")
    SoldPrice: float | None = None
    LotSqft: float | None = None


class CompSet(BaseModel):
    name: str
    comps: list[Property]
    df_preview: list[PropertyWithDeltas]
    avg_price: float | None = None
    count: int


class CompsResult(BaseModel):
    recent: CompSet
    older: CompSet
    active: CompSet
    fixFlip: CompSet


class SearchDiagnostics(BaseModel):
    radiusMiles: float
    propertyTypes: list[str]
    basePropertyCount: int
    fixFlipExpansionEnabled: bool
    fixFlipExpansionUsed: bool
    fixFlipExpandedPropertyCount: int
    expansionBasePropertyCount: int
    fixFlipThresholds: dict[str, float | int]
    fixFlipCount: int
    fixFlipDuplicateCount: int


class BaseCompInput(BaseModel):
    id: str | None = None
    price: float
    buildingSqft: float
    lotSqft: float
    distanceMiles: float | None = None
    eventDate: str | datetime | date


class RenovatedCompInput(BaseCompInput):
    purchasePrice: float
    purchaseDate: str | datetime | date
    resalePrice: float
    resaleDate: str | datetime | date


class SubjectSnapshot(BaseModel):
    buildingSqft: float
    lotSqft: float
    condition: PropertyCondition


class DiscountFactorResult(BaseModel):
    discountFactor: float
    df1: float
    df2: float
    usedFallback: bool


class CompWeightComponents(BaseModel):
    distance: float
    time: float
    buildingSize: float
    lotSize: float
    combined: float


class CompComputation(BaseModel):
    comp: BaseCompInput
    weightedEstimatedValue: float | None = None
    adjustedAmount: float | None = None
    weights: CompWeightComponents
    buildingSqftDiff: float | None = None
    lotSqftDiff: float | None = None
    daysSinceEvent: int | None = None


class CategoryComputation(BaseModel):
    average: float | None = None
    combinedWeight: float
    entries: list[CompComputation]


class RenovatedCategoryComputation(BaseModel):
    average: float | None = None
    entries: list[CompComputation]


class ValuationBreakdown(BaseModel):
    discountFactor: DiscountFactorResult
    sold: CategoryComputation
    listed: CategoryComputation
    offMarket: CategoryComputation
    renovated: RenovatedCategoryComputation
    asIsValue: float | None = None
    initialEstimatedValue: float | None = None
    averageEstimatedValue: float | None = None
    afterRepairValue: float | None = None
    finalEstimatedValue: float | None = None


class PropertySummaryRequest(BaseModel):
    query: str | None = None
    address: str | None = None
    zipcode: str | None = None
    listingKey: str | None = None
    radiusMiles: float = 3
    propertyTypes: list[str] = []
    minDays: int = 0
    maxDays: int = 365
    buildingDiffMax: float = 500
    lotDiffMax: float = 1000
    maxComps: int | None = None
    perTypeMax: int | None = None
    fixFlipMinHoldDays: int = 30
    fixFlipMaxHoldDays: int = 365
    fixFlipMinRoi: float = 0.1
    includeFixFlip: bool = True
    avmEstimates: list[float] = []
    loanProgram: str = "Standard"
    propertyCondition: PropertyCondition = "Normal Condition"


class PropertySummaryResponse(BaseModel):
    meta: dict[str, str]
    query: dict[str, str | None]
    subject: Property
    selectedSuggestion: dict | None = None
    suggestions: list[dict] = []
    rawProperties: list[Property]
    rawPropertiesHitCap: bool
    results: CompsResult
    diagnostics: SearchDiagnostics
    valuation: ValuationBreakdown
    ltv: dict
    media: list[dict] | None = None
