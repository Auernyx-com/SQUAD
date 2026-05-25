#!/usr/bin/env python3
"""
generate_state_shards.py
Generates skeleton statewide resource shards for all US states.
Run from SQUAD root. Skips states that already have a DATA/US/<STATE>.json.

Usage:
    python3 tools/generate_state_shards.py
"""

import json
import os

# Primary VAMC(s) per state — name and city only.
# Phones intentionally omitted — all marked VERIFY_BEFORE_PRODUCTION.
# Sources: va.gov facility directory (public record).
STATE_VAMC = {
    "AK": [("Alaska VA Healthcare System", "Anchorage")],
    "AL": [("Birmingham VA Medical Center", "Birmingham"), ("Tuscaloosa VA Medical Center", "Tuscaloosa"), ("Central Alabama VA — Tuskegee Division", "Tuskegee")],
    "AR": [("John L. McClellan Memorial VAMC", "Little Rock")],
    "AZ": [("Phoenix VA Health Care System", "Phoenix"), ("Southern Arizona VA Health Care System", "Tucson")],
    "CA": [("VA Greater Los Angeles", "Los Angeles"), ("VA Long Beach", "Long Beach"), ("VA San Diego", "San Diego"), ("VA Palo Alto", "Palo Alto"), ("VA San Francisco", "San Francisco"), ("VA Central California", "Fresno"), ("VA Northern California", "Sacramento")],
    "CT": [("VA Connecticut — West Haven Campus", "West Haven"), ("VA Connecticut — Newington Campus", "Newington")],
    "DC": [("Washington DC VA Medical Center", "Washington DC")],
    "DE": [("Wilmington VA Medical Center", "Wilmington")],
    "FL": [("Bay Pines VA Healthcare System", "Bay Pines"), ("James A. Haley VA — Tampa", "Tampa"), ("West Palm Beach VA", "West Palm Beach"), ("Miami VA Healthcare System", "Miami"), ("Malcom Randall VA — Gainesville", "Gainesville"), ("Orlando VA Health Care System", "Orlando")],
    "GA": [("Atlanta VA Health Care System", "Decatur"), ("Augusta VA Medical Center", "Augusta")],
    "HI": [("VA Pacific Islands — Spark Matsunaga VAMC", "Honolulu")],
    "IA": [("Iowa City VA Health Care System", "Iowa City"), ("VA Central Iowa", "Des Moines")],
    "ID": [("Boise VA Medical Center", "Boise")],
    "IL": [("Jesse Brown VA — Chicago", "Chicago"), ("Edward Hines Jr. VA", "Hines"), ("Marion VA Medical Center", "Marion")],
    "IN": [("Richard L. Roudebush VA — Indianapolis", "Indianapolis"), ("VA Northern Indiana", "Fort Wayne")],
    "KS": [("Robert J. Dole VA — Wichita", "Wichita"), ("Dwight D. Eisenhower VA — Leavenworth", "Leavenworth")],
    "KY": [("Lexington VA Health Care System", "Lexington"), ("Robley Rex VA — Louisville", "Louisville")],
    "LA": [("Southeast Louisiana VA — New Orleans", "New Orleans"), ("Overton Brooks VA — Shreveport", "Shreveport")],
    "MA": [("VA Boston Health Care System", "Boston"), ("Edith Nourse Rogers Memorial VA — Bedford", "Bedford")],
    "MD": [("VA Maryland — Baltimore", "Baltimore"), ("Perry Point VA Medical Center", "Perry Point")],
    "ME": [("Togus VA Medical Center", "Augusta")],
    "MI": [("John D. Dingell VA — Detroit", "Detroit"), ("Battle Creek VA", "Battle Creek"), ("VA Ann Arbor", "Ann Arbor"), ("Oscar G. Johnson VA — Iron Mountain", "Iron Mountain")],
    "MN": [("Minneapolis VA Health Care System", "Minneapolis"), ("St. Cloud VA Health Care System", "St. Cloud")],
    "MO": [("John Cochran VA — St. Louis", "St. Louis"), ("Harry S. Truman VA — Columbia", "Columbia"), ("Kansas City VA Medical Center", "Kansas City")],
    "MS": [("G.V. (Sonny) Montgomery VA — Jackson", "Jackson"), ("Gulf Coast VA — Biloxi", "Biloxi")],
    "MT": [("Fort Harrison VA Medical Center", "Helena")],
    "NC": [("Durham VA Health Care System", "Durham"), ("Fayetteville VA Medical Center", "Fayetteville"), ("W.G. (Bill) Hefner VA — Salisbury", "Salisbury"), ("Charles George VA — Asheville", "Asheville")],
    "ND": [("Fargo VA Health Care System", "Fargo")],
    "NE": [("VA Nebraska-Western Iowa — Omaha", "Omaha")],
    "NH": [("Manchester VA Medical Center", "Manchester")],
    "NJ": [("VA New Jersey — East Orange", "East Orange"), ("VA New Jersey — Lyons", "Lyons")],
    "NM": [("New Mexico VA Health Care System", "Albuquerque")],
    "NV": [("VA Southern Nevada — Las Vegas", "Las Vegas"), ("VA Sierra Nevada — Reno", "Reno")],
    "NY": [("VA New York Harbor — Manhattan", "New York"), ("VA New York Harbor — Brooklyn", "Brooklyn"), ("VA Western New York — Buffalo", "Buffalo"), ("Samuel S. Stratton VA — Albany", "Albany"), ("Syracuse VA Medical Center", "Syracuse"), ("Northport VA Medical Center", "Northport")],
    "OH": [("Cincinnati VA Medical Center", "Cincinnati"), ("Louis Stokes Cleveland VA", "Cleveland"), ("Chalmers P. Wylie VA — Columbus", "Columbus"), ("Dayton VA Medical Center", "Dayton")],
    "OK": [("Oklahoma City VA Health Care System", "Oklahoma City"), ("Jack C. Montgomery VA — Muskogee", "Muskogee")],
    "OR": [("VA Portland Health Care System", "Portland"), ("Roseburg VA Health Care System", "Roseburg"), ("Southern Oregon Rehab Center — White City", "White City")],
    "PA": [("Corporal Michael J. Crescenz VA — Philadelphia", "Philadelphia"), ("VA Pittsburgh", "Pittsburgh"), ("Coatesville VA Medical Center", "Coatesville"), ("Erie VA Medical Center", "Erie"), ("Lebanon VA Medical Center", "Lebanon")],
    "RI": [("Providence VA Medical Center", "Providence")],
    "SC": [("Columbia VA Health Care System", "Columbia"), ("Ralph H. Johnson VA — Charleston", "Charleston")],
    "SD": [("Hot Springs VA Medical Center", "Hot Springs"), ("Sioux Falls VA Health Care System", "Sioux Falls")],
    "TN": [("Tennessee Valley VA — Nashville", "Nashville"), ("Memphis VA Medical Center", "Memphis"), ("James H. Quillen VA — Mountain Home", "Mountain Home")],
    "TX": [("Michael E. DeBakey VA — Houston", "Houston"), ("VA North Texas — Dallas", "Dallas"), ("South Texas VA — San Antonio", "San Antonio"), ("Central Texas VA — Temple", "Temple"), ("Amarillo VA Health Care System", "Amarillo"), ("West Texas VA — Big Spring", "Big Spring"), ("El Paso VA Health Care System", "El Paso")],
    "UT": [("VA Salt Lake City Health Care System", "Salt Lake City")],
    "VA": [("Hunter Holmes McGuire VA — Richmond", "Richmond"), ("Hampton VA Medical Center", "Hampton"), ("Salem VA Medical Center", "Salem")],
    "VT": [("White River Junction VA Medical Center", "White River Junction")],
    "WI": [("William S. Middleton VA — Madison", "Madison"), ("Clement J. Zablocki VA — Milwaukee", "Milwaukee"), ("Tomah VA Medical Center", "Tomah")],
    "WV": [("Huntington VA Medical Center", "Huntington"), ("Beckley VA Medical Center", "Beckley"), ("Louis A. Johnson VA — Clarksburg", "Clarksburg"), ("Martinsburg VA Medical Center", "Martinsburg")],
    "WY": [("Cheyenne VA Medical Center", "Cheyenne")],
}

