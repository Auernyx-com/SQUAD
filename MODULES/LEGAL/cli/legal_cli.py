#!/usr/bin/env python3
"""
legal_cli.py
SQUAD BAT — Legal Division CLI

Usage:
  python legal_cli.py '{"legal_needs": ["discharge_upgrade"], "discharge": "other_than_honorable", "years_since_discharge": 8}'
  python legal_cli.py --file intake.json
  python legal_cli.py --interactive
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from legal_router import run


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
        print('\n  Routing failed. Free legal help:')
        print('    NVLSP — nvlsp.org  |  211.org  |  lawhelp.org')
        return

    if result.primary_path:
        print(f"\n  PRIMARY PATH:\n    {result.primary_path}")

    if result.next_action:
        print(f"\n  NEXT ACTION:\n    {result.next_action}")

    if result.key_forms:
        print('\n  KEY FORMS:')
        for f in result.key_forms:
            print(f'    • {f}')

    if result.key_resources:
        print('\n  KEY RESOURCES:')
        for r in result.key_resources:
            print(f'    • {r}')

    if result.secondary_options:
        print('\n  OPTIONS:')
        for opt in result.secondary_options:
            print(f'    • {opt}')

    if result.notes:
        print('\n  IMPORTANT NOTES:')
        for note in result.notes:
            print(f'    ⚑ {note}')

    if result.flags:
        print(f"\n  FLAGS: {', '.join(result.flags)}")

    print('\n' + '═' * 62)


def interactive_intake() -> dict:
    print('\nLEGAL DIVISION INTAKE — SQUAD BAT')
    print('─' * 44)

    payload = {}

    print('\nWHAT LEGAL ISSUE(S) DO YOU FACE? (enter numbers separated by spaces)')
    print('  1. Discharge upgrade')
    print('  2. VA claim denial / appeal')
    print('  3. Military Sexual Trauma (MST)')
    print('  4. Civilian legal issue (housing, employment, family, etc.)')
    print('  5. Military records correction (DD-214 errors, etc.)')
    print('  6. Predatory VSO or benefits scam')
    needs_raw = input('Select [e.g. 1 2]: ').strip().split()
    need_map = {
        '1': 'discharge_upgrade', '2': 'va_appeal', '3': 'mst',
        '4': 'civilian_legal', '5': 'records_correction', '6': 'predatory_lending'
    }
    payload['legal_needs'] = [need_map[n] for n in needs_raw if n in need_map]

    print('\nDISCHARGE STATUS:')
    print('  1. Honorable')
    print('  2. General (Under Honorable Conditions)')
    print('  3. Other Than Honorable (OTH)')
    print('  4. Dishonorable')
    print('  5. Unknown')
    dc = input('Select [1-5, default 5]: ').strip()
    payload['discharge'] = {
        '1': 'honorable', '2': 'general', '3': 'other_than_honorable',
        '4': 'dishonorable', '5': 'unknown'
    }.get(dc, 'unknown')

    years = input('\nYears since discharge (or Enter to skip): ').strip()
    if years.isdigit():
        payload['years_since_discharge'] = int(years)

    if 'va_appeal' in payload.get('legal_needs', []):
        print('\nWHICH APPEALS LANE ARE YOU IN (if any)?')
        print('  1. None / just denied')
        print('  2. Supplemental Claim')
        print('  3. Higher-Level Review (HLR)')
        print('  4. Board of Veterans Appeals (BVA)')
        print('  5. Court of Appeals for Veterans Claims (CAVC)')
        print('  6. Unknown')
        lane = input('Select [1-6, default 1]: ').strip()
        payload['appeals_lane'] = {
            '1': 'none', '2': 'supplemental', '3': 'hlr',
            '4': 'bva', '5': 'cavc', '6': 'unknown'
        }.get(lane, 'none')

    if 'civilian_legal' in payload.get('legal_needs', []):
        print('\nCIVILIAN LEGAL ISSUE TYPE:')
        print('  1. Housing (eviction, lease, foreclosure)')
        print('  2. Employment (discrimination, USERRA, wrongful termination)')
        print('  3. Family (divorce, custody, child support)')
        print('  4. Consumer (predatory lending, debt collection)')
        print('  5. Criminal record (expungement, veterans court)')
        print('  6. Other')
        ci = input('Select [1-6, default 6]: ').strip()
        payload['civilian_issue'] = {
            '1': 'housing', '2': 'employment', '3': 'family',
            '4': 'consumer', '5': 'criminal_record', '6': 'other'
        }.get(ci, 'other')

    payload['has_mst'] = input('\nIs Military Sexual Trauma (MST) a factor? (y/n): ').strip().lower() == 'y'
    payload['has_denied_claim'] = input('Has a VA claim been denied? (y/n): ').strip().lower() == 'y'

    state = input('State (e.g. CO): ').strip()
    if state:
        payload['state'] = state.upper()

    return payload


def main():
    parser = argparse.ArgumentParser(description='SQUAD BAT Legal Division CLI')
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
