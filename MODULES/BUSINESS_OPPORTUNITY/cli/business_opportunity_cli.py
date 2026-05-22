#!/usr/bin/env python3
"""
business_opportunity_cli.py
SQUAD BAT — Business & Opportunity Division CLI

Usage:
  python business_opportunity_cli.py '{"discharge": "honorable", "service_connected_disability": true, "state": "CO"}'
  python business_opportunity_cli.py --file intake.json
  python business_opportunity_cli.py --interactive
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from business_opportunity_router import route_to_dict


def print_result(result: dict) -> None:
    print('\n' + '═' * 62)
    print(f"  STATUS: {result['status']}")
    print('═' * 62)

    if result['status'] == 'NEEDS_INPUT':
        print('\n  Additional information needed:')
        for q in result['questions']:
            print(f'    • {q}')
        return

    if result['primary_path']:
        print(f"\n  PRIMARY PATH:\n    {result['primary_path']}")

    if result.get('certifications'):
        print('\n  CERTIFICATIONS YOU LIKELY QUALIFY FOR:')
        for cert in result['certifications']:
            print(f"    ★ {cert['name']}")
            print(f"      Scope: {cert['scope']}")
            print(f"      Certifier: {cert['certifier']}")
            if cert.get('note'):
                print(f"      Note: {cert['note']}")

    if result['next_action']:
        print(f"\n  NEXT ACTION:\n    {result['next_action']}")

    if result['key_resources']:
        print('\n  KEY RESOURCES:')
        for r in result['key_resources']:
            print(f'    • {r}')

    if result['secondary_options']:
        print('\n  ADDITIONAL OPTIONS:')
        for opt in result['secondary_options']:
            print(f'    • {opt}')

    if result['notes']:
        print('\n  IMPORTANT NOTES:')
        for note in result['notes']:
            print(f'    ⚑ {note}')

    if result['flags']:
        print(f"\n  FLAGS: {', '.join(result['flags'])}")

    print('\n' + '═' * 62)


def interactive_intake() -> dict:
    print('\nBUSINESS & OPPORTUNITY INTAKE — SQUAD BAT')
    print('─' * 44)

    payload = {}

    print('\nDISCHARGE STATUS:')
    print('  1. Honorable')
    print('  2. General (Under Honorable Conditions)')
    print('  3. Other Than Honorable (OTH)')
    print('  4. Dishonorable')
    print('  5. Unknown')
    dc = input('Select [1-5]: ').strip()
    payload['discharge'] = {'1':'honorable','2':'general','3':'other_than_honorable','4':'dishonorable','5':'unknown'}.get(dc,'unknown')

    payload['service_connected_disability'] = input('\nDo you have a service-connected disability? (y/n): ').strip().lower() == 'y'
    if payload['service_connected_disability']:
        r = input('Disability rating (0-100, or Enter to skip): ').strip()
        if r.isdigit():
            payload['disability_rating'] = int(r)

    print('\nWHERE ARE YOU IN BUSINESS?')
    print('  1. Just an idea — haven\'t started yet')
    print('  2. Startup — recently launched')
    print('  3. Existing business — already operating')
    stage = input('Select [1-3]: ').strip()
    payload['business_stage'] = {'1':'idea','2':'startup','3':'existing'}.get(stage,'idea')

    print('\nWHAT DO YOU NEED? (enter numbers separated by spaces)')
    print('  1. Get certified (VOSB/SDVOSB)')
    print('  2. Federal contracting')
    print('  3. Financing / SBA loans')
    print('  4. GSA surplus / auction access')
    print('  5. Mentorship / startup resources')
    print('  6. State programs (Colorado)')
    needs = input('Select [e.g. 1 2 4]: ').strip().split()
    need_map = {'1':'certification','2':'contracting','3':'financing','4':'surplus_access','5':'mentorship','6':'state_programs'}
    payload['need_branches'] = [need_map[n] for n in needs if n in need_map]

    loc = input('\nState (e.g. CO): ').strip()
    if loc: payload['state'] = loc.upper()
    county = input('County (optional): ').strip()
    if county: payload['county'] = county

    payload['owns_51_percent'] = input('\nDo you own 51% or more of the business? (y/n, default y): ').strip().lower() != 'n'
    payload['controls_operations'] = input('Do you control day-to-day operations? (y/n, default y): ').strip().lower() != 'n'

    return payload


def main():
    parser = argparse.ArgumentParser(description='SQUAD BAT Business & Opportunity Division CLI')
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

    result = route_to_dict(payload)
    if args.raw:
        print(json.dumps(result, indent=2))
    else:
        print_result(result)


if __name__ == '__main__':
    main()
