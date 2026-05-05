# Firebase Integration — Analysis & Roadmap

## What This Document Covers

This document analyzes the options for connecting SQUAD to Firebase so the project can be developed as a mobile phone application. It includes a pros/cons breakdown of each approach and the recommended path forward.

---

## Current State of SQUAD

SQUAD is currently a **Python-driven, artifact-first backend system** for veteran case navigation. Key characteristics:

- Logic lives in Python modules (`AGENTS/`, `pathfinder_cra/`, `MODULES/`)
- Data is JSON-schema-validated (case files, contracts, pipeline outputs)
- Governance and auditability are built into the design (Clerk, provenance, artifact routing)
- No mobile UI, no database server, no authentication layer
- Runs entirely as CLI / local file system operations

---

## Why Firebase

Firebase is a Google-backed platform that bundles the services a mobile app needs (auth, database, storage, notifications) without requiring you to run and maintain your own backend servers.

For SQUAD's use case (veteran case management, sensitive documentation, push alerts), Firebase provides:

| Firebase Service | SQUAD Use Case |
|---|---|
| **Firebase Auth** | Veteran / advocate login (anonymous, email/password, or Google) |
| **Cloud Firestore** | Case state, pipeline outputs, module results (replaces local JSON files) |
| **Firebase Storage** | Document uploads (DD-214, decision letters, HQS photos) |
| **Cloud Messaging (FCM)** | Deadline reminders, case status notifications |
| **Firebase Hosting** | Optional web companion (web-based intake form) |
| **Cloud Functions** | Serverless execution of existing Python pipeline modules |

---

## Option Analysis

### Option A — React Native + Firebase (Recommended)

**What it is:** Build the mobile app in React Native (JavaScript/TypeScript), connecting directly to Firebase services. Existing Python logic can be ported gradually to Firebase Cloud Functions or run server-side.

**Pros:**
- Targets iOS and Android from a single codebase
- React Native has strong Firebase support via `@react-native-firebase` (the most widely used integration library)
- Firestore's real-time sync maps naturally to case state that multiple users (veteran + advocate) may need to see simultaneously
- Firebase Auth handles the hard parts of secure login with very little code
- Existing JSON schemas (case files, Pathfinder contracts) can migrate to Firestore documents with minimal re-work
- Cloud Functions let you deploy the existing Python pipeline modules as serverless endpoints — no rewrite required immediately
- Firebase's free tier (Spark) is generous for a low-volume nonprofit use case

**Cons:**
- React Native adds a JavaScript/TypeScript layer; team must be comfortable in both Python (for pipeline logic) and JS (for the app)
- Python Cloud Functions require a bit of extra Firebase setup (Python runtime is supported but less common than Node.js for Cloud Functions)
- Firestore is a NoSQL document database — the current flat JSON file approach maps well, but complex queries require careful schema design up front

**Verdict:** Best all-around path given SQUAD's design (JSON-first, module-driven, offline-capable artifacts).

---

### Option B — Flutter + Firebase

**What it is:** Build the mobile app in Flutter (Dart language), using FlutterFire plugins.

**Pros:**
- Flutter produces highly performant, native-feel UIs on iOS, Android, and web from one codebase
- FlutterFire is well-maintained and fully featured
- Excellent Material Design / government-document UI patterns out of the box

**Cons:**
- Dart is a third language added to a repo already using Python and JSON/PowerShell — steeper onboarding
- Less reuse of existing JS ecosystem tooling

**Verdict:** Good option if you prioritize UI quality and performance over code-language consistency.

---

### Option C — Expo (React Native managed workflow) + Firebase

**What it is:** Expo is a managed toolchain on top of React Native. You use `expo-firebase-*` packages and Expo's build service.

**Pros:**
- Fastest way to get from zero to a running app on a real phone (no Xcode or Android Studio required for initial development)
- `eas build` handles iOS/Android compilation in the cloud
- Good for rapid prototyping

**Cons:**
- Managed workflow limits native module access; you eventually "eject" when you need full control
- Firebase integration via Expo has some limitations compared to bare React Native

**Verdict:** Best for a quick prototype or demo. Use Option A (bare React Native) once past prototype.

---

