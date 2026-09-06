# SQUAD

**Veteran Navigation System — Backend Coordinator + Resource Database**  
Powers [Pathfinder](https://squad.wyerd.org) at squad.wyerd.org

Part of SQUAD BAT — a veteran navigation platform built by and for veterans.

---

## What this is

SQUAD is the coordinator, decision logic, and resource database behind Pathfinder. When a veteran tells Pathfinder their situation, SQUAD:

1. Routes the intake through domain modules (housing, benefits, legal, etc.)
2. Matches their situation against verified local resource data
3. Returns specific programs, offices, and contacts — not generic advice

**The frontend** (what veterans see) is in [wyerd-squad](https://github.com/Auernyx-com/wyerd-squad).  
**The API worker** (Cloudflare Worker with AI binding) is in [pathfinder-worker](https://github.com/Auernyx-com/pathfinder-worker).

---

## Repository structure

```
SQUAD/
├── AGENTS/
│   └── CORE/
│       └── PATHFINDER/         ← Pathfinder coordinator agent
│
├── MODULES/                    ← Domain decision logic
│   ├── VA_BENEFITS/            ← Disability, PACT Act, appeals, TDIU
│   ├── HOUSING/                ← HUD-VASH, SSVF, VA home loan, eviction
│   ├── MEDICAL_DISABILITY/     ← VA enrollment, Vet Centers, MST care
│   ├── LEGAL/                  ← Discharge upgrade, appeals, civilian aid
│   ├── BUSINESS_OPPORTUNITY/   ← SDVOSB, Voc Rehab Ch. 31, SBA
│   ├── TRANSPORTATION/         ← BTSSS travel pay, DAV transport
│   ├── WOMEN_VETERANS/         ← Women-specific care tracks
│   ├── TOXIC_EXPOSURE/         ← Agent Orange, PFAS, Camp Lejeune, Gulf War
│   ├── CRISIS_REDIRECT/        ← Crisis Line routing (always additive)
│   ├── INTAKE_DO_NOT_GUESS/    ← Guardrail: intake boundaries
│   ├── OBSIDIAN_JUDGMENT/      ← Provenance + governance-hash tamper detection
│   └── RESOURCES_NONPROFITS/   ← Resource database (see below)
│
├── MODULES/RESOURCES_NONPROFITS/
│   ├── INDEX/
│   │   └── index.us.json       ← 50-state index: statewide + regional shards
│   └── DATA/US/
│       ├── AK.json             ← Statewide skeleton (all 50 states)
│       ├── ...
│       ├── CO.json
│       ├── CO/
│       │   ├── western_slope.json   ← Deep regional — confirmed local data
│       │   ├── front_range.json     ← El Paso, Teller, Pueblo, Fremont, Custer
│       │   └── denver_metro.json    ← Placeholder
│       ├── WA.json
│       └── WA/
│           └── puget_sound.json     ← Pierce, King, Kitsap, Thurston (JBLM)
│
├── tools/
│   └── generate_state_shards.py    ← Generates skeleton statewide shards
│
├── docs/
│   └── baseline-records.md         ← SHA-256 integrity run history
│
└── governance/                     ← Design laws, guardrails, audit records
```

---

## Resource shard system

Coverage is tiered. Regional shards take precedence over statewide:

```
Query: veteran in Mesa County, CO
  → Check CO/western_slope.json (covers Mesa) ✓
  → Return local contacts

Query: veteran in Larimer County, CO
  → No regional shard for Larimer
  → Fall back to CO.json (statewide)
  → Surface notice: "statewide data only for this area"

Query: veteran in Iowa
  → IA.json (statewide skeleton)
  → Surface notice: routes through national lines
```

### Shard structure

```json
{
  "region_id": "US/CO/western_slope",
  "country": "US",
  "state": "CO",
  "region_label": "Western Slope Colorado",
  "counties_covered": ["Mesa", "Delta", "Montrose", ...],
  "providers": [
    {
      "provider_id": "US/CO/western_slope/mesa-county-vso",
      "name": "Mesa County Veterans Service Office",
      "org_type": "county_vso",
      "services": ["claims_assistance", "benefits_navigation", ...],
      "phones": ["970-244-1693"],
      "urls": ["https://www.mesacounty.us/veterans"],
      "verify_before_production": []
    }
  ]
}
```

**VERIFY_BEFORE_PRODUCTION discipline**: Phone numbers are never LLM-generated. If a number isn't confirmed from a primary source, it is marked and not surfaced to veterans. Statewide skeleton shards ship with no phone numbers by design.

### Adding a regional shard

1. Create `DATA/US/<STATE>/<region>.json` using the existing regional shards as templates
2. Register it in `INDEX/index.us.json` under the state's `regions` array
3. Add the counties covered to the tool's `_COVERAGE_REGIONS` object in `wyerd-squad/tool/index.html`

### Generating statewide skeletons

```bash
python3 tools/generate_state_shards.py
```

Generates skeleton shards for any states that don't already have one. Skips existing files. Uses confirmed VAMC names/cities and state VSO names/URLs from public VA records.

---

## Design laws

**Fail-closed**: When uncertain, do not route. Surface the uncertainty to the veteran and tell them to verify with a VSO.

**Crisis is always additive**: Crisis Line routing is never gated on other intake answers. It is appended when relevant regardless of what else is surfaced.

**No percentage confidence surfaced to veterans**: Confidence is used internally to decide what to show; it is never displayed as a number to veterans.

**Discharge routing**: OTH and Bad Paper are handled without judgment. The system knows these veterans often have the most complex needs and the most barriers.

**Anti-sycophancy**: The system does not tell veterans they qualify for something they don't. It is honest about eligibility boundaries and always points to a VSO for final determination.

**Congressional rep names are never hardcoded**: Always routed to house.gov/representatives/find-your-representative. Names change; the locator doesn't.

---

## Coverage areas

| Module | What it covers |
|--------|---------------|
| VA Benefits | Disability ratings, PACT Act burn pit presumptives, previously denied claims, appeals, TDIU, SMC, Aid & Attendance |
| Housing | HUD-VASH, SSVF rapid re-housing, DV housing, criminal record barriers, VA home loan, eviction defense, adaptive housing grants |
| Healthcare | VA enrollment, VAMC assignment, Vet Center referral, MST care, caregiver support, Crisis Line |
| Legal | Discharge upgrade, VA appeals, MST legal support, civilian legal aid, records correction, predatory lending |
| Business | SDVOSB/VOSB certification, federal contracting, SBA programs, Voc Rehab Ch. 31, employment transition |
| Transportation | BTSSS travel pay, DAV transport, rural transport |
| Women Veterans | Women-specific care tracks across all modules |
| Toxic Exposure | Agent Orange, Camp Lejeune, Gulf War Syndrome, PFAS — PACT Act refile routing |

---

## Beta status

Western Slope Colorado pilot. Testing with veterans across different branches, discharge statuses, and situations before expanding nationally. Front Range CO and Pierce County WA regional shards added for initial beta testers.

National expansion is the goal. This is the pilot that gets it right first.

---

**SQUAD BAT — Veteran Navigation**  
Western Slope Colorado pilot → national expansion  
[squad.wyerd.org](https://squad.wyerd.org) · [admin@wyerd.org](mailto:admin@wyerd.org)
