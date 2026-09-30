# Phase 7 Content Quality Review Report

## Executive Summary
A comprehensive review of pipeline output quality identified content-quality bugs that bypassed basic format checks. In accordance with strict test-first methodology, failing test suites were authored in `tests/test_engine.py` (`TestPhase7QualityReview`) before implementing backend fixes. Thresholds were intentionally not lowered to force arbitrary answers; success is defined as genuine, helpful plans or a justified `no_match`.

Key quality upgrades implemented:
1. **Relevance Gate & Salient Symptom Verification**: Raised `REL_THRESHOLD` from `0.20` to `0.35` and implemented salient symptom term extraction (`extract_salient_symptoms` and `section_has_symptom`). Irrelevant articles (e.g. multi-window tutorials, screen mirroring, camera flicker) paired with distinct hardware or screen-blanking queries now reliably return `no_match`.
2. **Deeplink Retrieval & Catalog Validation Copying**: Fixed RRF score dampening by normalizing RRF scores against theoretical maximum ($2 / (k + 1)$). Enhanced deeplink search query aggregation to prioritize specific navigation targets (`Navigation bar`, etc.). Row 21 resolves to `DL-0169` and copies the catalog `validation` object verbatim to `validationDeeplink`.
3. **Step Ordering & Quality Formatting**:
   - Fixed conditional sub-step inversion in `extract_instructions` so device-specific instructions ("On devices with...") appear after their parent setup steps rather than before them.
   - Cleaned step text to imperative sentence case ending in a period, strictly under 25 words per atomic step.
   - Action names cleaned of trailing conjunctions, prepositions, and articles; unified duplicates in `app/pipeline.py`. Differentiated "Clear Email App Cache" from "Clear Email App Data".
4. **Strict Critical Category Restriction**: Constrained `critical` category assignment to truly irreversible or system-level actions (factory reset, wipe cache partition, network reset, restart device, software update, clear data). Touch sensitivity adjustments and display settings are correctly categorized as `manual` or `auto`.
5. **Brand and Model Canonicalization**: Normalized model numbers and brand names (`TechCorp A15G`, `Nexa Fold X1`, `Nexa A14`, etc.) into generic device terms in `canonicalize_query`, ensuring robust cross-model semantic cache hits.

---

## Complete Row-by-Row Verdicts & Justifications

