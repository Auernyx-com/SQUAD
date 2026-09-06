"""
local_resources.py
SQUAD BAT — Shared local-resource lookup for Division routers.

Why this exists
----------------
Confirmed via a top-down audit: none of the 8 division routers, and
nothing in AGENTS/, ever calls MODULES/RESOURCES_NONPROFITS/src/
nonprofit_search.py. The real, curated resource database (Mesa County
VSO, Western Slope regional shards, Puget Sound WA, etc.) exists,
is well-tested, and is never queried by anything a veteran's intake
actually reaches. Every division's guidance is static, hardcoded
national-line text.

This module is the single, shared integration point every division
calls into, instead of each one reimplementing its own version of
"find local data for this state/county." See README's own service
taxonomy (MODULES/RESOURCES_NONPROFITS/GOVERNANCE/
auernyx.nonprofit.scope.json) for the controlled service_tags vocabulary
each caller picks from.

Design decisions (settled in conversation before writing this):
  - Verified-data-only is already guaranteed by nonprofit_search.
    load_registry() silently excludes any record still carrying an
    unresolved verify_before_production marker before it ever reaches
    search() -- this module doesn't re-implement that check, it inherits
    it for free by always going through load_registry() first.
  - Fails safe, never raises: any error (missing file, malformed JSON,
    bad input) returns [] so a data problem in one region can never take
    a whole Division down for that veteran. The existing hardcoded
    national-line fallback in each router's own code still applies --
    this only ever ADDS to it, never replaces or blocks it.
  - Crisis/self-harm widening is additive, not exclusionary: passing
    crisis_or_self_harm=True widens/prioritizes the mental-health branch
    of a search, it never suppresses or gates out other, unrelated local
    resources from also being found. Matches this project's existing
    "crisis is always additive" design law.
  - State-scoped by construction, not just at match time: only the
    given state's own shard files are ever loaded into the candidate
    pool. A same-named place in a different state (Glenwood Springs, CO
    vs Glenwood Springs, IL) cannot cross-contaminate, because the other
    state's data is never even read.
  - County matching tries an exact (case-insensitive, "county"/"co."
    suffix-stripped) match first; if that finds nothing, falls back
    automatically to the closest real county name actually covered in
    that state's own data (stdlib difflib, no new dependency) -- silently
    resolved, never an interactive question back to the veteran. This
    is deliberately scoped to the one state's own known counties (a
    small candidate pool), not a nationwide fuzzy match, keeping the
    false-positive risk of matching the wrong similarly-named place low.
  - Every returned item is tagged "source": "local_verified" so a caller
    (and anyone reviewing output later) can visibly tell it apart from
    whatever hardcoded national-line text the router adds elsewhere.
"""
from __future__ import annotations

import difflib
import os
import sys
from typing import Any, Dict, List, Optional

_NONPROFIT_SRC = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "RESOURCES_NONPROFITS", "src")
)
if _NONPROFIT_SRC not in sys.path:
    sys.path.insert(0, _NONPROFIT_SRC)

_DATA_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "RESOURCES_NONPROFITS", "DATA", "US")
)


def _normalize_state(state: Optional[str]) -> str:
    return (state or "").strip().upper()


def _normalize_county(county: Optional[str]) -> str:
    c = (county or "").strip().lower()
    for suffix in (" county", " co.", " co"):
        if c.endswith(suffix):
            c = c[: -len(suffix)].strip()
    return c


def _shard_paths_for_state(state: str) -> List[str]:
    """Every shard file for a state: the statewide skeleton/file plus any
    regional files under DATA/US/<STATE>/. Filesystem-discovered, not read
    from INDEX/index.us.json -- deliberately kept to the simplest thing
    that works rather than adding a second, separately-maintained manifest
    as a prerequisite."""
    paths: List[str] = []

    top_level = os.path.join(_DATA_ROOT, f"{state}.json")
    if os.path.isfile(top_level):
        paths.append(top_level)

    region_dir = os.path.join(_DATA_ROOT, state)
    if os.path.isdir(region_dir):
        for name in sorted(os.listdir(region_dir)):
            if name.lower().endswith(".json"):
                paths.append(os.path.join(region_dir, name))

    return paths


