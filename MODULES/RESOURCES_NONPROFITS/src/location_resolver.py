"""
location_resolver.py
SQUAD BAT — Geographic scope resolver for resource data shards.

Resolves which data shards to load based on a geographic query.
Resolution order: region (most specific) → state → national (US) → global fallback.

Scope hierarchy:
  DATA/US/{STATE}/{region}.json   — regional shard (e.g. western_slope)
  DATA/US/{STATE}.json            — state shard (e.g. CO.json)
  DATA/US.json                    — national shard
  DATA/global.json                — global fallback (future use)

Usage:
    from location_resolver import resolve_shards
    paths = resolve_shards(state="CO", region="western_slope")
    # Returns list of existing shard paths, most-specific first
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional


def _module_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_segment(s: str) -> str:
    """Normalize a geographic string to a safe filename segment."""
    s = s.strip().upper() if len(s) <= 3 else s.strip().lower()
    # Allow alphanumeric, underscore, hyphen only
    s = re.sub(r"[^a-zA-Z0-9_\-]", "_", s)
    return s


def resolve_shards(
    *,
    country: str = "US",
    state: Optional[str] = None,
    region: Optional[str] = None,
) -> List[str]:
    """
    Returns ordered list of existing shard paths for the given geographic scope.
    Most specific first (regional → state → national).
    Caller passes all returned paths to load_registry() for merged results.

    Args:
        country:  ISO country code, default "US"
        state:    State/province code (e.g. "CO", "CA", "TX")
        region:   Sub-state region slug (e.g. "western_slope", "front_range")

    Returns:
        List of absolute path strings for shards that exist on disk.
        Empty list if no shards found for the scope.
    """
    data_root = _module_root() / "DATA"
    country_seg = _safe_segment(country) if country else "US"

    candidates: List[Path] = []

    # Level 1: regional shard (most specific)
    if state and region:
        state_seg = _safe_segment(state)
        region_seg = _safe_segment(region)
        candidates.append(data_root / country_seg / state_seg / f"{region_seg}.json")

    # Level 2: state shard
    if state:
        state_seg = _safe_segment(state)
        candidates.append(data_root / country_seg / f"{state_seg}.json")

    # Level 3: national shard
    candidates.append(data_root / f"{country_seg}.json")

    # Level 4: global fallback
    candidates.append(data_root / "global.json")

    return [str(p) for p in candidates if p.exists()]


def resolve_shards_for_county(
    *,
    country: str = "US",
    state: Optional[str] = None,
    county: Optional[str] = None,
) -> List[str]:
    """
    Variant for county-level queries. Maps known counties to their regional shard.
    Falls back to state → national if no regional mapping exists.

    The county_to_region map is the single place to add new region coverage
    as the program expands. Add entries here when a new regional shard is created.
    """
    county_to_region: dict[str, dict[str, str]] = {
        "US": {
            # Colorado — Western Slope
            "Mesa": "western_slope",
            "Garfield": "western_slope",
            "Delta": "western_slope",
            "Montrose": "western_slope",
            "San Miguel": "western_slope",
            "Ouray": "western_slope",
            "Gunnison": "western_slope",
            "Rio Blanco": "western_slope",
            "Moffat": "western_slope",
            "Grand": "western_slope",
            "Eagle": "western_slope",
            "Pitkin": "western_slope",
            # Add Front Range counties → "front_range" when that shard exists
            # Add San Luis Valley counties → "san_luis_valley" when that shard exists
        }
    }

    region = None
    if state and county:
        state_map = county_to_region.get(country, {})
        region = state_map.get(county)

    return resolve_shards(country=country, state=state, region=region)


def list_available_shards(country: str = "US") -> List[str]:
    """
    Returns all existing shard paths under the given country.
    Useful for admin tooling — shows what data is currently loaded.
    """
    data_root = _module_root() / "DATA" / _safe_segment(country)
    if not data_root.exists():
        return []
    return sorted(str(p) for p in data_root.rglob("*.json"))