| Row ID | Best Score | Verdict | SIIS Article Title | Justification |
| :--- | :---: | :---: | :--- | :--- |
| **row_1** | 0.60 | **ANSWER** | Email server not responding on smartphone or tablet | Query describes Gmail crashing to a blank screen on launch; article provides actionable steps to clear email app cache/data and test in safe mode. |
| **row_2** | 0.46 | **ANSWER** | Blank or black display on a smartphone or tablet | Query reports screen going blank/white across multiple apps; article provides physical inspection and boot checks. |
| **row_3** | 0.66 | **ANSWER** | Some things to check first | Query reports black screen blocking data transfer; article provides hardware navigation setup (USB OTG mouse/keyboard). |
| **row_4** | 0.58 | **ANSWER** | Blank or black display on a smartphone or tablet | Query reports screen suddenly went black; article provides forced power-on and battery diagnostic steps. |
| **row_5** | 0.52 | **ANSWER** | Transfer Secure folder with Data Transfer | Query describes tablet screen remaining blank during QR code scan for data transfer; article provides manual app launch and wireless transfer steps. |
| **row_7** | N/A | **NO_MATCH** | Use Multi window and App pairs on your smartphone or tablet | Article only covers multitasking / app pairs, failing to address the query's frozen dark screen and unclickable app icons. |
| **row_8** | N/A | **NO_MATCH** | Screen mirroring to your TechCorp TV | Article details Smart View TV projection; query is about the phone's physical display failing to expand to full size. |
| **row_9** | 0.37 | **ANSWER** | Access your smartphone's data if the screen does not respond | Query involves folding phone inner screen failure while cover screen works; article provides HDMI adapter and mouse recovery steps. |
| **row_10** | N/A | **NO_MATCH** | Screen flickers when using the Camera on a smartphone | SIIS article covers camera shutter speed lighting flicker; query describes physical hinge opening causing complete screen blackout. |
| **row_11** | 0.51 | **ANSWER** | Some things to check first | Query describes half-black/half-working screen; article provides peripheral access steps to retrieve data and navigate. |
| **row_12** | N/A | **NO_MATCH** | Use Multi window and App pairs on your smartphone or tablet | Article describes split-screen multitasking; query asks to remove an accessibility floating shortcut circle. |
| **row_13** | 0.58 | **ANSWER** | Blank or black display on a smartphone or tablet | Query describes blank screen after carrier reactivation; article provides charging and power recovery procedures. |
| **row_14** | 0.56 | **ANSWER** | Cracked or bleeding screen on smartphone or tablet | Query reports cracked screen; article provides authorized walk-in/mail-in repair scheduling guidance. |
| **row_15** | 0.57 | **ANSWER** | Blank or black display on a smartphone or tablet | Query reports blue/black screen with tiny text refusing to boot; article provides force restart and charging verification. |
| **row_16** | 0.43 | **ANSWER** | Blank or black display on a smartphone or tablet | Query reports screen flashes when plugging in charger; article provides charging port and connector pin inspection steps. |
| **row_17** | 0.66 | **ANSWER** | Some things to check first | Query reports blank screen with scrolling preventing data transfer; article provides peripheral keyboard/mouse connection steps. |
| **row_19** | 0.56 | **ANSWER** | Cracked or bleeding screen on smartphone or tablet | Query reports folding phone hinge crease crack; article provides repair service options. |
| **row_20** | N/A | **NO_MATCH** | Screen does not rotate on smartphone or tablet | Article explains auto-rotate and orientation lock; query reports physical/graphical screen distortion upon unboxing. |
| **row_21** | 0.47 | **ANSWER** | Touchscreen issues on a smartphone or tablet | Query reports delayed touch input and laggy responsiveness; article provides navigation bar gesture adjustment, safe mode, and device restart. |
| **row_22** | 0.43 | **ANSWER** | Blank or black display on a smartphone or tablet | Query reports screen is black while phone rings and powers on; article provides hard reboot and physical damage checks. |

---

## Detailed Justification for Key Rows

### Row 1: Explicit Justification (`ANSWER`, Score: 0.60)
- **User Query**: `1. My TechCorp A15G tablet screen flashes and then goes completely blank whenever I tap to open an email in Gmail, and after it works for a short time it goes blank again.`
- **Salient Symptoms**: `['email', 'gmail', 'flash', 'blank']`
- **SIIS Context**: `Email server not responding on smartphone or tablet`
- **Analysis**: Although the query mentions screen flashing, the root cause is explicitly tied to opening the email client (`Gmail`). The SIIS article contains actionable sections specifically targeting email app storage glitches (`Clear the Email App's Cache and Data`) and third-party app conflicts (`Restart Your Phone in Safe Mode`).
- **Verdict**: **ANSWER**. The pipeline produces 4 well-structured actions (`auto`, `manual`, `critical`, `critical`) with settings dummy fallbacks (`voiceassist://dummy_positive`) for app cache/data, eliminating false positive catalog assignments.

### Row 5: Explicit Justification (`ANSWER`, Score: 0.52)
- **User Query**: `Tablet screen stays completely blank when I try to use Data Transfer to scan the QR code for transferring data from my phone, so the transfer can't proceed.`
- **Salient Symptoms**: `['blank', 'data transfer', 'qr code', 'scan']`
- **SIIS Context**: `Transfer Secure folder with Data Transfer`
- **Analysis**: The user cannot proceed with QR code scanning due to a blank screen during data transfer setup. The SIIS article contains explicit instructions on how to manually access and open the Data Transfer app via the Apps screen search bar (`Swipe up on the Home screen to access the Apps screen`, `Tap the Search field`, `Enter and select Data Transfer to open the app`). This provides an immediate workaround to bypass the failed automated QR link.
- **Verdict**: **ANSWER**. The pipeline extracts the `Open Data Transfer App` manual action with 0 format violations.

