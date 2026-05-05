# Veteran Data Sovereignty — Law v1

**The veteran owns their data. SQUAD Battalion does not.**

## The Law

SQUAD Battalion exists to help veterans navigate the VA. It does not collect, retain, analyze, or profit from veteran information in any form. The veteran's privacy belongs to them. This platform exists to protect it, not to extract value from it.

## What this means in practice

**The Vault**
- Veteran data lives in one place: the veteran's encrypted vault
- The veteran holds the encryption key — derived from their recovery passphrase, never stored by SQUAD Battalion
- SQUAD Battalion has no copy of the key. No escrow. No recovery backdoor.

**Recovery passphrase**
- At vault creation the veteran sets a passphrase in their own words — a sentence, a phrase, something personally meaningful to them
- Minimum 5 syllables. No maximum.
- Example structure only: "I pledge allegiance to Baker Company" — the veteran writes their own
- The passphrase feeds a key derivation function. The phrase itself is never transmitted or stored anywhere
- If the veteran loses access, they recover using their passphrase. That is the only recovery path.
- SQUAD Battalion cannot unlock a veteran's vault. This is by design.

**Ephemeral processing**
- When a veteran authorizes an operation, only the minimum required fields are retrieved from the vault for that instance
- When the operation completes, the working copy is destroyed
- Nothing from that retrieval persists in logs, receipts, AI context, or system memory

**What is never stored anywhere outside the vault**
- SSN or military ID numbers
- Medical history, diagnoses, treatment records
- Disability ratings
- Financial account information
- Service records beyond what the veteran explicitly provides for a specific operation

**What the system records**
- Operation type and outcome only — never the data that informed it
- "HQS pre-screen completed — result: PASS_LIKELY" is recorded
- The address, veteran identity, and housing history that produced that result are not

**Aggregate data**
- Anonymized population-level outcome statistics are permitted — completion rates, common blocking stages, Division referral volumes
- These contain no individual identifiers and cannot be used to identify any veteran
- Every veteran is informed this data exists and may opt out at any time, no explanation required
- If anonymity is ever compromised in any form, data collection stops immediately and completely
- No exceptions. No grace period.

**What is never permitted**
- Behavioral analytics or session profiling
- Data sharing with third parties under any circumstances
- Use of veteran data to train models or improve any external system
- Re-identification of aggregate data
- Any analytics that require individual records

## Why

Veterans are a high-value target for identity theft. They carry military IDs, SSNs tied to service records, disability ratings, benefit payment streams, and security clearances. They navigate systems where sharing sensitive information is required — and bad actors exploit that exact moment of necessity.

This platform was built by a veteran who experienced the gaps firsthand and by an operator who experienced what targeted infrastructure compromise looks like. The security model is not theoretical.

The VA system is already confusing enough to be weaponized against the people it's supposed to serve. SQUAD Battalion does not add to that attack surface. It reduces it.

## The test

Before any feature is built, ask:
- Does this require storing veteran data outside the vault?
- Does this create a copy of veteran data anywhere?
- Could a full breach of SQUAD Battalion's infrastructure expose veteran information?
- Does this compromise the anonymity of aggregate data?

If any answer is yes — the feature does not ship in that form.

---

**Authority:** Justin Hughes — Founder, Auernyx / SQUAD Battalion
**Status:** Founding law — cannot be weakened by any future decision without explicit founder authorization
**Version:** v1 — 2026-05-05