# State VSO agencies — name and website
STATE_VSO = {
    "AK": ("Alaska Division of Veterans Affairs", "https://veterans.alaska.gov"),
    "AL": ("Alabama Department of Veterans Affairs", "https://www.va.alabama.gov"),
    "AR": ("Arkansas Department of Veterans Affairs", "https://www.veterans.arkansas.gov"),
    "AZ": ("Arizona Department of Veterans Services", "https://dvs.az.gov"),
    "CA": ("California Department of Veterans Affairs (CalVet)", "https://www.calvet.ca.gov"),
    "CT": ("Connecticut Department of Veterans Affairs", "https://portal.ct.gov/dva"),
    "DC": ("Office of Veterans Affairs — DC", "https://ova.dc.gov"),
    "DE": ("Delaware Commission of Veterans Affairs", "https://veteransaffairs.delaware.gov"),
    "FL": ("Florida Department of Veterans Affairs", "https://www.floridavets.org"),
    "GA": ("Georgia Department of Veterans Service", "https://veterans.georgia.gov"),
    "HI": ("Hawaii Office of Veterans Services", "https://dod.hawaii.gov/ovs"),
    "IA": ("Iowa Department of Veterans Affairs", "https://va.iowa.gov"),
    "ID": ("Idaho Division of Veterans Services", "https://veterans.idaho.gov"),
    "IL": ("Illinois Department of Veterans Affairs", "https://www2.illinois.gov/veterans"),
    "IN": ("Indiana Department of Veterans Affairs", "https://www.in.gov/dva"),
    "KS": ("Kansas Commission on Veterans Affairs", "https://kcva.ks.gov"),
    "KY": ("Kentucky Department of Veterans Affairs", "https://veterans.ky.gov"),
    "LA": ("Louisiana Department of Veterans Affairs", "https://www.vetaffairs.la.gov"),
    "MA": ("Massachusetts Department of Veterans Services", "https://www.mass.gov/orgs/department-of-veterans-services"),
    "MD": ("Maryland Department of Veterans Affairs", "https://veterans.maryland.gov"),
    "ME": ("Maine Bureau of Veterans Services", "https://www.maine.gov/veterans"),
    "MI": ("Michigan Veterans Affairs Agency", "https://www.michigan.gov/mvaa"),
    "MN": ("Minnesota Department of Veterans Affairs", "https://mn.gov/mdva"),
    "MO": ("Missouri Veterans Commission", "https://mvc.dps.mo.gov"),
    "MS": ("Mississippi Veterans Affairs Board", "https://www.vab.ms.gov"),
    "MT": ("Montana Veterans Affairs Division", "https://dma.mt.gov/veterans"),
    "NC": ("North Carolina Division of Veterans Affairs", "https://www.milvets.nc.gov"),
    "ND": ("North Dakota Department of Veterans Affairs", "https://www.nd.gov/veterans"),
    "NE": ("Nebraska Department of Veterans Affairs", "https://veterans.nebraska.gov"),
    "NH": ("New Hampshire Division of Veterans Services", "https://www.nh.gov/nhveterans"),
    "NJ": ("New Jersey Department of Military and Veterans Affairs", "https://www.nj.gov/military"),
    "NM": ("New Mexico Department of Veterans Services", "https://www.nmdvs.org"),
    "NV": ("Nevada Department of Veterans Services", "https://veterans.nv.gov"),
    "NY": ("New York Division of Veterans Services", "https://veterans.ny.gov"),
    "OH": ("Ohio Department of Veterans Services", "https://dvs.ohio.gov"),
    "OK": ("Oklahoma Department of Veterans Affairs", "https://odva.ok.gov"),
    "OR": ("Oregon Department of Veterans Affairs", "https://www.oregon.gov/odva"),
    "PA": ("Pennsylvania Department of Military and Veterans Affairs", "https://www.dmva.pa.gov"),
    "RI": ("Rhode Island Office of Veterans Services", "https://veterans.ri.gov"),
    "SC": ("South Carolina Department of Veterans Affairs", "https://va.sc.gov"),
    "SD": ("South Dakota Department of Veterans Affairs", "https://vetaffairs.sd.gov"),
    "TN": ("Tennessee Department of Veterans Services", "https://www.tn.gov/veterans"),
    "TX": ("Texas Veterans Commission", "https://www.tvc.texas.gov"),
    "UT": ("Utah Department of Veterans and Military Affairs", "https://veterans.utah.gov"),
    "VA": ("Virginia Department of Veterans Services", "https://www.dvs.virginia.gov"),
    "VT": ("Vermont Office of Veterans Affairs", "https://veterans.vermont.gov"),
    "WI": ("Wisconsin Department of Veterans Affairs", "https://dva.wi.gov"),
    "WV": ("West Virginia Division of Veterans Assistance", "https://veterans.wv.gov"),
    "WY": ("Wyoming Veterans Commission", "https://wyomingveterans.com"),
}