### Row 10: Explicit Justification (`NO_MATCH`, Score: N/A, Raw: 0.300)
- **User Query**: `My TechCorp Nexa Fold X1 screen flickers and goes blank whenever I open it, so I can't see anything or access the settings, which stops me from using the phone.`
- **Salient Symptoms**: `['blank', 'flicker', 'flickers']`
- **SIIS Context**: `Screen flickers when using the Camera on a smartphone`
- **Analysis**: The user's issue is a hardware folding hinge defect—the display flickers and blanks when physically unfolded. The SIIS article, however, discusses lighting frequency and shutter speed mismatch when recording video indoors under fluorescent bulbs (`Troubleshooting Video Flickering`). The best raw semantic score is only `0.300` (well below `REL_THRESHOLD = 0.35`). Furthermore, none of the camera troubleshooting steps address hinge opening or display blackout.
- **Verdict**: **NO_MATCH**. The pipeline correctly drops the context and returns `fallback: "no_match"`.

---

## Detailed Analysis of Required `no_match` Rows

### Row 7: Multi-Window vs. Frozen Dark Screen
- **Query**: Tablet screen stays dark; only 3 app icons lit while the rest are dark and will not open.
- **SIIS Article**: `Use Multi window and App pairs on your smartphone or tablet`
- **Failure Cause**: The article teaches how to configure split-screen app pairs and pop-up view. It has zero troubleshooting guidance for an unresponsive OS launcher or selective backlight failure. The salient symptom check flags missing terms (`dark`, `won't open`, `nothing loads`), preventing false positive plan extraction.

### Row 8: TV Screen Mirroring vs. Small Phone Display
- **Query**: Phone main screen stays small and does not fill the display; cannot expand to full size.
- **SIIS Article**: `Screen mirroring to your TechCorp TV`
- **Failure Cause**: The article instructs on connecting via Smart View to an external television. It does not address the phone's native aspect ratio or one-handed mode glitch. Salient symptom `doesn't fill` is absent from the TV mirroring guide. Correctly rejected.

### Row 12: Multi-Window Pop-up vs. Floating Shortcut Circle
- **Query**: Floating circle constantly hovers on screen giving quick shortcuts (Assistant Menu); user wants to remove it.
- **SIIS Article**: `Use Multi window and App pairs on your smartphone or tablet`
- **Failure Cause**: The article covers creating multi-window pairs. The floating circle is the accessibility Assistant Menu, which is completely unmentioned in the multi-window guide. Rejected due to absence of salient terms (`floating circle`, `hover`).

### Row 20: Auto-Rotate Settings vs. Distorted Unboxed Display
- **Query**: Screen looks distorted right after receiving the new phone; user requests diagnostic test.
- **SIIS Article**: `Screen does not rotate on smartphone or tablet`
- **Failure Cause**: The article solely covers auto-rotate locks and orientation settings. It contains no guidance on graphical distortion or display panel hardware diagnostics. Salient symptom `distorted` has zero overlap with rotation settings. Correctly rejected.

---

## Deeplink & Step Formatting Verification

### Row 21 Deeplink Resolution (DL-0169)
- **Resolved Deeplink**: `voiceassist://masked/act/2f3dd95259`
- **Original Type**: `onClickURL`
- **Message**: `View Navigation bar`
- **Description**: `Opens the navigation bar settings page in device Settings on the device.`
- **Validation Deeplink**:
  ```json
  {
    "deeplink": "voiceassist://masked/val/d8310c1b7d",
    "key": "Navigation bar"
  }
  ```
- **Ordering**: The outer navigation step precedes the sub-step:
  1. `Navigate to and open Settings.`
  2. `Tap Display.`
  3. `Tap Navigation bar.`
  4. `Select Buttons to turn off full screen gestures.`

---

## Evaluation Benchmark Summary

- **Total Test Suite**: 64 passed in 7.27s (`pytest tests/`)
- **Plan Generation Recall**: 15/20 (75.0% - exactly 15 valid plans and 5 justified no_match fallbacks)
- **URL Leak Rate**: 0.0% (0 leaks across all responses)
- **Catalog URI Violations**: 0 (all actionable deeplinks exist in catalog)
- **Description & Title Word Violations**: 0
- **Category Order Violations**: 0 (strictly `auto` -> `manual` -> `critical`)
- **Manual Action Deeplink Violations**: 0
- **P95 Cold Latency**: 592.60 ms
- **P95 Warm Cache Hit Latency**: 7.76 ms (SLA <= 300 ms)
- **Paraphrase Semantic Hit Rate**: 89.4% (177/198 hits across variations)
