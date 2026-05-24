#!/usr/bin/env python3
"""
va_benefits_cli.py
SQUAD BAT — VA Benefits Division CLI

Usage:
  python va_benefits_cli.py '{"discharge": "honorable", "era": "post_9_11", "need_branches": ["education"]}'
  python va_benefits_cli.py --file intake.json
  python va_benefits_cli.py --interactive
"""

import argparse
import json
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from va_benefits_router import run


def result_to_dict(result) -> dict:
    return {
        "status": result.status,
        "primary_path": result.primary_path,
        "secondary_options": result.secondary_options,
        "flags": result.flags,
        "next_action": result.next_action,
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
        print('\n  Routing failed. Contact a VSO directly:')
        print('    1-800-827-1000  |  va.gov')
        if result.notes:
            for note in result.notes:
                print(f'    {note}')
        return

    qual = result.audit.get("qualification_status", "")
    if qual:
        print(f"\n  DISCHARGE QUALIFICATION: {qual}")

    if result.primary_path:
        print(f"\n  PRIMARY PATH:\n    {result.primary_path}")

    if result.next_action:
        print(f"\n  NEXT ACTION:\n    {result.next_action}")

    if result.key_forms:
        print('\n  KEY FORMS:')
        for f in result.key_forms:
            print(f'    • {f}')

    if result.secondary_options:
        print('\n  ADDITIONAL OPTIONS:')
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
    print('\nVA BENEFITS INTAKE — SQUAD BAT')
    print('─' * 44)

    payload = {}

    print('\nDISCHARGE STATUS:')
    print('  1. Honorable')
    print('  2. General (Under Honorable Conditions)')
    print('  3. Other Than Honorable (OTH)')
    print('  4. Dishonorable')
    print('  5. Unknown')
    dc = input('Select [1-5]: ').strip()
    payload['discharge'] = {
        '1': 'honorable', '2': 'general', '3': 'other_than_honorable',
        '4': 'dishonorable', '5': 'unknown'
    }.get(dc, 'unknown')

    print('\nSERVICE ERA:')
    print('  1. Post-9/11 (2001–present)')
    print('  2. Gulf War (1990–2001)')
    print('  3. Vietnam (1964–1975)')
    print('  4. Korea (1950–1964)')
    print('  5. Peacetime / Other')
    print('  6. Unknown')
    era = input('Select [1-6]: ').strip()
    payload['era'] = {
        '1': 'post_9_11', '2': 'gulf_war', '3': 'vietnam',
        '4': 'korea', '5': 'peacetime', '6': 'unknown'
    }.get(era, 'unknown')

    print('\nWHAT DO YOU NEED? (enter numbers separated by spaces)')
    print('  1. Education / GI Bill')
    print('  2. Vocational rehab (VR&E)')
    print('  3. Employment / job search')
    print('  4. Transition assistance (separating now)')
    print('  5. Home loan')
    print('  6. Adaptive housing')
    print('  7. VA Pension')
    print('  8. Life insurance (VGLI)')
    print('  9. Survivor / dependent benefits')
    print('  10. Burial / memorial')
    needs_raw = input('Select [e.g. 1 3 5]: ').strip().split()
    need_map = {
        '1': 'education', '2': 'voc_rehab', '3': 'employment',
        '4': 'transition', '5': 'home_loan', '6': 'adaptive_housing',
        '7': 'pension', '8': 'life_insurance',
        '9': 'survivor_benefits', '10': 'burial'
    }
    payload['need_branches'] = [need_map[n] for n in needs_raw if n in need_map]

    payload['is_transitioning'] = input('\nCurrently separating from active duty? (y/n): ').strip().lower() == 'y'

    r = input('Service-connected disability rating (0-100, or Enter to skip): ').strip()
    if r.isdigit():
        payload['disability_rating'] = int(r)

    payload['wartime_service'] = input('Wartime service (served during a declared war period)? (y/n): ').strip().lower() == 'y'

    income = input('Monthly income in dollars (or Enter to skip): ').strip()
    if income.isdigit():
        payload['income_monthly'] = int(income)

    payload['has_dependents'] = input('Have dependents (spouse, children)? (y/n): ').strip().lower() == 'y'
    payload['is_survivor_or_dependent'] = input('Are you a surviving spouse or dependent of a veteran? (y/n): ').strip().lower() == 'y'

    months = input('Months since separation (or Enter to skip): ').strip()
    if months.isdigit():
        payload['months_since_separation'] = int(months)

    state = input('State (e.g. CO): ').strip()
    if state:
        payload['state'] = state.upper()
    county = input('County (optional): ').strip()
    if county:
        payload['county'] = county

    return payload


def main():
    parser = argparse.ArgumentParser(description='SQUAD BAT VA Benefits Division CLI')
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
