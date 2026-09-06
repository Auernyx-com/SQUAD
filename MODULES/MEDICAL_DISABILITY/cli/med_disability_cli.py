#!/usr/bin/env python3
"""
med_disability_cli.py
SQUAD BAT — Medical & Disability Division CLI

Usage:
  python med_disability_cli.py '{"va_status": "enrolled_no_rating", "discharge": "honorable"}'
  python med_disability_cli.py --file intake.json
  python med_disability_cli.py --interactive
"""

import argparse
import json
import sys
import os

# Allow import from parent src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from med_disability_router import route_to_dict


def print_result(result: dict) -> None:
    print("\n" + "═" * 60)
    print(f"  STATUS: {result['status']}")
    print("═" * 60)

    if result["status"] == "NEEDS_INPUT":
        print("\n  Additional information needed:")
        for q in result["questions"]:
            print(f"    • {q}")
        return

    if result["primary_path"]:
        print(f"\n  PRIMARY PATH:\n    {result['primary_path']}")

    if result["next_action"]:
        print(f"\n  NEXT ACTION:\n    {result['next_action']}")

    if result["key_forms"]:
        print("\n  KEY FORMS:")
        for f in result["key_forms"]:
            print(f"    • {f}")

    if result.get("key_resources"):
        print("\n  LOCAL RESOURCES:")
        for r in result["key_resources"]:
            print(f"    • {r}")

    if result["secondary_options"]:
        print("\n  SECONDARY OPTIONS:")
        for opt in result["secondary_options"]:
            print(f"    • {opt}")

    if result["notes"]:
        print("\n  NOTES:")
        for note in result["notes"]:
            print(f"    ⚑ {note}")

    if result["flags"]:
        print(f"\n  FLAGS: {', '.join(result['flags'])}")

    print("\n" + "═" * 60)


def interactive_intake() -> dict:
    print("\nMEDICAL & DISABILITY INTAKE — SQUAD BAT")
    print("─" * 40)

    payload = {}

    # Qualification gate first
    print("\nDISCHARGE STATUS (determines qualification):")
    print("  1. Honorable")
    print("  2. General (Under Honorable Conditions)")
    print("  3. Other Than Honorable (OTH)")
    print("  4. Dishonorable")
    print("  5. Unknown / Not sure")
    dc = input("Select [1-5]: ").strip()
    discharge_map = {
        "1": "honorable", "2": "general",
        "3": "other_than_honorable", "4": "dishonorable", "5": "unknown"
    }
    payload["discharge"] = discharge_map.get(dc, "unknown")

    # VA enrollment status
    print("\nVA STATUS:")
    print("  1. Not enrolled in VA healthcare")
    print("  2. Enrolled but no disability rating")
    print("  3. Have a disability rating")
    print("  4. Rated at 100% (Permanent & Total)")
    va = input("Select [1-4]: ").strip()
    va_map = {
        "1": "not_enrolled", "2": "enrolled_no_rating",
        "3": "has_rating", "4": "100_percent_PT"
    }
    payload["va_status"] = va_map.get(va, "not_enrolled")

    # Disability rating if applicable
    if payload["va_status"] in ("has_rating", "100_percent_PT"):
        rating_str = input("\nCurrent disability rating (0–100, or press Enter to skip): ").strip()
        if rating_str.isdigit():
            payload["disability_rating"] = int(rating_str)

    # Need branches
    print("\nWhat do you need help with? (enter numbers separated by spaces)")
    print("  1. Healthcare enrollment")
    print("  2. File initial disability claim")
    print("  3. Increase current rating")
    print("  4. Appeal a denial")
    print("  5. Mental health / PTSD / TBI / MST")
    print("  6. Caregiver support")
    print("  7. Can't work due to service-connected conditions (TDIU)")
    need_input = input("Select [e.g. 1 3]: ").strip().split()
    need_map = {
        "1": "healthcare_enrollment", "2": "initial_claim",
        "3": "increase_claim", "4": "appeal",
        "5": "mental_health", "6": "caregiver",
        "7": "tdiu"
    }
    payload["need_branches"] = [need_map[n] for n in need_input if n in need_map]

    # Mental health specifics
    if "mental_health" in payload["need_branches"]:
        payload["ptsd"] = input("\nPTSD? (y/n): ").strip().lower() == "y"
        payload["tbi"] = input("TBI? (y/n): ").strip().lower() == "y"
        payload["mst"] = input("Military Sexual Trauma (MST)? (y/n): ").strip().lower() == "y"

    # Caregiver
    if "caregiver" in payload["need_branches"]:
        payload["caregiver_need"] = True

    # Appeal specifics
    if "appeal" in payload["need_branches"]:
        payload["recent_denial"] = input("\nDenied within the last year? (y/n): ").strip().lower() == "y"
        payload["has_new_evidence"] = input("Do you have new evidence (new diagnosis, nexus letter, buddy statement)? (y/n): ").strip().lower() == "y"

    # TDIU
    if "tdiu" in payload["need_branches"]:
        payload["unemployable"] = True

    # Dependents
    payload["has_dependents"] = input("\nDo you have dependents (spouse, children)? (y/n): ").strip().lower() == "y"

    # P&T
    if payload["va_status"] == "100_percent_PT":
        payload["permanent_total"] = True

    # Location
    loc = input("\nState and county (e.g. 'Mesa County, CO') or press Enter to skip: ").strip()
    if loc:
        payload["location"] = loc

    return payload


def main():
    parser = argparse.ArgumentParser(description="SQUAD BAT Medical & Disability Division CLI")
    parser.add_argument("payload", nargs="?", help="JSON payload string")
    parser.add_argument("--file", "-f", help="Path to JSON intake file")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive intake mode")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")
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


if __name__ == "__main__":
    main()
