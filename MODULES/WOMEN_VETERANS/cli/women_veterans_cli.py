#!/usr/bin/env python3
"""
women_veterans_cli.py
SQUAD BAT — Women Veterans Division CLI

Usage:
  python women_veterans_cli.py '{"needs": ["healthcare", "mst"], "has_mst": true}'
  python women_veterans_cli.py --file intake.json
  python women_veterans_cli.py --interactive
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from women_veterans_router import run


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
        print('\n  Routing failed. Direct line:')
        print('    Women Veterans Call Center: 1-855-829-6636')
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
    print('\nWOMEN VETERANS DIVISION INTAKE — SQUAD BAT')
    print('─' * 44)
    print('All information is confidential.')
    print()

    payload = {}

    print('WHAT DO YOU NEED HELP WITH? (enter numbers separated by spaces)')
    print('  1. VA health care enrollment or access')
    print('  2. Pregnancy / maternity care')
    print('  3. Military Sexual Trauma (MST) care')
    print('  4. Mental health (PTSD, depression, anxiety)')
    print('  5. Reproductive health (screenings, contraception, fertility, menopause)')
    print('  6. Housing or homelessness')
    print('  7. Childcare during VA appointments')
    print('  8. Peer support / women veteran community')
    print('  9. Help with VA benefits or claims')
    needs_raw = input('Select [e.g. 1 3 4]: ').strip().split()
    need_map = {
        '1': 'healthcare', '2': 'maternity', '3': 'mst',
        '4': 'mental_health', '5': 'reproductive_health',
        '6': 'housing', '7': 'childcare',
        '8': 'peer_support', '9': 'benefits_help'
    }
    payload['needs'] = [need_map[n] for n in needs_raw if n in need_map]

    payload['enrolled_va_healthcare'] = input('\nCurrently enrolled in VA health care? (y/n): ').strip().lower() == 'y'
    payload['is_pregnant'] = input('Currently pregnant? (y/n): ').strip().lower() == 'y'
    payload['has_young_children'] = input('Have children under 12? (y/n): ').strip().lower() == 'y'
    payload['has_mst'] = input('Has Military Sexual Trauma been a factor? (y/n): ').strip().lower() == 'y'
    payload['has_ptsd'] = input('Experiencing PTSD? (y/n): ').strip().lower() == 'y'

    print('\nHOUSING SITUATION:')
    print('  1. Stable')
    print('  2. At risk')
    print('  3. Currently homeless')
    print('  4. Prefer not to say')
    hs = input('Select [1-4, default 4]: ').strip()
    payload['housing_situation'] = {
        '1': 'stable', '2': 'at_risk', '3': 'homeless', '4': 'unknown'
    }.get(hs, 'unknown')

    r = input('\nDisability rating (0-100, or Enter to skip): ').strip()
    if r.isdigit():
        payload['disability_rating'] = int(r)

    state = input('State (e.g. CO): ').strip()
    if state:
        payload['state'] = state.upper()

    return payload


def main():
    parser = argparse.ArgumentParser(description='SQUAD BAT Women Veterans Division CLI')
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
