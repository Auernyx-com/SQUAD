#!/usr/bin/env python3
"""
toxic_exposure_cli.py
SQUAD BAT — Toxic Exposure Division CLI

Usage:
  python toxic_exposure_cli.py '{"era": "post_9_11", "exposure_types": ["burn_pit"], "locations_served": ["iraq"], "conditions": ["respiratory"]}'
  python toxic_exposure_cli.py --file intake.json
  python toxic_exposure_cli.py --interactive
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from toxic_exposure_router import run


def result_to_dict(result) -> dict:
    return {
        "status": result.status,
        "primary_path": result.primary_path,
        "secondary_options": result.secondary_options,
        "flags": result.flags,
        "next_action": result.next_action,
        "key_resources": result.key_resources,
        "key_forms": result.key_forms,
        "notes": result.notes,
        "presumptive_conditions": result.presumptive_conditions,
        "questions": result.questions,
        "audit": result.audit,
    }


def print_result(result) -> None:
    print('\n' + '═' * 62)
    print(f"  STATUS: {result.status}")
    print('═' * 62)

    if result.status == 'NEEDS_INPUT':
        print('\n  Additional information needed:')
        for q in result.questions:
            print(f'    • {q}')
        return

    if result.status == 'FAILED_CLOSED':
        print('\n  Routing failed. Call VA directly:')
        print('    1-800-827-1000 — ask about PACT Act eligibility')
        print('    va.gov/pact-act-information')
        return

    if result.primary_path:
        print(f"\n  PRIMARY PATH:\n    {result.primary_path}")

    if result.next_action:
        print(f"\n  NEXT ACTION:")
        for line in result.next_action.split('. '):
            if line.strip():
                print(f"    {line.strip()}.")

    if result.notes:
        print('\n  ⚠  IMPORTANT — READ THIS:')
        for note in result.notes:
            print(f'\n    {note}')

    if result.key_forms:
        print('\n  KEY FORMS:')
        for f in result.key_forms:
            print(f'    • {f}')

    if result.key_resources:
        print('\n  KEY RESOURCES:')
        for r in result.key_resources:
            print(f'    • {r}')

    if result.secondary_options:
        print('\n  DETAILS & OPTIONS:')
        for opt in result.secondary_options:
            print(f'\n    • {opt}')

    if result.presumptive_conditions:
        print(f'\n  PRESUMPTIVE CONDITIONS ({len(result.presumptive_conditions)} covered):')
        for cond in result.presumptive_conditions[:10]:
            print(f'    ✓ {cond}')
        if len(result.presumptive_conditions) > 10:
            print(f'    ... and {len(result.presumptive_conditions) - 10} more — see va.gov/pact-act-information')

    if result.flags:
        print(f"\n  FLAGS: {', '.join(result.flags)}")

    print('\n' + '═' * 62)


def interactive_intake() -> dict:
    print('\nTOXIC EXPOSURE DIVISION INTAKE — SQUAD BAT')
    print('─' * 44)
    print('Identifying what you may have been exposed to during service.')
    print()

    payload = {}

    print('SERVICE ERA:')
    print('  1. Post-9/11 (OIF, OEF, OND — Iraq, Afghanistan, etc.)')
    print('  2. Gulf War (1990–2001 — Operation Desert Storm/Shield)')
    print('  3. Vietnam (1962–1975)')
    print('  4. Korea (1950–present — especially DMZ 1967–1971)')
    print('  5. Cold War / Other')
    print('  6. Unknown')
    era = input('Select [1-6]: ').strip()
    payload['era'] = {
        '1': 'post_9_11', '2': 'gulf_war', '3': 'vietnam',
        '4': 'korea', '5': 'cold_war', '6': 'unknown'
    }.get(era, 'unknown')

    print('\nWHAT WERE YOU EXPOSED TO? (enter numbers separated by spaces)')
    print('  1. Burn pits / smoke / open-air trash burning')
    print('  2. Agent Orange / herbicides')
    print('  3. Contaminated water (Camp Lejeune 1953–1987)')
    print('  4. Gulf War Illness / unexplained chronic symptoms')
    print('  5. Radiation (nuclear testing, Hiroshima/Nagasaki, Palomares)')
    print('  6. PFAS / firefighting foam (AFFF) at military base')
    print('  7. Not sure / want to find out what applies')
    exp_raw = input('Select [e.g. 1 3]: ').strip().split()
    exp_map = {
        '1': 'burn_pit', '2': 'agent_orange', '3': 'camp_lejeune',
        '4': 'gulf_war_syndrome', '5': 'radiation', '6': 'pfas', '7': 'unknown'
    }
    payload['exposure_types'] = [exp_map[n] for n in exp_raw if n in exp_map]

    print('\nWHERE DID YOU SERVE? (enter country/location names, comma-separated)')
    print('  Examples: Iraq, Afghanistan, Kuwait, Vietnam, Korea, Camp Lejeune')
    locs_raw = input('Locations (or Enter to skip): ').strip()
    if locs_raw:
        payload['locations_served'] = [
            loc.strip().lower().replace(' ', '_')
            for loc in locs_raw.split(',') if loc.strip()
        ]

    print('\nCURRENT HEALTH CONDITIONS? (enter numbers separated by spaces)')
    print('  1. Respiratory (breathing issues, asthma, chronic cough)')
    print('  2. Cancer (any type)')
    print('  3. Neurological (headaches, memory, tingling, tremors)')
    print('  4. GI / digestive (IBS, chronic stomach issues)')
    print('  5. Chronic fatigue')
    print('  6. Skin conditions')
    print('  7. Cardiac / heart')
    print('  8. Reproductive health issues')
    print('  9. Undiagnosed / doctors can\'t explain it')
    print('  10. No conditions yet / just want info')
    cond_raw = input('Select [e.g. 1 3 9]: ').strip().split()
    cond_map = {
        '1': 'respiratory', '2': 'cancer', '3': 'neurological',
        '4': 'gi', '5': 'chronic_fatigue', '6': 'skin',
        '7': 'cardiac', '8': 'reproductive', '9': 'undiagnosed', '10': 'none_yet'
    }
    payload['conditions'] = [cond_map[n] for n in cond_raw if n in cond_map]

    payload['camp_lejeune'] = input('\nDid you serve or live at Camp Lejeune between 1953–1987? (y/n): ').strip().lower() == 'y'
    if payload['camp_lejeune']:
        payload['is_lejeune_family_member'] = input('Are you a family member (not the veteran)? (y/n): ').strip().lower() == 'y'

    payload['was_previously_denied'] = input('Have you been denied a VA claim for a toxic exposure condition? (y/n): ').strip().lower() == 'y'
    payload['enrolled_va_healthcare'] = input('Currently enrolled in VA health care? (y/n): ').strip().lower() == 'y'

    state = input('State (e.g. CO): ').strip()
    if state:
        payload['state'] = state.upper()

    return payload


def main():
    parser = argparse.ArgumentParser(description='SQUAD BAT Toxic Exposure Division CLI')
    parser.add_argument('payload', nargs='?', help='JSON payload string')
    parser.add_argument('--file', '-f', help='Path to JSON intake file')
    parser.add_argument('--interactive', '-i', action='store_true')
    parser.add_argument('--raw', action='store_true', help='Output raw JSON')
    args = parser.parse_args()

    if args.interactive:
        payload = interactive_intake()
    elif args.file:
        with open(args.file) as fh:
            payload = json.load(fh)
    elif args.payload:
        payload = json.loads(args.payload)
    else:
        parser.print_help()
        sys.exit(1)

    result = run(payload)

    if args.raw:
        print(json.dumps(result_to_dict(result), indent=2))
    else:
        print_result(result)


if __name__ == '__main__':
    main()