### Option D — Keep Python, Add Firebase Admin SDK

**What it is:** Keep the current CLI-based system, but add Firebase as the persistence and notification layer (no mobile UI yet). The existing Python scripts write to Firestore instead of local JSON files.

**Pros:**
- Smallest initial code change to this repo
- Can be done incrementally without touching the module logic
- Firebase Admin SDK for Python is well-supported

**Cons:**
- Does not produce a phone app — just moves the backend to the cloud
- Veterans/advocates would still need another front-end to interact with the system

**Verdict:** A useful intermediate step (Phase 1 backend migration), but not the end goal.

---

## Recommended Path Forward

```
Phase 1 (Now): Firebase project setup + backend wiring  ← CURRENT STATE
  ├── Create Firebase project in Firebase Console
  ├── firebase.json, .firebaserc, firestore.rules, storage.rules — DONE ✅
  ├── Install Firebase Admin SDK for Python
  └── Wire OUTPUTS/RUNS writes to Firestore (case records)

Phase 2: Mobile app scaffold
  ├── Scaffold React Native app in mobile/ directory
  ├── Connect @react-native-firebase/app + auth + firestore
  ├── Implement intake form (maps to Pathfinder contract schema)
  ├── Implement case dashboard (reads from Firestore)
  └── Add hosting section back to firebase.json pointing at mobile/web-build

Phase 3: Pipeline as Cloud Functions
  ├── Deploy Python pipeline modules as Firebase Cloud Functions (Python runtime)
  ├── Mobile app triggers functions instead of running CLI
  ├── Outputs written back to Firestore, push notification sent via FCM
  └── Add functions section back to firebase.json

Phase 4: Production hardening
  ├── Refine Firebase Security Rules as needed
  ├── Offline support (Firestore offline persistence)
  └── App Store / Google Play submission via EAS Build
```

---

## Current Deployment State

**What `firebase deploy` will deploy right now:**

| Service | Status | Notes |
|---|---|---|
| Firestore rules | ✅ Ready | Per-user case isolation; backend-only writes for run artifacts |
| Firestore indexes | ✅ Ready | No custom indexes required yet |
| Storage rules | ✅ Ready | Per-user file isolation under `cases/{uid}/` |
| Cloud Functions | ⏳ Phase 3 | `functions/` not scaffolded yet |
| Hosting | ⏳ Phase 2 | `mobile/web-build` not built yet |

**To deploy Phase 1 now:**
```bash
npm install -g firebase-tools
firebase login
firebase deploy --only firestore,storage
```

---

## Will This Work?

**Yes, with the right sequencing.** The SQUAD architecture is well-suited to Firebase because:

1. It is already JSON-schema-driven — Firestore stores JSON documents natively
2. Every meaningful action produces a saved artifact — Firestore gives you that cloud-persisted artifact store
3. The module boundaries (Legitimacy → Gate → HQS → Outreach) map cleanly to Cloud Function endpoints
4. Governance guardrails live in Python and JSON config files that do not need to change

The main work is building the mobile UI layer and deploying the Python pipeline as Cloud Functions. The core logic does **not** need to be rewritten.

---

## Files Added by This Integration

| File | Purpose |
|---|---|
| `firebase.json` | Firebase project configuration (Firestore + Storage; Functions/Hosting added in later phases) |
| `.firebaserc` | Firebase project alias — update `squad-app` to your actual Firebase project ID |
| `firestore.rules` | Firestore security rules (per-user case isolation) |
| `firestore.indexes.json` | Firestore index configuration |
| `storage.rules` | Storage security rules (per-user file isolation) |
| `DOCS/FIREBASE_INTEGRATION.md` | This document |

---

## Next Steps

1. **Create a Firebase project** at [console.firebase.google.com](https://console.firebase.google.com) (project name: `squad-app` or similar)
2. **Update `.firebaserc`** — replace `squad-app` with your actual Firebase project ID
3. **Install Firebase CLI**: `npm install -g firebase-tools` then `firebase login`
4. **Deploy Phase 1**: `firebase deploy --only firestore,storage`
5. **Scaffold the mobile app** in `mobile/` using React Native + `@react-native-firebase` (Phase 2)
