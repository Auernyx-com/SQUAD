#!/usr/bin/env python3
"""
transportation_cli.py
SQUAD BAT — Transportation Division CLI

Usage:
  python transportation_cli.py '{"transport_needs": ["va_appointment"], "enrolled_va_healthcare": true, "is_rural": true, "state": "CO"}'
  python transportation_cli.py --file intake.json
  python transportation_cli.py --interactive
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from transportation_router import run


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
        print('\n  Routing failed. Immediate resources:')
        print('    211.org  |  DAV dav.org/find-a-chapter')
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
    print('\nTRANSPORTATION DIVISION INTAKE — SQUAD BAT')
    print('─' * 44)

    payload = {}

    print('\nWHAT TRANSPORTATION DO YOU NEED? (enter numbers separated by spaces)')
    print('  1. Rides to VA appointments')
    print('  2. Adaptive vehicle or equipment')
    print('  3. Rural / remote area transport')
    print('  4. Daily or general transit')
    print('  5. Crisis / emergency transport')
    needs_raw = input('Select [e.g. 1 3]: ').strip().split()
    need_map = {
        '1': 'va_appointment', '2': 'adaptive_vehicle',
        '3': 'rural', '4': 'daily_transit', '5': 'crisis'
    }
    payload['transport_needs'] = [need_map[n] for n in needs_raw if n in need_map]

    payload['enrolled_va_healthcare'] = input('\nEnrolled in VA health care? (y/n): ').strip().lower() == 'y'
    payload['has_sc_disability'] = input('Have a service-connected disability? (y/n): ').strip().lower() == 'y'

    if payload['has_sc_disability']:
        r = input('Disability rating (0-100, or Enter to skip): ').strip()
        if r.isdigit():
            payload['disability_rating'] = int(r)

    payload['is_rural'] = input('Do you live in a rural or remote area? (y/n): ').strip().lower() == 'y'
    payload['has_vehicle'] = input('Do you have personal vehicle access? (y/n): ').strip().lower() == 'y'
    payload['can_drive'] = input('Are you able to drive? (y/n): ').strip().lower() == 'y'
    payload['needs_adaptive_vehicle'] = input('Do you need an adaptive vehicle or equipment? (y/n): ').strip().lower() == 'y'

    state = input('State (e.g. CO): ').strip()
    if state:
        payload['state'] = state.upper()
    county = input('County (optional): ').strip()
    if county:
        payload['county'] = county

    return payload


def main():
    parser = argparse.ArgumentParser(description='SQUAD BAT Transportation Division CLI')
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
