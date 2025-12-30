"""HQS_PreInspection_Screener_v1

Goal
Predict whether a unit will likely pass HUD/HQS (and common PHA add-ons) using available
public info (listing text + photos + your answers), and produce a showing checklist.

This is a pre-screen, not a substitute for the real HQS inspection.

Outputs
- hqsStatus: PASS_LIKELY | FAIL_LIKELY | UNKNOWN | PASS_WITH_FIXES
- failReasons[], fixableItems[], unknownItems[], showingChecklist[]
- confidence: LOW | MED | HIGH

Determinism / policy notes
- No auto-fail on wood heat or hotplate-only by default (PHAs vary). Those remain UNKNOWN unless
  you explicitly encode them as hard evidence.
- leaksWaterDamage=yes is treated as a hard-fail signal in v1 (often maps to active leaks/rot).

Version: v1
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional


# ----------------------------
# Enums (JSON-schema friendly)
# ----------------------------


class Ternary(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class UnitType(str, Enum):
    APARTMENT = "apartment"
    HOUSE = "house"
    TOWNHOME = "townhome"
    MOBILE = "mobile"
    TINYHOME = "tinyhome"


class HeatSource(str, Enum):
    FORCED_AIR = "forced_air"
    BASEBOARD = "baseboard"
    WALL_HEATER = "wall_heater"
    MINI_SPLIT = "mini_split"
    WOOD = "wood"
    UNKNOWN = "unknown"


class HeatProvidedBy(str, Enum):
    LANDLORD = "landlord"
    TENANT = "tenant"
    UNKNOWN = "unknown"


class CookingAppliance(str, Enum):
    STOVE = "stove"
    HOTPLATE = "hotplate"
    NONE = "none"
    UNKNOWN = "unknown"


class WasherDryer(str, Enum):
    IN_UNIT = "in_unit"
    ON_SITE = "on_site"
    NONE = "none"
    UNKNOWN = "unknown"


class KitchenVent(str, Enum):
    HOOD_DUCTED = "hood_ducted"
    HOOD_RECIRCULATING = "hood_recirculating"
    NONE = "none"
    UNKNOWN = "unknown"


class HQSStatus(str, Enum):
    PASS_LIKELY = "PASS_LIKELY"
    FAIL_LIKELY = "FAIL_LIKELY"
    UNKNOWN = "UNKNOWN"
    PASS_WITH_FIXES = "PASS_WITH_FIXES"


class Confidence(str, Enum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"


# ----------------------------
# Data Model
# ----------------------------


@dataclass(frozen=True)
class Utilities:
    hasWorkingHeat: Ternary = Ternary.UNKNOWN
    heatSource: HeatSource = HeatSource.UNKNOWN
    heatProvidedBy: HeatProvidedBy = HeatProvidedBy.UNKNOWN
    hotWater: Ternary = Ternary.UNKNOWN
    cookingAppliance: CookingAppliance = CookingAppliance.UNKNOWN
    oven: Ternary = Ternary.UNKNOWN
    washerDryer: WasherDryer = WasherDryer.UNKNOWN


@dataclass(frozen=True)
class Ventilation:
    bathroomHasWindow: Ternary = Ternary.UNKNOWN
    bathroomHasFanDuctedOutside: Ternary = Ternary.UNKNOWN
    kitchenHasVent: KitchenVent = KitchenVent.UNKNOWN


@dataclass(frozen=True)
class Safety:
    smokeDetectors: Ternary = Ternary.UNKNOWN
    coDetectors: Ternary = Ternary.UNKNOWN
    gfciInKitchenBath: Ternary = Ternary.UNKNOWN
    handrailsOnStairs: Ternary = Ternary.UNKNOWN
    exteriorDoorDeadbolt: Ternary = Ternary.UNKNOWN
    egressWindowsInBedrooms: Ternary = Ternary.UNKNOWN


@dataclass(frozen=True)
class ConditionSignals:
    visibleMold: Ternary = Ternary.UNKNOWN
    pestSigns: Ternary = Ternary.UNKNOWN
    brokenWindows: Ternary = Ternary.UNKNOWN
    exposedWiring: Ternary = Ternary.UNKNOWN
    missingOutletCovers: Ternary = Ternary.UNKNOWN
    leaksWaterDamage: Ternary = Ternary.UNKNOWN


@dataclass(frozen=True)
class Unit:
    address: str
    unitType: UnitType
    listingUrl: Optional[str] = None

    bedroomsAdvertised: int = 0
    bathroomsAdvertised: Optional[float] = None
    sqft: Optional[int] = None
    yearBuilt: Optional[int] = None
    floorLevel: Optional[int] = None
    hasBasementBedroom: Optional[bool] = None

    utilities: Utilities = field(default_factory=Utilities)
    ventilation: Ventilation = field(default_factory=Ventilation)
    safety: Safety = field(default_factory=Safety)
    conditionSignals: ConditionSignals = field(default_factory=ConditionSignals)

    photosProvided: int = 0
    notesText: Optional[str] = None


@dataclass(frozen=True)
class HQSPreInspectionResult:
    hqsStatus: HQSStatus
    failReasons: List[str]
    unknownItems: List[str]
    fixableItems: List[str]
    showingChecklist: List[str]
    confidence: Confidence


# ----------------------------
# Reason Catalog
# ----------------------------


HARD_FAIL_REASONS = {
    "NO_HEAT": "No working heat (or clearly inadequate heat source)",
    "NO_HOT_WATER": "No hot water",
    "ELECTRICAL_HAZARD": "Major electrical hazard (exposed wiring / panel cover missing / scorching)",
    "NO_SMOKE_DETECTORS": "No smoke detector ability (clearly missing and landlord says no)",
    "NO_BEDROOM_EGRESS": "Bedroom without legal egress (esp. basement bedroom without egress)",
    "PLUMBING_FAILURE": "Sewage / active plumbing failure (toilet not functional / active leaks)",
    "SEVERE_MOLD_OR_PESTS": "Severe mold or infestation evidence",
}

FIXABLE_ITEMS = {
    "SMOKE_DETECTORS": "Missing/expired smoke detectors",
    "CO_DETECTORS": "Missing/expired CO detectors",
    "GFCI": "Missing/nonfunctional GFCI in kitchen/bath",
    "HANDRAILS": "Missing handrails on stairs (3+ steps typical)",
    "OUTLET_COVERS": "Loose/broken outlet covers",
    "BROKEN_WINDOW_LOCKS": "Broken window locks / windows don’t lock",
    "TRIP_HAZARDS": "Trip hazards (loose flooring, cords, uneven thresholds)",
    "PEELING_PAINT_PRE1978": "Peeling paint risk (pre-1978) – flag for lead-based paint rules",
    "BROKEN_WINDOWS": "Broken window panes / damaged glazing",
}

BASE_SHOWING_CHECKLIST = [
    "Heat & hot water: thermostat present and responds; heat source visible and operational; run hot water 60 seconds",
    "Electrical: test GFCI outlets (kitchen/bath); no exposed wiring; no scorched outlets; breaker panel cover present",
    "Safety: smoke detectors present; CO detector present if gas/attached garage; bedroom egress windows open",
    "Ventilation: bathroom window OR fan that exhausts outside; kitchen vent present (ducted preferred; recirc may be acceptable depending on PHA)",
    "Doors/windows: exterior doors latch + deadbolt; windows open/close/lock; no broken panes",
    "Plumbing: toilet flush; no leaks under sinks; shower drains; no sewage smell",
]

TINYHOME_SPECIAL_FLAGS = [
    "Tiny home/studio flag: sleeping loft without egress is a common fail zone",
    "Tiny home/studio flag: no permanent heat source is a common fail zone",
    "Tiny home/studio flag: hotplate-only kitchens may be PHA-dependent",
    "Tiny home/studio flag: bathroom ventilation missing is a common fail zone",
    "Tiny home/studio flag: RV-like electrical setups can fail inspection",
]


# ----------------------------
# Pure Evaluation Functions
# ----------------------------


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _photo_coverage_bucket(photos: int) -> str:
    if photos >= 18:
        return "HIGH"
    if photos >= 8:
        return "MED"
    return "LOW"


def _confidence(unit: Unit) -> Confidence:
    bucket = _photo_coverage_bucket(unit.photosProvided)
    has_notes = bool(unit.notesText and unit.notesText.strip())

    if unit.unitType == UnitType.TINYHOME:
        if bucket == "HIGH" and has_notes:
            return Confidence.MED
        return Confidence.LOW

    if bucket == "HIGH" and has_notes:
        return Confidence.HIGH
    if bucket in ("HIGH", "MED"):
        return Confidence.MED
    return Confidence.LOW


def _hard_fail_hits(unit: Unit) -> List[str]:
    hits: List[str] = []

    # Heat
    if unit.utilities.hasWorkingHeat == Ternary.NO:
        hits.append(HARD_FAIL_REASONS["NO_HEAT"])

    if unit.utilities.hotWater == Ternary.NO:
        hits.append(HARD_FAIL_REASONS["NO_HOT_WATER"])

    if unit.conditionSignals.exposedWiring == Ternary.YES:
        hits.append(HARD_FAIL_REASONS["ELECTRICAL_HAZARD"])

    if unit.safety.smokeDetectors == Ternary.NO:
        hits.append(HARD_FAIL_REASONS["NO_SMOKE_DETECTORS"])

    if unit.safety.egressWindowsInBedrooms == Ternary.NO:
        hits.append(HARD_FAIL_REASONS["NO_BEDROOM_EGRESS"])

    # Active leaks/water damage: treated as a hard-fail signal in v1.
    if unit.conditionSignals.leaksWaterDamage == Ternary.YES:
        hits.append(HARD_FAIL_REASONS["PLUMBING_FAILURE"])

    if unit.conditionSignals.visibleMold == Ternary.YES or unit.conditionSignals.pestSigns == Ternary.YES:
        hits.append(HARD_FAIL_REASONS["SEVERE_MOLD_OR_PESTS"])

    return _dedupe_preserve_order(hits)


def _fixable_hits(unit: Unit) -> List[str]:
    fixes: List[str] = []

    # Note: smokeDetectors=NO is treated as hard-fail (landlord says no / clearly missing).
    # smokeDetectors=UNKNOWN becomes a showing verification item.

    if unit.safety.coDetectors == Ternary.NO:
        fixes.append(FIXABLE_ITEMS["CO_DETECTORS"])

    if unit.safety.gfciInKitchenBath == Ternary.NO:
        fixes.append(FIXABLE_ITEMS["GFCI"])

    if unit.safety.handrailsOnStairs == Ternary.NO:
        fixes.append(FIXABLE_ITEMS["HANDRAILS"])

    if unit.conditionSignals.missingOutletCovers == Ternary.YES:
        fixes.append(FIXABLE_ITEMS["OUTLET_COVERS"])

    if unit.conditionSignals.brokenWindows == Ternary.YES:
        fixes.append(FIXABLE_ITEMS["BROKEN_WINDOWS"])

    # Pre-1978 paint risk: flag-only.
    if unit.yearBuilt is not None and unit.yearBuilt < 1978:
        fixes.append(FIXABLE_ITEMS["PEELING_PAINT_PRE1978"])

    return _dedupe_preserve_order(fixes)


def _unknown_items(unit: Unit) -> List[str]:
    unknowns: List[str] = []

    if unit.utilities.hotWater == Ternary.UNKNOWN:
        unknowns.append("Verify hot water (run 60 seconds)")

    if unit.utilities.hasWorkingHeat == Ternary.UNKNOWN:
        unknowns.append("Verify working heat (thermostat responds; heat runs)")
    if unit.utilities.heatSource == HeatSource.UNKNOWN:
        unknowns.append("Verify heat source type")

    if unit.safety.gfciInKitchenBath == Ternary.UNKNOWN:
        unknowns.append("Verify GFCI presence/function in kitchen/bath")

    if unit.conditionSignals.exposedWiring == Ternary.UNKNOWN:
        unknowns.append("Verify no exposed wiring/scorched outlets/panel cover")

    if unit.safety.smokeDetectors == Ternary.UNKNOWN:
        unknowns.append("Verify smoke detectors present and placed correctly")

    if unit.safety.coDetectors == Ternary.UNKNOWN:
        unknowns.append("Verify CO detector if fuel-burning appliances or attached garage")

    if unit.safety.egressWindowsInBedrooms == Ternary.UNKNOWN:
        unknowns.append("Verify bedroom egress windows (open/close; correct size/location)")

    if unit.hasBasementBedroom is True and unit.safety.egressWindowsInBedrooms == Ternary.UNKNOWN:
        unknowns.append("Basement bedroom indicated: confirm legal egress window")

    if unit.ventilation.bathroomHasWindow == Ternary.UNKNOWN and unit.ventilation.bathroomHasFanDuctedOutside == Ternary.UNKNOWN:
        unknowns.append("Verify bathroom ventilation (window or fan ducted outside)")

    if unit.ventilation.kitchenHasVent == KitchenVent.UNKNOWN:
        unknowns.append("Verify kitchen ventilation (ducted/recirc/none)")

    if unit.safety.exteriorDoorDeadbolt == Ternary.UNKNOWN:
        unknowns.append("Verify exterior doors latch + deadbolt")

    if unit.conditionSignals.leaksWaterDamage == Ternary.UNKNOWN:
        unknowns.append("Verify no active leaks/water damage under sinks and around fixtures")

    if unit.conditionSignals.visibleMold == Ternary.UNKNOWN:
        unknowns.append("Verify no visible mold/mildew odor")

    if unit.conditionSignals.pestSigns == Ternary.UNKNOWN:
        unknowns.append("Verify no pest signs (droppings, traps, dead insects)")

    return _dedupe_preserve_order(unknowns)


def _showing_checklist(unit: Unit, unknown_items: List[str]) -> List[str]:
    checklist: List[str] = []
    checklist.extend([f"PRIORITY VERIFY: {u}" for u in unknown_items])
    checklist.extend(BASE_SHOWING_CHECKLIST)

    if unit.unitType == UnitType.TINYHOME:
        checklist.extend(TINYHOME_SPECIAL_FLAGS)

    return _dedupe_preserve_order(checklist)


def evaluate_hqs_preinspection(unit: Unit) -> HQSPreInspectionResult:
    hard_fails = _hard_fail_hits(unit)
    fixes = _fixable_hits(unit)
    unknowns = _unknown_items(unit)
    conf = _confidence(unit)

    if hard_fails:
        return HQSPreInspectionResult(
            hqsStatus=HQSStatus.FAIL_LIKELY,
            failReasons=hard_fails,
            unknownItems=unknowns,
            fixableItems=fixes,
            showingChecklist=_showing_checklist(unit, unknowns),
            confidence=conf,
        )

    if fixes:
        return HQSPreInspectionResult(
            hqsStatus=HQSStatus.PASS_WITH_FIXES,
            failReasons=[],
            unknownItems=unknowns,
            fixableItems=fixes,
            showingChecklist=_showing_checklist(unit, unknowns),
            confidence=conf,
        )

    # No hard fails, no fixables.
    # If any unknowns remain and confidence is not HIGH, mark UNKNOWN.
    if unknowns and conf in (Confidence.LOW, Confidence.MED):
        status = HQSStatus.UNKNOWN
    else:
        status = HQSStatus.PASS_LIKELY

    return HQSPreInspectionResult(
        hqsStatus=status,
        failReasons=[],
        unknownItems=unknowns,
        fixableItems=[],
        showingChecklist=_showing_checklist(unit, unknowns),
        confidence=conf,
    )


# ----------------------------
# JSON helpers
# ----------------------------


def unit_to_dict(unit: Unit) -> dict:
    return asdict(unit)


def result_to_dict(result: HQSPreInspectionResult) -> dict:
    return asdict(result)


# ----------------------------
# Minimal demo
# ----------------------------


def _demo() -> None:
    unit = Unit(
        address="123 Example St",
        unitType=UnitType.APARTMENT,
        listingUrl=None,
        bedroomsAdvertised=2,
        bathroomsAdvertised=1.0,
        sqft=900,
        yearBuilt=1975,
        floorLevel=2,
        hasBasementBedroom=False,
        utilities=Utilities(
            hasWorkingHeat=Ternary.UNKNOWN,
            heatSource=HeatSource.UNKNOWN,
            heatProvidedBy=HeatProvidedBy.UNKNOWN,
            hotWater=Ternary.UNKNOWN,
            cookingAppliance=CookingAppliance.STOVE,
            oven=Ternary.YES,
            washerDryer=WasherDryer.ON_SITE,
        ),
        ventilation=Ventilation(
            bathroomHasWindow=Ternary.UNKNOWN,
            bathroomHasFanDuctedOutside=Ternary.UNKNOWN,
            kitchenHasVent=KitchenVent.UNKNOWN,
        ),
        safety=Safety(
            smokeDetectors=Ternary.UNKNOWN,
            coDetectors=Ternary.UNKNOWN,
            gfciInKitchenBath=Ternary.UNKNOWN,
            handrailsOnStairs=Ternary.UNKNOWN,
            exteriorDoorDeadbolt=Ternary.UNKNOWN,
            egressWindowsInBedrooms=Ternary.UNKNOWN,
        ),
        conditionSignals=ConditionSignals(
            visibleMold=Ternary.UNKNOWN,
            pestSigns=Ternary.UNKNOWN,
            brokenWindows=Ternary.UNKNOWN,
            exposedWiring=Ternary.UNKNOWN,
            missingOutletCovers=Ternary.UNKNOWN,
            leaksWaterDamage=Ternary.UNKNOWN,
        ),
        photosProvided=6,
        notesText="Nice unit, limited photos.",
    )

    result = evaluate_hqs_preinspection(unit)
    print("hqsStatus:", result.hqsStatus.value)
    print("confidence:", result.confidence.value)
    print("failReasons:")
    for x in result.failReasons:
        print(" -", x)
    print("fixableItems:")
    for x in result.fixableItems:
        print(" -", x)
    print("unknownItems:")
    for x in result.unknownItems[:12]:
        print(" -", x)
    print("showingChecklist:")
    for x in result.showingChecklist[:10]:
        print(" -", x)


if __name__ == "__main__":
    _demo()
