# HUD-VASH / HCV / Section 8 Program Gate (v1)

This workspace contains a single authoritative module that normalizes voucher inputs, computes gross rent/tenant share estimates, applies hard program gates (40% initial lease-up cap + off-book side payments), and emits a standardized output plus an auto-generated “Ask PHA” question set when required inputs are unknown.

Key knobs added for real-world use:

- `approvalBedroomCapSize`: bedroom size used for payment standard / utility allowance lookup (studio->0, 1BR+->1)
- `rentReasonablenessPolicy`: `FLAG_ONLY` (default) | `PENDING_IF_HIGH` | `HARD_FAIL_IF_HIGH`

## Files

- `ProgramGate_HUDVASH_HCV_S8.py` — core module + minimal demo
- `PHAOverrides_TEMPLATE.json` — template for local PHA overrides (store local policy/data here, not in code)

## Quick run

From PowerShell in this folder:

- Run the demo: `python .\ProgramGate_HUDVASH_HCV_S8.py`

If you want to call it from other code, import `ProgramGateInput`, `UtilityResponsibility`, and `run_program_gate`.