STATE_NAMES = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona",
    "CA": "California", "CT": "Connecticut", "DC": "District of Columbia",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "IA": "Iowa", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts",
    "MD": "Maryland", "ME": "Maine", "MI": "Michigan", "MN": "Minnesota",
    "MO": "Missouri", "MS": "Mississippi", "MT": "Montana", "NC": "North Carolina",
    "ND": "North Dakota", "NE": "Nebraska", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NV": "Nevada", "NY": "New York", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VA": "Virginia", "VT": "Vermont", "WI": "Wisconsin",
    "WV": "West Virginia", "WY": "Wyoming",
}

DATA_ROOT = os.path.join(os.path.dirname(__file__), '..', 'MODULES', 'RESOURCES_NONPROFITS', 'DATA', 'US')

def build_state_shard(state_code):
    state_name   = STATE_NAMES[state_code]
    vamcs        = STATE_VAMC.get(state_code, [])
    vso_name, vso_url = STATE_VSO.get(state_code, (f"{state_name} Veterans Affairs", ""))
    vamc_cities  = ", ".join(set(city for _, city in vamcs)) if vamcs else "statewide"

    providers = []

    # State VSO
    providers.append({
        "provider_id": f"US/{state_code}/{state_code.lower()}-state-vso",
        "name": vso_name,
        "org_type": "state_agency",
        "coverage_counties": [],
        "cities": [],
        "services": [
            "claims_assistance", "benefits_navigation",
            "resource_referral", "advocacy"
        ],
        "va_visibility": "high",
        "notes": f"State veterans service agency. Free accredited claims assistance and benefits navigation statewide. Find county VSO contacts at {vso_url}.",
        "phones": [],
        "urls": [vso_url] if vso_url else [],
        "verify_before_production": [f"{vso_name} statewide phone — check state website"],
        "source_hints": [vso_url if vso_url else "state veterans affairs website"]
    })

    # Primary VAMC(s)
    for i, (vamc_name, vamc_city) in enumerate(vamcs):
        providers.append({
            "provider_id": f"US/{state_code}/{state_code.lower()}-vamc-{i+1}",
            "name": vamc_name,
            "org_type": "vamc",
            "coverage_counties": [],
            "cities": [vamc_city],
            "services": [
                "primary_care", "mental_health", "specialty_care",
                "benefits_navigation"
            ],
            "va_visibility": "high",
            "notes": f"VA Medical Center serving {state_name}. VA enrollment required for most services. Find full details at va.gov/find-locations.",
            "phones": [],
            "urls": ["https://www.va.gov/find-locations"],
            "verify_before_production": [f"{vamc_name} main line and address — check va.gov/find-locations"],
            "source_hints": ["va.gov facility locator"]
        })

    # Vet Centers (always via locator)
    providers.append({
        "provider_id": f"US/{state_code}/{state_code.lower()}-vet-centers",
        "name": f"{state_name} Vet Centers",
        "org_type": "vet_center",
        "coverage_counties": [],
        "cities": [],
        "services": [
            "mental_health_peer_support", "clinical_therapy_referral",
            "mst_counseling", "resource_referral", "family_support"
        ],
        "va_visibility": "high",
        "notes": "VA-affiliated Vet Centers. No VA enrollment required — walk-in eligible. Find all locations at va.gov/find-locations (filter: Vet Center).",
        "phones": [],
        "urls": ["https://www.va.gov/find-locations"],
        "source_hints": ["va.gov vet center locator"]
    })

    return {
        "region_id": f"US/{state_code}",
        "country": "US",
        "state": state_code,
        "region_label": f"{state_name} — Statewide",
        "notes": (
            f"Statewide {state_name} shard. Regional shards take precedence for local queries — "
            f"this file is the fallback when no regional shard exists for a county. "
            f"Primary VA facility/facilities: {', '.join(name for name, _ in vamcs) if vamcs else 'see va.gov/find-locations'} "
            f"({vamc_cities}). State VSO: {vso_name}. "
            f"All phone numbers marked VERIFY_BEFORE_PRODUCTION — national VA lines are always valid. "
            f"Add regional shards under DATA/US/{state_code}/<region>.json as local data is confirmed."
        ),
        "providers": providers
    }


def main():
    os.makedirs(DATA_ROOT, exist_ok=True)
    skipped = []
    created = []

    for state_code in sorted(STATE_NAMES.keys()):
        out_path = os.path.join(DATA_ROOT, f"{state_code}.json")
        if os.path.exists(out_path):
            skipped.append(state_code)
            continue
        shard = build_state_shard(state_code)
        with open(out_path, 'w') as f:
            json.dump(shard, f, indent=2)
            f.write('\n')
        created.append(state_code)
        print(f"  created: {state_code}.json")

    print(f"\nDone. Created {len(created)} shards. Skipped {len(skipped)} (already exist): {', '.join(skipped)}")


if __name__ == '__main__':
    main()