def _known_counties_for_state(paths: List[str]) -> List[str]:
    """Union of every region's top-level counties_covered list across all
    of a state's shard files -- the candidate pool fuzzy matching is
    scoped to, so it can never resolve to a different state's county."""
    import json

    counties: List[str] = []
    for p in paths:
        try:
            with open(p, encoding="utf-8-sig") as f:
                shard = json.load(f)
        except Exception:
            continue
        for c in shard.get("counties_covered") or []:
            if isinstance(c, str) and c.strip() and c not in counties:
                counties.append(c)
    return counties


def _resolve_county(raw_county: str, known_counties: List[str]) -> Optional[str]:
    """Exact (normalized) match first; if that fails, the closest real
    county name actually covered in this state's own data. Returns None
    if nothing is close enough to be worth trusting."""
    if not raw_county or not known_counties:
        return None

    normalized = _normalize_county(raw_county)
    for known in known_counties:
        if _normalize_county(known) == normalized:
            return known

    close = difflib.get_close_matches(
        raw_county.strip(), known_counties, n=1, cutoff=0.72
    )
    if close:
        return close[0]

    # Also try matching the normalized (suffix-stripped) form -- catches
    # "Mesa County" -> "Mesa" cases difflib's raw-string comparison alone
    # might score just under the cutoff for the un-stripped input.
    close_normalized = difflib.get_close_matches(
        normalized, [_normalize_county(k) for k in known_counties], n=1, cutoff=0.72
    )
    if close_normalized:
        for known in known_counties:
            if _normalize_county(known) == close_normalized[0]:
                return known

    return None


def find_local_resources(
    *,
    state: Optional[str],
    county: Optional[str] = None,
    service_tags: Optional[List[str]] = None,
    crisis_or_self_harm: bool = False,
    # nonprofit_search.search() is explicitly "no ranking, no scores, stable
    # name sort only" (its own docstring) -- a low limit here interacts
    # badly with that: alphabetically-early general orgs ("American Legion")
    # can crowd out the county's own official VSO office ("Mesa County
    # Veterans Service Office") purely on sort order, not relevance.
    # Confirmed directly: limit=2 against Mesa/claims_assistance returned
    # American Legion + Colorado Division of Veterans Affairs and cut off
    # the actual Mesa County VSO entry entirely. 5 comfortably covers every
    # real per-county provider count seen in the current data (western_slope
    # tops out at 8 total across all tags combined) without introducing any
    # ranking logic of this module's own -- that would cut against the
    # existing "no ranking" design law, not work around a real bug in it.
    limit_per_tag: int = 5,
) -> List[Dict[str, Any]]:
    """
    Look up verified local resources for a veteran's state/county, scoped
    to one or more controlled-vocabulary service tags.

    Never raises. Returns [] on any failure, missing data, or no match --
    callers should treat that exactly like "no local data available yet"
    and fall back to whatever national-line guidance they already have.
    This function only ever adds to that, never replaces or blocks it.

    Each returned dict is a sanitized provider record (see
    nonprofit_search.load_registry) with an added "source":
    "local_verified" key so callers can visibly distinguish this from
    hardcoded national fallback text.
    """
    try:
        state_code = _normalize_state(state)
        if len(state_code) != 2 or not state_code.isalpha():
            return []

        tags = [t for t in (service_tags or []) if isinstance(t, str) and t.strip()]
        if not tags:
            return []

        paths = _shard_paths_for_state(state_code)
        if not paths:
            return []

        from nonprofit_search import load_registry, search  # type: ignore

        records = load_registry(paths)
        if not records:
            return []

        # Found directly by this module's own test suite: when a county was
        # supplied but couldn't be resolved, falling back to county=None
        # does NOT mean "no county filter, only statewide entries" -- it
        # means "no county filter at all," which search() correctly treats
        # as "show every county's data unfiltered." Confirmed directly:
        # county=None on the western_slope shard returned all 8 providers
        # across Mesa, Delta, Garfield, and Montrose combined -- exactly the
        # kind of wrong-county mismatch this whole lookup exists to prevent.
        #
        # If the veteran specified a county and it doesn't resolve to
        # anything in this state's data, the raw (unresolved) string is
        # passed through instead. Confirmed directly (against both a
        # regional shard and CO.json's own statewide-only entries, which
        # have coverage_counties == []): a non-matching literal string
        # excludes every record, county-scoped and truly-statewide alike --
        # search()'s county filter has no notion of "statewide passthrough,"
        # only "matches" or "doesn't." That means an unresolvable county
        # loses the statewide fallback a veteran might otherwise have gotten
        # from omitting county entirely. Accepted deliberately: safe-by-
        # default (never guess which county someone meant) matters more
        # here than being maximally generous, and it keeps this function's
        # behavior to two simple cases -- resolves, or doesn't -- rather
        # than a third "sort of resolves" path. Only an actually-omitted
        # county (None/"") skips the filter and reaches statewide entries.
        resolved_county = county
        if county:
            known = _known_counties_for_state(paths)
            match = _resolve_county(county, known)
            if match:
                resolved_county = match

        seen_ids: set = set()
        out: List[Dict[str, Any]] = []
        for tag in tags:
            matches = search(
                records,
                county=resolved_county,
                service=tag,
                crisis_or_self_harm=crisis_or_self_harm,
                limit=limit_per_tag,
            )
            for m in matches:
                pid = m.get("provider_id")
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                tagged = dict(m)
                tagged["source"] = "local_verified"
                out.append(tagged)

        return out

    except Exception:
        # Fail safe, always -- a bad shard file or unexpected input must
        # never break a Division's own routing for the rest of its guidance.
        return []


