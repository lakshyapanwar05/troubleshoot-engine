# Data Notes — Smart Guided Troubleshooting Engine

## 1. Data File Structures

### deeplinks.json
- Top-level keys: `_readme`, `count` (578), `deeplinks` (array)
- Each entry: `id`, `deeplink`, `description`, `message`, `originalType`, `control_type`, `qna_description`, `validation`
- `validation` is either `null` or `{deeplink, key}` (basic) or `{deeplink, key, resultType, condition, value}` (full)
- **originalType distribution**: `onClickURL`: 254, `offURL`: 138, `onURL`: 138, `updateURL`: 36, `null`: 11, `placeholder`: 1
- **Dummy entry**: `DL-DUMMY`, `voiceassist://dummy_positive`, placeholder type
- **TV entries**: 18 entries mention "TV" in description/message — must be excluded unless query mentions TV

### siis_responses.json
- Top-level keys: `_readme`, `count` (20), `responses` (array)
- Each entry: `id`, `original_query`, `siis_response: {title, content}`
- Row IDs: row_1 through row_22 (skips 6, 18; row_7=line6, row_8=line7, etc.)
- Content is markdown-ish: preamble `Category,... Title ( Categories): `, then `#`/`##`/`###` headings, `## Step N:` sections, bullet-like instructions
- Content sizes vary from ~500 bytes (row_14 cracked screen) to ~9 KB (row_7/row_12 Multi window)

### input.txt
- 20 lines (line 21 is blank), one query per line
- Lines 16-17 have numbered prefixes and quotes: `1. "..."` and `1. "..." 2. "..." 3. "..."`
- Line 17 is multi-intent (3 numbered complaints)

### sample_output.json
- Shows the envelope shape: `{query, response: {contexts: [Goal]}}`
- Action descriptions are 9-10 words (spec says 5-7 — follow spec, not sample)
- Uses `voiceassist://` URIs (not `bixby://`)

### schema.py
- Pydantic v2 models: `BaseDeeplink`, `Deeplink`, `Condition`, `ResultTypes`, `actionCategory`, `ValidationDeepLink`, `StepGroup`, `Action`, `Goal`, `ContextDeeplinkResponse`
- `Deeplink` has optional `classes` field (dict) and optional `originalType`
- `Action.category` defaults to `manual`

## 2. Query-SIIS Mismatches (Relevance Gate Needed)

| Row | Query Topic | SIIS Title | Match? |
|-----|------------|------------|--------|
| row_1 | Tablet screen flashes/blank in Gmail | Email server not responding | **MISMATCH** — email troubleshooting, not screen display |
| row_5 | Blank screen during Data Transfer QR scan | Transfer Secure folder with Data Transfer | **PARTIAL** — transfer article, not blank screen fix |
| row_7 | Screen stays dark, 3 app icons lit | Multi window and App pairs | **MISMATCH** — multi-window feature, not screen darkness |
| row_8 | Screen stays small, won't fill display | Screen mirroring to TechCorp TV | **MISMATCH** — TV mirroring, not screen size issue |
| row_10 | Screen flickers/blank when opened (Fold) | Screen flickers when using Camera | **PARTIAL** — camera flicker, not general screen flicker |
| row_12 | Floating circle/shortcuts to remove | Multi window and App pairs | **MISMATCH** — multi-window feature, not floating assistant |
| row_20 | Distorted screen, needs diagnostic | Screen does not rotate | **MISMATCH** — rotation troubleshooting, not distortion |

These rows should return `no_match` via the relevance gate.

## 3. Rows That Should Produce Valid Plans

| Row | Query Topic | SIIS Title | Notes |
|-----|------------|------------|-------|
| row_2 | Blank/white screen in apps | Blank or black display | Good match |
| row_3 | Black screen, can't transfer data | Some things to check first | Partial — has USB mouse/force restart content |
| row_4 | Screen went black after month | Blank or black display | Good match |
| row_9 | Inner screen stopped, cover works | Access data if screen doesn't respond | Good match |
| row_11 | Half black display (Fold) | Some things to check first | Partial match |
| row_13 | Blank screen after carrier deactivation | Blank or black display | Good match |
| row_14 | Cracked screen, can't use device | Cracked or bleeding screen | Good match |
| row_15 | Blue/black screen, won't start | Blank or black display | Good match |
| row_16 | Screen flashes when charging | Blank or black display | Partial match (charging related) |
| row_17 | Blank screen, can't transfer data | Some things to check first | Partial match |
| row_19 | Multi-intent: cracked+touch+display | Cracked or bleeding screen | Good match (3 sub-queries) |
| row_21 | Touch delayed/laggy | Touchscreen issues | Good match |
| row_22 | Black screen, phone works otherwise | Blank or black display | Good match |

## 4. Embedding Model
- Located at `models/minilm/` — `sentence-transformers/all-MiniLM-L6-v2`
- ~90 MB safetensors, tokenizer present
- Must be loaded from local path, never downloaded

## 5. Observations
- Row IDs skip 6 and 18 (20 rows total: 1-5, 7-17, 19-22)
- Several SIIS documents contain corrupted/run-together text (e.g., row_3 "Security and privacy > Screen lock and biometrics,and then enteryourcurrentpin...")
- The "Some things to check first" article (rows 3, 11, 17) has multiple unrelated sections (Fingerprint, Kids PIN, Device Locked, Third-Party Keyboard)
- Multi-intent query is row_19 (line 17): 3 numbered complaints about cracked screen, touch not working, display visibility