def _normalize_phone_for_downstream_matching(raw: str) -> str:
    r"""
    pf_coordinator_v1.py's invoke_division() promotes a Division's
    key_resources/notes lines into the coordinator-level
    "immediate_contacts" field ONLY when a line matches its own phone
    regex: r'(1-\d{3}-\d{3}-\d{4}|1-\d{3}-\d{4}|1-877-4AID-VET|
    \d{3}-\d{3}-\d{4}|988)' -- dash-separated digits only, no parens or
    spaces. Confirmed directly that the real shard data is inconsistent:
    western_slope.json uses "(970) 245-4156" (does not match), while
    front_range.json uses "719-553-1000" (matches) for the same kind of
    entry. Without normalizing here, a real local phone number would
    silently fail to reach the one field the coordinator's own synthesis
    actually surfaces at the top level -- staying buried and effectively
    invisible depending on which region's formatting convention happened
    to write it, not on whether the data itself was good.
    """
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"{digits[0]}-{digits[1:4]}-{digits[4:7]}-{digits[7:11]}"
    return raw  # Not a recognizable US number shape -- leave it as given.


def format_local_resource_line(resource: Dict[str, Any]) -> str:
    """
    One shared formatting function for every Division router to use, so a
    veteran sees the same "Local (verified): ..." shape everywhere instead
    of 8 slightly different hand-rolled formats. Labeled explicitly per
    the agreed design: local, verified data must be visibly distinguished
    from whatever hardcoded national-line text a router adds elsewhere.

    Never raises -- a malformed resource dict degrades to a minimal line
    rather than breaking the caller's whole result.
    """
    try:
        name = str(resource.get("name") or "Local organization").strip()
        phones = resource.get("phones") or []
        urls = resource.get("urls") or []

        if phones and isinstance(phones, list):
            contact = _normalize_phone_for_downstream_matching(str(phones[0]))
        elif urls and isinstance(urls, list):
            contact = str(urls[0])
        else:
            contact = "contact info not yet verified -- see notes"

        return f"Local (verified): {name} — {contact}"
    except Exception:
        return "Local (verified): a local resource was found but could not be formatted."
