/**
 * ================================================================
 * SMART GUIDED TROUBLESHOOTING ENGINE — script.js
 * Phase 2: API Integration + Dynamic Rendering
 *
 * What changed from Phase 1:
 *   ✅ sendQuery()      — real async fetch POST to /troubleshoot
 *   ✅ displayCategories()  — renders categories from API response
 *   ✅ displayExplanation() — renders keywords + confidence score
 *   ✅ displaySteps()       — renders all steps with deep links
 *   ✅ showError()          — graceful error banner on API failure
 *   ✅ handleResponse()     — central response dispatcher
 *
 * Phase 3 hooks (not yet active):
 *   → renderStep() one-by-one for adaptive flow
 * Phase 4 hooks (not yet active):
 *   → self-healing badge, XAI reasoning text
 * ================================================================
 */

/* -------------------------------------------------------
   APP STATE
   Central state object. In Phase 2+ this will hold
   backend responses, step progress, session ID, etc.
------------------------------------------------------- */
const AppState = {
  currentQuery: '',        // Raw query string from user
  isAnalyzing: false,     // Whether a request is in-flight
  stepsCompleted: 0,         // How many steps are marked done
  totalSteps: 0,         // Total steps in current flow
  sessionId: null,      // Phase 3+: unique session per query
  feedbackGiven: false,     // Whether user submitted feedback
  lastResponse: null,      // Phase 2: stores last API response object
};

/* -------------------------------------------------------
   DOM ELEMENT REFERENCES
   Cached at load so we don't query DOM repeatedly.
------------------------------------------------------- */
const DOM = {
  input: () => document.getElementById('issue-input'),
  charCount: () => document.getElementById('char-count'),
  submitBtn: () => document.getElementById('submit-btn'),
  statusBadge: () => document.getElementById('status-badge'),
  statusDot: () => document.getElementById('status-dot'),
  statusLabel: () => document.getElementById('status-label'),
  outputArea: () => document.getElementById('output-area'),
  analyzingPanel: () => document.getElementById('analyzing-panel'),
  panelIssues: () => document.getElementById('panel-detected-issues'),
  panelXAI: () => document.getElementById('panel-explainable-ai'),
  panelSteps: () => document.getElementById('panel-steps'),
  panelFeedback: () => document.getElementById('panel-feedback'),
  intentChips: () => document.getElementById('intent-chips'),
  intentBadge: () => document.getElementById('intent-count-badge'),
  stepsList: () => document.getElementById('steps-list'),
  stepsBadge: () => document.getElementById('step-count-badge'),
  stepsProgressRow: () => document.getElementById('steps-progress-row'),
  progressLabel: () => document.getElementById('progress-label'),
  progressFill: () => document.getElementById('progress-bar-fill'),
  xaiKeywords: () => document.getElementById('xai-keywords').querySelector('.xai-keywords-list'),
  xaiReasoning: () => document.getElementById('xai-reasoning-text'),
  gaugeValue: () => document.getElementById('gauge-value'),
  gaugeFill: () => document.getElementById('gauge-fill-path'),
  feedbackYes: () => document.getElementById('feedback-yes'),
  feedbackNo: () => document.getElementById('feedback-no'),
  feedbackConfirm: () => document.getElementById('feedback-confirmation'),
  feedbackConfText: () => document.getElementById('feedback-confirmation-text'),
  chips: () => document.querySelectorAll('.chip'),
  errorBanner: () => document.getElementById('error-banner'),
  errorBannerText: () => document.getElementById('error-banner-text'),
  contextTags: () => document.getElementById('context-tags-list'),
};

/* ================================================================
   CORE FUNCTION: sendQuery()  ← PHASE 2 UPGRADE
   Entry point called by the submit button's onclick handler.
   Now performs a real async POST to /troubleshoot.
   Phase 3: Add sessionId to request body for adaptive flow.
   ================================================================ */
async function sendQuery() {
  const inputEl = DOM.input();
  const query = inputEl.value.trim();

  /* Validation — don't allow empty queries */
  if (!query) {
    shakeInput();
    return;
  }

  /* Prevent duplicate in-flight requests */
  if (AppState.isAnalyzing) return;

  /* Log query for debugging */
  console.group('[Query Submitted]');
  console.log('Query:', query);
  console.log('Timestamp:', new Date().toISOString());
  console.groupEnd();

  /* Update state */
  AppState.currentQuery = query;
  AppState.isAnalyzing = true;
  AppState.feedbackGiven = false;
  AppState.lastResponse = null;

  /* UI: dismiss any prior error, clear old output, start loading */
  hideError();
  clearOutputPanels();
  setAnalyzingState(true);

  try {
    /* Call real FastAPI backend: POST /v1/troubleshoot */
    const response = await fetch('/v1/troubleshoot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      throw new Error(`Engine returned HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    console.group('[Engine Response]');
    console.log('Query:', query);
    console.log('Response:', data);
    console.groupEnd();

    AppState.lastResponse = data;
    handleResponse(data);

  } catch (err) {
    console.error('[Error]:', err);
    setAnalyzingState(false);
    showError(err.message || 'Unable to connect to troubleshooting engine.');
  }
}


/* ================================================================
   MOCK ENGINE
   Produces realistic API responses without a backend.
   getMockResponse(query) → same shape as POST /troubleshoot response.
   Remove this section entirely when the real backend is connected.
   ================================================================ */

/**
 * delay(ms)
 * Returns a Promise that resolves after `ms` milliseconds.
 * Used to simulate network latency in mock mode.
 */
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * getMockResponse(query)
 * Keyword-matches the query against topic libraries and returns
 * a full mock response object matching the /troubleshoot schema.
 *
 * @param {string} query — raw user input
 * @returns {{ categories, context, confidence, keywords, steps }}
 */
function getMockResponse(query) {
  const q = query.toLowerCase();

  /* ── Topic library ─────────────────────────────────────────────
     Each topic has: match keywords, categories, context tags,
     confidence, keyword highlights, and troubleshooting steps.
  ─────────────────────────────────────────────────────────────── */
  const topics = [

    /* 1. BATTERY */
    {
      match: ['battery', 'drain', 'charge', 'power', 'draining', 'dies quickly',
        'not charging', 'low battery', 'charging slow'],
      categories: ['battery', 'performance'],
      context: detectContext(q, ['gaming', 'overnight', 'standby', 'heating', 'background apps']),
      confidence: 0.91,
      keywords: filterKeywords(q, ['battery', 'drain', 'charging', 'power', 'gaming', 'heating']),
      steps: [
        {
          text: 'Open Battery settings and enable Battery Saver mode',
          deeplink: '/settings/battery', recommended: true
        },
        {
          text: 'Check which apps are consuming the most battery in Battery Usage',
          deeplink: '/settings/battery/usage', recommended: true
        },
        {
          text: 'Disable Always-On Display and reduce screen brightness to 50%',
          deeplink: '/settings/display', recommended: false
        },
        {
          text: 'Turn off Wi-Fi, Bluetooth, and GPS when not in use',
          deeplink: '/settings/connections', recommended: false
        },
        {
          text: 'Restrict background activity for heavy apps',
          deeplink: '/settings/apps', recommended: false
        },
      ],
    },

    /* 2. SCREEN / DISPLAY */
    {
      match: ['screen', 'display', 'flicker', 'flickering', 'brightness', 'dim',
        'black screen', 'touch', 'unresponsive', 'dead pixels', 'refresh rate'],
      categories: ['display', 'touch'],
      context: detectContext(q, ['update', 'drop', 'water', 'sunlight', 'gaming']),
      confidence: 0.88,
      keywords: filterKeywords(q, ['screen', 'flicker', 'display', 'brightness', 'touch']),
      steps: [
        {
          text: 'Restart the device and check if the issue persists',
          deeplink: null, recommended: true
        },
        {
          text: 'Adjust screen brightness and disable Auto Brightness',
          deeplink: '/settings/display/brightness', recommended: true
        },
        {
          text: 'Disable hardware overlays in Developer Options',
          deeplink: '/settings/developer', recommended: false
        },
        {
          text: 'Check for pending software or firmware updates',
          deeplink: '/settings/update', recommended: false
        },
        {
          text: 'Run Screen Diagnostics in Device Care',
          deeplink: '/settings/device-care/diagnostics', recommended: false
        },
      ],
    },

    /* 3. WI-FI / NETWORK */
    {
      match: ['wifi', 'wi-fi', 'internet', 'network', 'connection', 'disconnecting',
        'slow internet', 'no signal', 'mobile data', 'hotspot'],
      categories: ['network', 'connectivity'],
      context: detectContext(q, ['router', 'office', 'home', '5g', '4g', 'vpn']),
      confidence: 0.85,
      keywords: filterKeywords(q, ['wifi', 'internet', 'network', 'connection', 'signal', 'data']),
      steps: [
        {
          text: 'Toggle Wi-Fi off and back on, then reconnect to your network',
          deeplink: '/settings/wifi', recommended: true
        },
        {
          text: 'Forget the network and reconnect with the password',
          deeplink: '/settings/wifi/saved', recommended: true
        },
        {
          text: 'Reset network settings (Wi-Fi, Mobile, Bluetooth)',
          deeplink: '/settings/general/reset', recommended: false
        },
        {
          text: 'Check if your router firmware is up to date',
          deeplink: null, recommended: false
        },
        {
          text: 'Disable Wi-Fi power saving mode in Advanced Wi-Fi settings',
          deeplink: '/settings/wifi/advanced', recommended: false
        },
      ],
    },

    /* 4. APP CRASH */
    {
      match: ['app', 'crash', 'crashing', 'force close', 'not opening', 'freezing',
        'stuck', 'won\'t open', 'keeps closing', 'not responding'],
      categories: ['app', 'performance'],
      context: detectContext(q, ['startup', 'update', 'install', 'storage', 'background']),
      confidence: 0.89,
      keywords: filterKeywords(q, ['app', 'crash', 'freeze', 'close', 'startup', 'storage']),
      steps: [
        {
          text: 'Force stop the app and clear its cache',
          deeplink: '/settings/apps', recommended: true
        },
        {
          text: 'Check if an app update is available in the store',
          deeplink: null, recommended: true
        },
        {
          text: 'Clear app data (note: this resets app preferences)',
          deeplink: '/settings/apps', recommended: false
        },
        {
          text: 'Uninstall and reinstall the app',
          deeplink: null, recommended: false
        },
        {
          text: 'Check available storage — low storage can cause crashes',
          deeplink: '/settings/storage', recommended: false
        },
      ],
    },

    /* 5. PERFORMANCE / LAG */
    {
      match: ['slow', 'lag', 'lagging', 'performance', 'sluggish', 'heating',
        'hot', 'overheating', 'fps', 'frame drop', 'stutter'],
      categories: ['performance', 'battery'],
      context: detectContext(q, ['gaming', 'multitasking', 'ram', 'background', 'heating']),
      confidence: 0.86,
      keywords: filterKeywords(q, ['slow', 'lag', 'performance', 'heating', 'fps', 'ram']),
      steps: [
        {
          text: 'Open Device Care and run a full optimization scan',
          deeplink: '/settings/device-care', recommended: true
        },
        {
          text: 'Close background apps and free up RAM',
          deeplink: '/settings/apps/running', recommended: true
        },
        {
          text: 'Enable Game Booster for better game performance',
          deeplink: '/settings/game-booster', recommended: false
        },
        {
          text: 'Reduce screen resolution and refresh rate',
          deeplink: '/settings/display/resolution', recommended: false
        },
        {
          text: 'Check storage — under 15% free space degrades performance',
          deeplink: '/settings/storage', recommended: false
        },
      ],
    },

    /* 6. AUDIO / SOUND */
    {
      match: ['sound', 'audio', 'speaker', 'volume', 'microphone', 'no sound',
        'muted', 'distorted', 'earphone', 'headphone', 'bluetooth audio'],
      categories: ['audio', 'connectivity'],
      context: detectContext(q, ['call', 'music', 'video', 'bluetooth', 'earphones']),
      confidence: 0.83,
      keywords: filterKeywords(q, ['sound', 'audio', 'speaker', 'volume', 'microphone']),
      steps: [
        {
          text: 'Check volume levels and ensure the device is not on silent',
          deeplink: '/settings/sounds', recommended: true
        },
        {
          text: 'Disconnect Bluetooth devices that may be intercepting audio',
          deeplink: '/settings/bluetooth', recommended: true
        },
        {
          text: 'Run the Speaker Test in Device Diagnostics',
          deeplink: '/settings/device-care/diagnostics', recommended: false
        },
        {
          text: 'Clear the cache for the Media and Audio service',
          deeplink: '/settings/apps/media', recommended: false
        },
        {
          text: 'Check if a software update is available',
          deeplink: '/settings/update', recommended: false
        },
      ],
    },

    /* 7. STORAGE */
    {
      match: ['storage', 'space', 'full', 'memory', 'files', 'photos',
        'not enough space', 'internal memory', 'sd card'],
      categories: ['storage', 'performance'],
      context: detectContext(q, ['photos', 'videos', 'apps', 'downloads', 'sd card']),
      confidence: 0.87,
      keywords: filterKeywords(q, ['storage', 'space', 'memory', 'files', 'photos']),
      steps: [
        {
          text: 'Open Device Care → Storage and run a junk file cleanup',
          deeplink: '/settings/device-care/storage', recommended: true
        },
        {
          text: 'Move photos and videos to an SD card or cloud storage',
          deeplink: '/settings/storage', recommended: true
        },
        {
          text: 'Uninstall unused apps to free up space',
          deeplink: '/settings/apps', recommended: false
        },
        {
          text: 'Clear download folder and trash in the Gallery app',
          deeplink: null, recommended: false
        },
        {
          text: 'Use Smart Switch to back up and manage device storage',
          deeplink: null, recommended: false
        },
      ],
    },

    /* 8. CHARGING */
    {
      match: ['charging', 'charger', 'fast charge', 'wireless', 'not charging',
        'slow charge', 'usb', 'cable', 'power adapter'],
      categories: ['charging', 'battery'],
      context: detectContext(q, ['wireless', 'fast charging', 'usb-c', 'adapter', 'heat']),
      confidence: 0.90,
      keywords: filterKeywords(q, ['charging', 'charger', 'usb', 'cable', 'fast charge']),
      steps: [
        {
          text: 'Use the original Samsung charger and cable for best results',
          deeplink: null, recommended: true
        },
        {
          text: 'Enable Fast Charging in Battery settings',
          deeplink: '/settings/battery', recommended: true
        },
        {
          text: 'Clean the USB-C port with a dry brush or compressed air',
          deeplink: null, recommended: false
        },
        {
          text: 'Toggle Airplane mode while charging to speed up charge',
          deeplink: '/settings/connections', recommended: false
        },
        {
          text: 'Check if the charging port is damaged in Device Care',
          deeplink: '/settings/device-care/diagnostics', recommended: false
        },
      ],
    },

  ]; // end topics

  /* ── Match query against topic library ── */
  let matched = null;
  let bestScore = 0;

  for (const topic of topics) {
    const score = topic.match.filter(kw => q.includes(kw)).length;
    if (score > bestScore) {
      bestScore = score;
      matched = topic;
    }
  }

  /* ── Fallback for unrecognised queries ── */
  if (!matched || bestScore === 0) {
    matched = {
      categories: ['general'],
      context: [],
      confidence: 0.72,
      keywords: extractWords(q).slice(0, 4),
      steps: [
        {
          text: 'Restart your device — resolves most transient issues',
          deeplink: null, recommended: true
        },
        {
          text: 'Check for a software update in Settings → Software Update',
          deeplink: '/settings/update', recommended: true
        },
        {
          text: 'Run Device Care to scan for problems',
          deeplink: '/settings/device-care', recommended: false
        },
        {
          text: 'Back up your data and perform a soft reset if the issue persists',
          deeplink: '/settings/general/reset', recommended: false
        },
      ],
    };
  }

  return {
    categories: matched.categories,
    context: matched.context,
    confidence: matched.confidence,
    keywords: matched.keywords.length > 0
      ? matched.keywords
      : matched.match.slice(0, 3),
    steps: matched.steps,
  };
}

/* ── Mock helpers ─────────────────────────────────────────────── */

/**
 * detectContext(query, candidates)
 * Returns any candidate context words found in the query.
 */
function detectContext(query, candidates) {
  return candidates.filter(c => query.includes(c));
}

/**
 * filterKeywords(query, candidates)
 * Returns keyword candidates that appear in the query string.
 * Falls back to the first three candidates if none match.
 */
function filterKeywords(query, candidates) {
  const matched = candidates.filter(k => query.includes(k));
  return matched.length > 0 ? matched : candidates.slice(0, 3);
}

/**
 * extractWords(query)
 * Splits query into meaningful words (ignores short stop words).
 */
function extractWords(query) {
  const stopWords = new Set(['the', 'a', 'an', 'is', 'are', 'my', 'i', 'it',
    'and', 'or', 'but', 'not', 'in', 'on', 'at',
    'to', 'for', 'of', 'with', 'this', 'that']);
  return query
    .split(/\s+/)
    .map(w => w.replace(/[^a-z]/gi, '').toLowerCase())
    .filter(w => w.length > 2 && !stopWords.has(w));
}


/* ================================================================
   UI STATE HELPERS
   ================================================================ */


/**
 * setAnalyzingState(active)
 * Transitions UI into or out of the "analyzing" loading state.
 * - Shows/hides the animated orb panel
 * - Disables/enables submit button
 * - Updates status badge
 */
/**
 * setAnalyzingState(active)
 * Transitions UI into or out of the "analyzing" loading state.
 * - Starts/stops the revolving sun solar connector and ascending beam
 * - Shows/hides the animated orb panel
 * - Disables/enables submit button
 * - Updates status badge with solar uplink label
 */
function setAnalyzingState(active) {
  const analyzingEl = DOM.analyzingPanel();
  const submitBtn = DOM.submitBtn();
  const badgeEl = DOM.statusBadge();
  const dotEl = DOM.statusDot();
  const labelEl = DOM.statusLabel();

  AppState.isAnalyzing = active;

  if (active) {
    /* Activate revolving solar connector & energy beam */
    startSolarConnector();

    /* Show analyzing panel */
    analyzingEl.classList.add('visible');

    /* Disable submit button + show spinner */
    submitBtn.disabled = true;
    submitBtn.classList.add('loading');

    /* Update status badge to "Analyzing" style if present */
    if (badgeEl) {
      badgeEl.classList.remove('error');
      badgeEl.classList.add('analyzing');
    }
    if (dotEl) dotEl.style.background = '#FBBF24';
    if (labelEl) labelEl.textContent = 'Solar AI Connector Active...';
  } else {
    /* Stop revolving solar connector with gentle deceleration */
    stopSolarConnector();

    /* Hide analyzing panel */
    analyzingEl.classList.remove('visible');

    /* Re-enable submit button */
    submitBtn.disabled = false;
    submitBtn.classList.remove('loading');

    /* Restore status badge to "Ready" if present */
    if (badgeEl) badgeEl.classList.remove('analyzing', 'error');
    if (dotEl) dotEl.style.background = '';
    if (labelEl) labelEl.textContent = 'AI Engine Ready';
  }
}

/* ================================================================
   REVOLVING SOLAR CONNECTOR SYSTEM
   - Activates when user submits their problem query
   - Spins the sun's optical flares and orbital connector rings
   - Generates a luminous dynamic energy beam arcing from the
     chat console directly to the revolving sun
   - Uplinks photon energy pulses continuously along the curve
   ================================================================ */

let solarConnectorAnimId = null;
let solarConnectorPulseOffset = 0;

function startSolarConnector() {
  const sunEl = document.getElementById('bg-sun');
  const consoleEl = document.getElementById('lakeside-console');
  const svgEl = document.getElementById('solar-connector-svg');
  if (!sunEl || !svgEl) return;

  // 1. Activate revolving solar connector mode on sun & console
  sunEl.classList.add('processing-active');
  if (consoleEl) consoleEl.classList.add('connector-uplink');
  svgEl.classList.add('active');

  // 2. Ensure sun is elevated and visible even if at night/dusk
  ScenicState.isProcessingConnector = true;
  renderScenicFrame(ScenicState.currentMinutes);

  // 3. Start high-frequency continuous beam calculation loop
  function animateBeam() {
    if (!AppState.isAnalyzing) return;
    updateConnectorBeamGeometry();
    solarConnectorAnimId = requestAnimationFrame(animateBeam);
  }
  solarConnectorPulseOffset = 0;
  solarConnectorAnimId = requestAnimationFrame(animateBeam);
}

function stopSolarConnector() {
  const sunEl = document.getElementById('bg-sun');
  const consoleEl = document.getElementById('lakeside-console');
  const svgEl = document.getElementById('solar-connector-svg');

  if (solarConnectorAnimId) {
    cancelAnimationFrame(solarConnectorAnimId);
    solarConnectorAnimId = null;
  }

  // Gracefully fade beam and decelerate sun
  if (svgEl) svgEl.classList.remove('active');
  if (consoleEl) consoleEl.classList.remove('connector-uplink');

  setTimeout(() => {
    if (!AppState.isAnalyzing && sunEl) {
      sunEl.classList.remove('processing-active');
      ScenicState.isProcessingConnector = false;
      renderScenicFrame(ScenicState.currentMinutes);
    }
  }, 450);
}

/**
 * updateConnectorBeamGeometry()
 * Recalculates the exact cubic bezier path between the chatbox console
 * and the center of the revolving sun. Animates ascending pulse orbs.
 */
function updateConnectorBeamGeometry() {
  const consoleEl = document.getElementById('lakeside-console');
  const sunEl = document.getElementById('bg-sun');
  const glowPath = document.getElementById('connector-beam-glow');
  const corePath = document.getElementById('connector-beam-core');
  const p1 = document.getElementById('connector-pulse-1');
  const p2 = document.getElementById('connector-pulse-2');
  const p3 = document.getElementById('connector-pulse-3');

  if (!consoleEl || !sunEl || !corePath) return;

  const cRect = consoleEl.getBoundingClientRect();
  const sRect = sunEl.getBoundingClientRect();

  // Start point: top center of the lakeside chat console
  const x1 = cRect.left + cRect.width / 2;
  const y1 = cRect.top + 2;

  // End point: center of the revolving sun
  const x2 = sRect.left + sRect.width / 2;
  const y2 = sRect.top + sRect.height / 2;

  // Curved cubic bezier handles for natural, graceful energy arc
  const dx = x2 - x1;
  const dy = y2 - y1;
  const cp1X = x1 + dx * 0.15;
  const cp1Y = y1 + dy * 0.55;
  const cp2X = x2 - dx * 0.25;
  const cp2Y = y2 - dy * 0.15;

  const d = `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${cp1X.toFixed(1)} ${cp1Y.toFixed(1)}, ${cp2X.toFixed(1)} ${cp2Y.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;

  corePath.setAttribute('d', d);
  if (glowPath) glowPath.setAttribute('d', d);

  // Animate pulse dots along the cubic bezier from console (t=0) to sun (t=1)
  solarConnectorPulseOffset = (solarConnectorPulseOffset + 0.02) % 1;

  function setPulsePosition(dotEl, tOffset) {
    if (!dotEl) return;
    const t = (solarConnectorPulseOffset + tOffset) % 1;
    // Cubic Bezier formula: B(t) = (1-t)^3 P0 + 3(1-t)^2 t P1 + 3(1-t) t^2 P2 + t^3 P3
    const mt = 1 - t;
    const mt2 = mt * mt;
    const mt3 = mt2 * mt;
    const t2 = t * t;
    const t3 = t2 * t;

    const px = mt3 * x1 + 3 * mt2 * t * cp1X + 3 * mt * t2 * cp2X + t3 * x2;
    const py = mt3 * y1 + 3 * mt2 * t * cp1Y + 3 * mt * t2 * cp2Y + t3 * y2;

    dotEl.setAttribute('cx', px.toFixed(1));
    dotEl.setAttribute('cy', py.toFixed(1));
    // Fade out near the very ends
    const opacity = Math.sin(t * Math.PI);
    dotEl.setAttribute('opacity', Math.max(0.15, opacity).toFixed(2));
  }

  setPulsePosition(p1, 0.0);
  setPulsePosition(p2, 0.33);
  setPulsePosition(p3, 0.67);
}

/* ================================================================
   ERROR BANNER HELPERS
   ================================================================ */

/**
 * showError(message)
 * Displays the error banner below the input card.
 * Also sets the status badge to the error variant.
 *
 * @param {string} message — human-readable error text
 */
function showError(message) {
  /* Update status badge */
  const badgeEl = DOM.statusBadge();
  const dotEl = DOM.statusDot();
  const labelEl = DOM.statusLabel();
  if (badgeEl) badgeEl.classList.add('error');
  if (dotEl) dotEl.style.background = 'var(--brand-red)';
  if (labelEl) labelEl.textContent = 'Connection Error';

  /* Show the inline error banner */
  const banner = DOM.errorBanner();
  const bannerText = DOM.errorBannerText();
  if (bannerText) bannerText.textContent = message;
  if (banner) banner.hidden = false;

  console.error('UI Error displayed:', message);
}

/**
 * hideError()
 * Hides the error banner — called before each new sendQuery().
 */
function hideError() {
  const banner = DOM.errorBanner();
  const badgeEl = DOM.statusBadge();
  const dotEl = DOM.statusDot();
  const labelEl = DOM.statusLabel();

  if (banner) banner.hidden = true;
  if (badgeEl) badgeEl.classList.remove('error');
  if (dotEl) dotEl.style.background = '';
  if (labelEl) labelEl.textContent = 'AI Engine Ready';
}

/**
 * clearOutputPanels()
 * Resets all output panel content and hides them.
 * Called at the start of each new sendQuery().
 * In Phase 2+, this ensures stale data is cleared before
 * new results arrive.
 */
function clearOutputPanels() {
  /* Hide all four result panels */
  const panels = [
    DOM.panelIssues(),
    DOM.panelXAI(),
    DOM.panelSteps(),
    DOM.panelFeedback(),
  ];
  panels.forEach(p => { if (p) p.hidden = true; });

  /* Clear dynamic content containers */
  const intentEl = DOM.intentChips();
  if (intentEl) intentEl.innerHTML = '';

  const stepsEl = DOM.stepsList();
  if (stepsEl) stepsEl.innerHTML = '';

  const kwEl = DOM.xaiKeywords();
  if (kwEl) kwEl.innerHTML = '';

  /* Reset badge counts */
  const intentBadge = DOM.intentBadge();
  if (intentBadge) intentBadge.textContent = '0 found';

  const stepBadge = DOM.stepsBadge();
  if (stepBadge) stepBadge.textContent = '0 steps';

  /* Reset XAI fields */
  const reasoningEl = DOM.xaiReasoning();
  if (reasoningEl) reasoningEl.textContent = 'Reasoning will appear here once analysis is complete.';

  const gaugeVal = DOM.gaugeValue();
  if (gaugeVal) gaugeVal.textContent = '--';

  const gaugeFillEl = DOM.gaugeFill();
  if (gaugeFillEl) gaugeFillEl.style.strokeDashoffset = '141.4';

  /* Reset feedback state */
  AppState.stepsCompleted = 0;
  AppState.totalSteps = 0;

  const confirmEl = DOM.feedbackConfirm();
  if (confirmEl) confirmEl.hidden = true;

  const yesBtn = DOM.feedbackYes();
  const noBtn = DOM.feedbackNo();
  if (yesBtn) yesBtn.classList.remove('selected');
  if (noBtn) noBtn.classList.remove('selected');

  /* Hide progress row */
  const progressRow = DOM.stepsProgressRow();
  if (progressRow) progressRow.hidden = true;
}

/**
 * shakeInput()
 * Visual error feedback when user tries to submit empty input.
 */
function shakeInput() {
  const inputEl = DOM.input();
  inputEl.style.borderColor = 'var(--brand-red)';
  inputEl.style.animation = 'none';

  /* Trigger reflow to restart animation */
  inputEl.offsetHeight; // eslint-disable-line no-unused-expressions

  /* Inline keyframes via CSS class would be cleaner in large apps */
  inputEl.style.animation = 'shakeAnim 0.4s ease';

  setTimeout(() => {
    inputEl.style.borderColor = '';
    inputEl.style.animation = '';
  }, 600);

  inputEl.focus();
}

/* ================================================================
   PHASE 2: RESPONSE DISPATCHER
   handleResponse() receives the parsed API JSON and routes
   each field to its dedicated display function.
   ================================================================ */

/**
 * handleResponse(data)
 * Central dispatcher called after a successful API response.
 * Hides the loading state and renders all result panels.
 *
 * Expected data shape:
 * {
 *   categories: string[],
 *   context:    string[],
 *   confidence: number (0–1),
 *   keywords:   string[],
 *   steps: [{ text, deeplink, recommended }]
 * }
 */
function handleResponse(data) {
  /* Stop loading spinner & solar connector beam */
  setAnalyzingState(false);

  const contexts = data?.response?.contexts || [];
  const meta = data?.meta || {};
  const query = data?.query || AppState.currentQuery;
  const variations = data?.query_variations || [];

  /* Render each panel with real backend data */
  displayCategories(contexts, meta);
  displayExplanation(query, contexts, meta, variations);
  displaySteps(contexts);

  /* Show feedback panel last (slight delay for visual stagger) */
  setTimeout(() => showPanel(DOM.panelFeedback()), 300);

  /* Scroll output into view */
  setTimeout(() => {
    DOM.outputArea().scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 80);
}

/** Helper: removes hidden attribute and triggers fade-in animation */
function showPanel(panelEl) {
  if (!panelEl) return;
  panelEl.hidden = false;
  /* Force reflow so animation re-triggers on subsequent queries */
  panelEl.classList.remove('fade-in');
  panelEl.offsetHeight; // eslint-disable-line no-unused-expressions
  panelEl.classList.add('fade-in');
}

/* ================================================================
   BACKEND RESPONSE ADAPTERS & DISPLAY FUNCTIONS
   ================================================================ */

/**
 * displayCategories(contexts, meta)
 * Renders the "Detected Issues" panel using backend Goal contexts.
 * Each context (Goal) becomes a chip with title, match score %,
 * and an engine metadata status bar.
 */
function displayCategories(contexts, meta) {
  const container = DOM.intentChips();
  const badgeEl = DOM.intentBadge();
  const panel = DOM.panelIssues();
  if (!container || !panel) return;

  container.innerHTML = '';

  if (!contexts || contexts.length === 0) {
    /* Edge case: Backend returned no matching contexts / rejection */
    container.innerHTML =
      '<p class="no-results-hint">No matching troubleshooting guide found for this query. Please refine your description or try another symptom.</p>';
    
    const metaRow = createMetaBadgeRow(meta, false);
    container.appendChild(metaRow);

    if (badgeEl) badgeEl.textContent = '0 found';
    showPanel(panel);
    return;
  }

  /* Render each context as a result chip */
  contexts.forEach((ctx, idx) => {
    const chip = createCategoryChip(ctx, idx);
    container.appendChild(chip);
  });

  /* Render engine metadata badges (Cache Hit, Latency, Model, Fallback) */
  const metaRow = createMetaBadgeRow(meta, true);
  container.appendChild(metaRow);

  if (badgeEl) badgeEl.textContent = `${contexts.length} found`;
  showPanel(panel);
}

/**
 * createCategoryChip(ctx, index)
 * Builds a chip for a detected Goal context with title and confidence score.
 */
function createCategoryChip(ctx, index) {
  const chip = document.createElement('div');
  chip.className = 'intent-chip category-chip';
  chip.setAttribute('role', 'listitem');
  chip.style.animationDelay = `${index * 60}ms`;

  const checkEl = document.createElement('span');
  checkEl.className = 'category-check';
  checkEl.textContent = '✓';
  checkEl.setAttribute('aria-hidden', 'true');

  const labelEl = document.createElement('span');
  labelEl.className = 'intent-label';
  labelEl.textContent = ctx.title || ctx.goal || 'General Troubleshooting';

  chip.appendChild(checkEl);
  chip.appendChild(labelEl);

  if (ctx.score !== undefined && ctx.score !== null) {
    const scorePct = Math.round(ctx.score * 100);
    const scoreBadge = document.createElement('span');
    scoreBadge.className = 'intent-confidence';
    scoreBadge.textContent = `${scorePct}% match`;
    chip.appendChild(scoreBadge);
  }

  return chip;
}

/**
 * createMetaBadgeRow(meta, hasResults)
 * Creates real engine telemetry chips (Cache Hit, Latency, Model, Fallback).
 */
function createMetaBadgeRow(meta, hasResults) {
  const row = document.createElement('div');
  row.className = 'meta-badge-row';

  // Cache hit badge
  const cacheBadge = document.createElement('span');
  cacheBadge.className = `meta-badge ${meta.cache_hit ? 'cache-hit' : 'cache-miss'}`;
  cacheBadge.innerHTML = meta.cache_hit
    ? '⚡ Semantic Cache Hit'
    : (meta.fallback ? '🔄 Fallback Search' : '🔍 Engine Retrieval');
  row.appendChild(cacheBadge);

  // Latency badge
  if (meta.latency_ms !== undefined) {
    const latBadge = document.createElement('span');
    latBadge.className = 'meta-badge latency';
    latBadge.innerHTML = `⏱️ ${meta.latency_ms}ms`;
    row.appendChild(latBadge);
  }

  // Model badge
  if (meta.model) {
    const modelBadge = document.createElement('span');
    modelBadge.className = 'meta-badge model';
    modelBadge.innerHTML = `🤖 ${meta.model}`;
    row.appendChild(modelBadge);
  }

  // Fallback badge if applicable
  if (meta.fallback) {
    const fbBadge = document.createElement('span');
    fbBadge.className = 'meta-badge fallback';
    fbBadge.innerHTML = `⚠️ Fallback: ${meta.fallback}`;
    row.appendChild(fbBadge);
  }

  return row;
}

/**
 * displayExplanation(query, contexts, meta, variations)
 * Renders the Explainable AI panel with keywords, confidence gauge, and reasoning.
 */
function displayExplanation(query, contexts, meta, variations) {
  const panel = DOM.panelXAI();
  if (!panel) return;

  /* ── Keywords ── */
  const kwContainer = DOM.xaiKeywords();
  if (kwContainer) {
    kwContainer.innerHTML = '';
    const queryWords = extractWords(query);
    const contextWords = contexts.length > 0 ? extractWords(contexts[0].title || '') : [];
    const combined = Array.from(new Set([...queryWords, ...contextWords])).slice(0, 7);

    if (combined.length === 0) {
      kwContainer.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">No specific keywords detected</span>';
    } else {
      combined.forEach(kw => {
        const pill = document.createElement('span');
        pill.className = 'keyword-pill';
        pill.textContent = kw;
        kwContainer.appendChild(pill);
      });
    }
  }

  /* ── Confidence gauge ── */
  const bestScore = contexts.length > 0 ? (contexts[0].score || 0) : 0;
  const pct = Math.round(bestScore * 100);
  const gaugeVal = DOM.gaugeValue();
  const gaugeFill = DOM.gaugeFill();

  if (gaugeVal) gaugeVal.textContent = contexts.length > 0 ? `${pct}%` : '0%';

  if (gaugeFill) {
    setTimeout(() => {
      const offset = 141.4 * (1 - pct / 100);
      gaugeFill.style.strokeDashoffset = offset;
    }, 150);
  }

  /* ── AI Reasoning narrative ── */
  const reasonEl = DOM.xaiReasoning();
  if (reasonEl) {
    if (contexts.length === 0) {
      reasonEl.textContent =
        `The engine evaluated your issue description across all device symptom profiles. ` +
        `No resolution plan exceeded the minimum relevance gate. ` +
        `Engine latency: ${meta.latency_ms || 0}ms.`;
    } else {
      const srcText = meta.cache_hit
        ? 'Matched via prewarmed semantic vector embedding cache.'
        : (meta.fallback
            ? `Retrieved via BM25 hybrid fallback search across local SIIS knowledge base (${meta.fallback}).`
            : 'Validated against verified device decision rules and ranking.');

      reasonEl.textContent =
        `Matched resolution plan: "${contexts[0].title}". ` +
        `${srcText} ` +
        `Confidence score: ${pct}%. ` +
        `Response generated in ${meta.latency_ms || 0}ms using ${meta.model || 'rules-v1'}.`;
    }
  }

  showPanel(panel);
}

/**
 * displaySteps(contexts)
 * Renders the "Troubleshooting Steps" panel by extracting action step groups
 * across all returned Goal contexts.
 */
function displaySteps(contexts) {
  const list = DOM.stepsList();
  const panel = DOM.panelSteps();
  if (!list || !panel) return;

  list.innerHTML = '';

  // Flatten stepGroups across actions in all contexts
  const allSteps = [];
  (contexts || []).forEach(ctx => {
    (ctx.actions || []).forEach(action => {
      (action.stepGroups || []).forEach(sg => {
        allSteps.push({
          actionName: action.actionName || ctx.title,
          category: action.category || 'manual',
          description: action.description || '',
          steps: sg.steps || [],
          actionableDeeplink: sg.actionableDeeplink || null,
          validationDeeplink: sg.validationDeeplink || null,
        });
      });
    });
  });

  AppState.totalSteps = allSteps.length;
  AppState.stepsCompleted = 0;

  if (allSteps.length === 0) {
    list.innerHTML =
      '<p class="no-results-hint">No specific troubleshooting steps available for this query.</p>';
    updateStepsProgress();
    showPanel(panel);
    return;
  }

  allSteps.forEach((stepData, idx) => {
    const stepEl = createStepItem({
      index: idx + 1,
      actionName: stepData.actionName,
      category: stepData.category,
      description: stepData.description,
      steps: stepData.steps,
      actionableDeeplink: stepData.actionableDeeplink,
      validationDeeplink: stepData.validationDeeplink,
    });
    stepEl.style.animationDelay = `${idx * 60}ms`;
    list.appendChild(stepEl);
  });

  updateStepsProgress();
  showPanel(panel);
}

/* ================================================================
   PHASE 2: LOW-LEVEL CHIP FACTORY (kept for Phase 3 compatibility)
   Phase 3 will call createIntentChip() directly with confidence %.
   ================================================================ */

/**
 * createIntentChip({ icon, label, confidence, isPending })
 * Factory for a single intent chip DOM element.
 * Used by both placeholder and Phase 3 real renderers.
 */
function createIntentChip({ icon, label, confidence, isPending }) {
  const chip = document.createElement('div');
  chip.className = 'intent-chip';
  chip.setAttribute('role', 'listitem');

  /* Icon */
  const iconEl = document.createElement('span');
  iconEl.className = 'intent-icon';
  iconEl.textContent = icon;
  iconEl.setAttribute('aria-hidden', 'true');

  /* Label */
  const labelEl = document.createElement('span');
  labelEl.className = 'intent-label';
  labelEl.textContent = label;

  chip.appendChild(iconEl);
  chip.appendChild(labelEl);

  /* Confidence badge (only if confidence is provided) */
  if (confidence !== null && confidence !== undefined) {
    const confEl = document.createElement('span');
    confEl.className = 'intent-confidence';
    confEl.textContent = `${confidence}%`;
    chip.appendChild(confEl);

    /* Confidence bar at bottom */
    const bar = document.createElement('div');
    bar.className = 'confidence-bar';
    bar.style.setProperty('--pct', `${confidence}%`);
    chip.appendChild(bar);
  }

  /* Pending state styling */
  if (isPending) {
    chip.style.borderColor = 'rgba(255,255,255,0.06)';
    chip.style.background = 'rgba(255,255,255,0.02)';
    labelEl.style.fontStyle = 'italic';
    labelEl.style.color = 'var(--text-muted)';
  }

  return chip;
}

/**
 * renderStep(stepData, index)
 * Phase 2/3: Renders a single troubleshooting step.
 * Call this in a loop or streamed for adaptive flow.
 *
 * @param {Object} stepData — {
 *   title:       string,
 *   description: string,
 *   deepLink:    string | null,   // Phase 4 deep link URL
 *   recommended: boolean,          // Phase 4 "Recommended" badge
 *   selfHealing: boolean,          // Phase 4 "Self-Healing" badge
 * }
 * @param {number} index — 1-based step index
 *
 * Example call (Phase 2):
 *   data.steps.forEach((s, i) => renderStep(s, i + 1));
 */
function renderStep(stepData, index) {
  const list = DOM.stepsList();
  if (!list) return;

  const stepEl = createStepItem({ ...stepData, index });

  /* Stagger animation delay for sequential reveal */
  stepEl.style.animationDelay = `${(index - 1) * 80}ms`;

  list.appendChild(stepEl);

  /* Update progress tracking */
  AppState.totalSteps = Math.max(AppState.totalSteps, index);
  updateStepsProgress();
}

/**
 * createStepItem({ index, actionName, category, description, steps, actionableDeeplink, validationDeeplink })
 * Factory for a single backend step-group DOM element.
 * Renders: category badge, action title, description, sub-steps list,
 * actionable deeplink button (with clipboard toast), validation pill, and Mark Done.
 */
function createStepItem({ index, actionName, category, description, steps, actionableDeeplink, validationDeeplink }) {
  const cat = category || 'manual';

  const item = document.createElement('div');
  item.className = cat === 'auto'
    ? 'step-item is-recommended'
    : cat === 'critical'
      ? 'step-item is-critical'
      : 'step-item';
  item.setAttribute('role', 'listitem');
  item.setAttribute('data-step', index);

  /* Step number bubble */
  const numEl = document.createElement('div');
  numEl.className = 'step-number';
  numEl.textContent = index;
  numEl.setAttribute('aria-label', `Step ${index}`);

  /* Body */
  const bodyEl = document.createElement('div');
  bodyEl.className = 'step-body';

  /* Category badge */
  const catLabels = { auto: 'Automated', manual: 'Recommended', critical: 'Caution' };
  const badge = document.createElement('span');
  badge.className = `step-badge ${cat}`;
  badge.textContent = catLabels[cat] || cat;
  bodyEl.appendChild(badge);

  /* Action title */
  const titleEl = document.createElement('h3');
  titleEl.className = 'step-title';
  titleEl.textContent = actionName || 'Troubleshooting Step';
  bodyEl.appendChild(titleEl);

  /* Description (if present and not empty) */
  if (description && description.trim()) {
    const descEl = document.createElement('p');
    descEl.className = 'step-desc';
    descEl.textContent = description;
    bodyEl.appendChild(descEl);
  }

  /* Sub-steps list */
  if (steps && steps.length > 0) {
    const subList = document.createElement('ol');
    subList.className = 'step-substeps-list';
    steps.forEach(stepText => {
      const li = document.createElement('li');
      li.className = 'step-substep';
      li.textContent = stepText;
      subList.appendChild(li);
    });
    bodyEl.appendChild(subList);
  }

  /* Validation deeplink pill */
  if (validationDeeplink && validationDeeplink.deeplink) {
    const valPill = document.createElement('span');
    valPill.className = 'validation-pill';
    const vKey = validationDeeplink.key || 'check';
    const vCond = validationDeeplink.condition || '';
    const vVal = validationDeeplink.value || '';
    valPill.innerHTML = `🔍 Verify: <code>${vKey}${vCond ? ' ' + vCond : ''}${vVal ? ' ' + vVal : ''}</code>`;
    bodyEl.appendChild(valPill);
  }

  /* Action row: deeplink button + mark done */
  const actionRow = document.createElement('div');
  actionRow.className = 'step-action-row';

  /* Actionable deeplink button */
  if (actionableDeeplink && actionableDeeplink.deeplink) {
    const dlBtn = document.createElement('button');
    dlBtn.className = 'step-deep-link';
    dlBtn.type = 'button';
    const dlLabel = actionableDeeplink.description || actionableDeeplink.message || 'Open in Settings';
    dlBtn.textContent = '↗ ' + dlLabel;
    dlBtn.onclick = () => triggerDeeplink(
      actionableDeeplink.deeplink,
      actionableDeeplink.message || dlLabel
    );
    actionRow.appendChild(dlBtn);
  }

  /* Mark done button */
  const doneBtn = document.createElement('button');
  doneBtn.className = 'step-done-btn';
  doneBtn.type = 'button';
  doneBtn.textContent = '✓ Mark Done';
  doneBtn.setAttribute('aria-label', `Mark step ${index} as done`);
  doneBtn.onclick = () => markStepDone(item, doneBtn, index);
  actionRow.appendChild(doneBtn);

  bodyEl.appendChild(actionRow);
  item.appendChild(numEl);
  item.appendChild(bodyEl);

  return item;
}

/**
 * triggerDeeplink(deeplink, message)
 * Dispatches a deeplink URI — the exact URI returned by the backend is preserved.
 *
 * On Samsung/Android (voiceassist:// or intent:// scheme):
 *   - window.location.href is set to the URI; the Android OS intercepts it and
 *     routes it to the VoiceAssist / Settings app that registered the scheme.
 *   - An <iframe> trick is used so navigation away from the SPA is not triggered.
 *
 * On desktop/browser (where the scheme is unregistered):
 *   - The URI is copied to clipboard and a toast explains what to do.
 *   - No error is thrown — the browser silently fails to open an unknown scheme.
 */
function triggerDeeplink(deeplink, message) {
  if (!deeplink) return;

  console.log('[Deeplink] dispatching:', deeplink, '|', message);

  const label = message || deeplink;

  // ── Mobile / Samsung device path ──────────────────────────────────
  // Use a hidden iframe so the SPA doesn't navigate away.
  // The Android OS resolves the custom URI scheme to the registered handler.
  const isMobile = /Android|Samsung|Galaxy/i.test(navigator.userAgent);
  if (isMobile) {
    try {
      const frame = document.createElement('iframe');
      frame.style.cssText = 'display:none;width:0;height:0;border:0;';
      document.body.appendChild(frame);
      frame.src = deeplink;                      // triggers Android intent
      setTimeout(() => frame.remove(), 2000);
    } catch (_) {
      // Fallback: direct navigation (will work even if iframe is blocked)
      window.location.href = deeplink;
    }
    showDeeplinkToast('⚡ ' + label);
    return;
  }

  // ── Desktop / browser path ────────────────────────────────────────
  // Copy the exact URI to clipboard; toast tells user to use it on device.
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(deeplink)
      .then(() => showDeeplinkToast('📋 Copied deeplink — use on Samsung device: ' + label))
      .catch(() => showDeeplinkToast('⚡ Deeplink: ' + label));
  } else {
    showDeeplinkToast('⚡ Deeplink: ' + label);
  }
}

/**
 * showDeeplinkToast(msg)
 * Displays a brief toast confirming deeplink action.
 */
function showDeeplinkToast(msg) {
  const existing = document.getElementById('deeplink-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'deeplink-toast';
  toast.className = 'toast-notification';
  toast.textContent = '⚡ ' + (msg.length > 60 ? msg.slice(0, 57) + '...' : msg);
  document.body.appendChild(toast);

  /* Animate in */
  setTimeout(() => toast.classList.add('visible'), 10);

  /* Auto-dismiss after 3s */
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 400);
  }, 3000);
}

/**
 * markStepDone(itemEl, btnEl, index)
 * Marks a step as completed, updates progress bar.
 * Phase 2+: Can trigger next adaptive step from backend.
 */
function markStepDone(itemEl, btnEl, index) {
  if (itemEl.classList.contains('completed')) return;

  itemEl.classList.add('completed');
  btnEl.textContent = '✓ Done';
  btnEl.disabled = true;

  AppState.stepsCompleted++;
  updateStepsProgress();

  console.log(`Step ${index} marked complete. Progress: ${AppState.stepsCompleted}/${AppState.totalSteps}`);

  /* Phase 3: Could trigger next adaptive step here:
     if (AppState.stepsCompleted < AppState.totalSteps) {
       fetchNextStep(index + 1, AppState.sessionId);
     }
  */
}

/**
 * updateStepsProgress()
 * Updates the step progress bar and label.
 */
function updateStepsProgress() {
  const badgeEl = DOM.stepsBadge();
  const progressRow = DOM.stepsProgressRow();
  const progressFill = DOM.progressFill();
  const progressLbl = DOM.progressLabel();

  if (badgeEl) badgeEl.textContent = `${AppState.totalSteps} steps`;
  if (progressRow) progressRow.hidden = AppState.totalSteps === 0;

  if (progressFill && AppState.totalSteps > 0) {
    const pct = Math.round((AppState.stepsCompleted / AppState.totalSteps) * 100);
    progressFill.style.setProperty('--progress', `${pct}%`);
  }

  if (progressLbl) {
    progressLbl.textContent = `Step ${AppState.stepsCompleted} of ${AppState.totalSteps}`;
  }
}

/**
 * renderExplainPanel(explanationData)
 * Phase 4 hook — still available for richer XAI data.
 * Phase 2 uses displayExplanation() directly with keywords + confidence.
 *
 * @param {Object} explanationData — {
 *   keywords:   string[],
 *   confidence: number (0–1),
 *   reasoning:  string,
 * }
 */
function renderExplainPanel(explanationData) {
  const { keywords = [], confidence = 0, reasoning = '' } = explanationData;
  displayExplanation(keywords, confidence);

  /* Phase 4: also show raw reasoning text if provided */
  const reasonEl = DOM.xaiReasoning();
  if (reasonEl && reasoning) reasonEl.textContent = reasoning;
}

/* ================================================================
   FEEDBACK HANDLER
   Phase 1: logs to console.
   Phase 2: sends POST to /api/feedback with session ID + rating.
   ================================================================ */

/**
 * submitFeedback(rating)
 * Called by Yes/No feedback buttons.
 *
 * @param {'yes'|'no'} rating
 *
 * Phase 2 REPLACEMENT:
 *   await fetch('/api/feedback', {
 *     method: 'POST',
 *     headers: { 'Content-Type': 'application/json' },
 *     body: JSON.stringify({ sessionId: AppState.sessionId, rating }),
 *   });
 */
function submitFeedback(rating) {
  if (AppState.feedbackGiven) return;
  AppState.feedbackGiven = true;

  /* ── Phase 1: Log to console ── */
  console.group('[User Feedback Submitted]');
  console.log('Rating:', rating);
  console.log('Query:', AppState.currentQuery);
  console.log('→ Phase 2 note: POST to /api/feedback here');
  console.groupEnd();

  /* Dim both buttons */
  DOM.feedbackYes().classList.add('selected');
  DOM.feedbackNo().classList.add('selected');

  /* Show confirmation message */
  const confirmEl = DOM.feedbackConfirm();
  const confirmText = DOM.feedbackConfText();

  if (confirmText) {
    confirmText.textContent = rating === 'yes'
      ? 'Thank you! Glad we could help resolve your issue.'
      : 'Thank you for your feedback. We will use this to improve.';
  }

  if (confirmEl) confirmEl.hidden = false;
}

/* ================================================================
   EXAMPLE CHIPS — QUICK INPUT
   Clicking a chip fills the textarea.
   ================================================================ */

/**
 * initChips()
 * Attaches click handlers to example chips.
 * Chips pre-fill the input textarea with their data-query value.
 */
function initChips() {
  const chips = DOM.chips();
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const query = chip.getAttribute('data-query');
      const inputEl = DOM.input();
      if (query && inputEl) {
        inputEl.value = query;
        updateCharCount(inputEl);
        /* Auto-submit on chip click — fires real backend immediately */
        sendQuery();
      }
    });
  });
}

/* ================================================================
   CHARACTER COUNT
   ================================================================ */

/**
 * updateCharCount(inputEl)
 * Updates the character counter below the textarea.
 * Changes color as user approaches the 500 char limit.
 */
function updateCharCount(inputEl) {
  const countEl = DOM.charCount();
  if (!countEl) return;

  const len = inputEl.value.length;
  const max = parseInt(inputEl.getAttribute('maxlength'), 10) || 500;

  countEl.textContent = `${len} / ${max}`;
  countEl.classList.remove('near-limit', 'at-limit');

  if (len >= max) countEl.classList.add('at-limit');
  else if (len >= max * 0.8) countEl.classList.add('near-limit');
}

/* ================================================================
   KEYBOARD SHORTCUTS
   ================================================================ */

/**
 * initKeyboardShortcuts()
 * Ctrl+Enter (or Cmd+Enter) submits the query.
 * Escape clears the input.
 */
function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    /* Ctrl/Cmd + Enter → Submit */
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      sendQuery();
    }

    /* Escape → Clear input if focused */
    if (e.key === 'Escape' && document.activeElement === DOM.input()) {
      DOM.input().value = '';
      updateCharCount(DOM.input());
    }
  });
}

/* ================================================================
   GLOBAL SHAKE ANIMATION (injected dynamically)
   ================================================================ */

/**
 * injectShakeKeyframes()
 * Adds the shake animation keyframes to the document <head>
 * so we can use it without modifying styles.css.
 */
function injectShakeKeyframes() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes shakeAnim {
      0%, 100% { transform: translateX(0); }
      20%       { transform: translateX(-6px); }
      40%       { transform: translateX(6px); }
      60%       { transform: translateX(-4px); }
      80%       { transform: translateX(4px); }
    }

    @keyframes pulseGlow {
      0%, 100% { box-shadow: 0 0 0 0 rgba(108,142,245,0.4); }
      50%       { box-shadow: 0 0 0 8px rgba(108,142,245,0); }
    }
  `;
  document.head.appendChild(style);
}

/* ================================================================
   DYNAMIC SCENIC BACKGROUND & TIME CONTROLLER ENGINE
   - Smooth continuous 24h day/night cycle
   - Continuous Sun arc & Moon arc behind mountains/lake/house
   - Continuous color interpolation for sky gradient, lake water,
     mountains, and cozy window glows
   - Floating glass time controller with slider, presets, and live clock
   - Smooth continuous animation when jumping between presets or hours
   ================================================================ */

const ScenicState = {
  isLive: true,
  currentMinutes: 720,      // 0 to 1440
  targetMinutes: 720,
  animId: null,
  animStartTime: 0,
  animDuration: 1300,
  animStartMinutes: 0,
  animDelta: 0,
  isProcessingConnector: false,
};

// Continuous color palette keyframes across the 24-hour cycle
const SCENIC_KEYFRAMES = [
  {
    hour: 0,
    sky: [[2, 5, 14], [5, 14, 35], [10, 28, 62]],
    mtn: [13, 22, 38],
    hill: [8, 22, 29],
    lake: [7, 23, 40],
    winGlow: 0.95,
    stars: 1.0,
    shimmer: 0.35,
    phase: 'Moonlit Night'
  },
  {
    hour: 4.5,
    sky: [[5, 10, 26], [16, 20, 52], [32, 35, 78]],
    mtn: [20, 24, 46],
    hill: [12, 26, 36],
    lake: [14, 28, 54],
    winGlow: 0.9,
    stars: 0.85,
    shimmer: 0.4,
    phase: 'Predawn'
  },
  {
    hour: 5.6,
    sky: [[20, 18, 54], [75, 29, 78], [247, 186, 118]],
    mtn: [44, 31, 61],
    hill: [29, 38, 47],
    lake: [56, 39, 69],
    winGlow: 0.7,
    stars: 0.25,
    shimmer: 0.55,
    phase: 'Dawn Sunrise'
  },
  {
    hour: 8.5,
    sky: [[21, 66, 115], [43, 110, 166], [255, 243, 205]],
    mtn: [58, 86, 117],
    hill: [31, 71, 53],
    lake: [32, 95, 143],
    winGlow: 0.25,
    stars: 0.0,
    shimmer: 0.75,
    phase: 'Morning'
  },
  {
    hour: 12.0,
    sky: [[13, 71, 161], [25, 118, 210], [227, 242, 253]],
    mtn: [74, 107, 148],
    hill: [38, 92, 70],
    lake: [43, 108, 176],
    winGlow: 0.05,
    stars: 0.0,
    shimmer: 0.9,
    phase: 'High Noon'
  },
  {
    hour: 15.5,
    sky: [[18, 78, 150], [45, 125, 195], [235, 240, 248]],
    mtn: [70, 95, 138],
    hill: [35, 85, 65],
    lake: [40, 100, 160],
    winGlow: 0.1,
    stars: 0.0,
    shimmer: 0.85,
    phase: 'Afternoon'
  },
  {
    hour: 17.5,
    sky: [[30, 21, 58], [211, 75, 65], [254, 209, 102]],
    mtn: [67, 28, 74],
    hill: [56, 35, 51],
    lake: [114, 46, 58],
    winGlow: 0.6,
    stars: 0.0,
    shimmer: 0.8,
    phase: 'Golden Hour'
  },
  {
    hour: 19.2,
    sky: [[14, 7, 32], [107, 30, 88], [224, 109, 78]],
    mtn: [34, 20, 50],
    hill: [22, 25, 36],
    lake: [45, 28, 62],
    winGlow: 0.9,
    stars: 0.5,
    shimmer: 0.5,
    phase: 'Twilight Dusk'
  },
  {
    hour: 21.0,
    sky: [[4, 8, 20], [10, 20, 48], [18, 38, 76]],
    mtn: [16, 24, 42],
    hill: [10, 24, 30],
    lake: [10, 26, 46],
    winGlow: 0.95,
    stars: 0.9,
    shimmer: 0.4,
    phase: 'Nightfall'
  },
  {
    hour: 24.0,
    sky: [[2, 5, 14], [5, 14, 35], [10, 28, 62]],
    mtn: [13, 22, 38],
    hill: [8, 22, 29],
    lake: [7, 23, 40],
    winGlow: 0.95,
    stars: 1.0,
    shimmer: 0.35,
    phase: 'Moonlit Night'
  }
];

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function lerpColor(c1, c2, t) {
  return [
    Math.round(lerp(c1[0], c2[0], t)),
    Math.round(lerp(c1[1], c2[1], t)),
    Math.round(lerp(c1[2], c2[2], t)),
  ];
}

function easeInOutSmooth(t) {
  // Ken Perlin's SmootherStep: 6t^5 - 15t^4 + 10t^3 (zero 1st and 2nd derivatives at edges)
  return t * t * t * (t * (t * 6 - 15) + 10);
}

/**
 * renderScenicFrame(minutes)
 * Core continuous rendering function: updates sky, sun, moon,
 * landscape, window lighting, and controller widgets.
 */
function renderScenicFrame(minutes) {
  // Normalize minutes to [0, 1440)
  const normMin = ((minutes % 1440) + 1440) % 1440;
  const hour = normMin / 60;

  // 1. Digital Clock Display in Time Controller
  let h12 = Math.floor(hour) % 12;
  if (h12 === 0) h12 = 12;
  const m = Math.floor(normMin % 60);
  const mPad = m < 10 ? '0' + m : '' + m;
  const actualAmpm = (hour >= 12 && hour < 24) ? 'PM' : 'AM';

  const elH = document.getElementById('tc-h');
  const elM = document.getElementById('tc-m');
  const elAmpm = document.getElementById('tc-ampm');
  if (elH) elH.textContent = h12;
  if (elM) elM.textContent = mPad;
  if (elAmpm) elAmpm.textContent = actualAmpm;

  // 2. Interpolate Scenic Keyframe Colors
  let k1 = SCENIC_KEYFRAMES[0];
  let k2 = SCENIC_KEYFRAMES[1];
  for (let i = 0; i < SCENIC_KEYFRAMES.length - 1; i++) {
    if (hour >= SCENIC_KEYFRAMES[i].hour && hour <= SCENIC_KEYFRAMES[i + 1].hour) {
      k1 = SCENIC_KEYFRAMES[i];
      k2 = SCENIC_KEYFRAMES[i + 1];
      break;
    }
  }

  const range = k2.hour - k1.hour || 1;
  const t = Math.max(0, Math.min(1, (hour - k1.hour) / range));

  // Sky colors (3 stops)
  const sky0 = lerpColor(k1.sky[0], k2.sky[0], t);
  const sky1 = lerpColor(k1.sky[1], k2.sky[1], t);
  const sky2 = lerpColor(k1.sky[2], k2.sky[2], t);
  const mtn = lerpColor(k1.mtn, k2.mtn, t);
  const hill = lerpColor(k1.hill, k2.hill, t);
  const lake = lerpColor(k1.lake, k2.lake, t);
  const winGlow = lerp(k1.winGlow, k2.winGlow, t);
  const starsOpacity = lerp(k1.stars, k2.stars, t);
  const shimmer = lerp(k1.shimmer, k2.shimmer, t);

  // Sharp mountain multi-faceted calculations
  const mtnFar = [Math.max(0, mtn[0] - 12), Math.max(0, mtn[1] - 14), Math.max(0, mtn[2] - 18)];
  const mtnLit = [Math.min(255, mtn[0] + 28), Math.min(255, mtn[1] + 34), Math.min(255, mtn[2] + 48)];
  const mtnShadow = [Math.max(0, mtn[0] - 14), Math.max(0, mtn[1] - 16), Math.max(0, mtn[2] - 20)];

  // Dynamic snow tint (alpenglow at dawn/dusk, silver at night, white at midday)
  let snowColor = 'rgba(235, 245, 255, 0.9)';
  if (hour >= 5.0 && hour <= 6.8) {
    snowColor = 'rgba(255, 210, 180, 0.92)'; // Rose alpenglow
  } else if (hour >= 17.0 && hour <= 19.5) {
    snowColor = 'rgba(255, 175, 120, 0.94)'; // Fiery sunset alpenglow
  } else if (hour > 19.5 && hour < 21.5) {
    snowColor = 'rgba(200, 170, 220, 0.85)'; // Twilight violet
  } else if (hour >= 21.5 || hour < 5.0) {
    snowColor = 'rgba(185, 220, 255, 0.82)'; // Moonlight silver
  }

  const rootStyle = document.documentElement.style;
  rootStyle.setProperty(
    '--sky-gradient',
    `linear-gradient(175deg, rgb(${sky0.join(',')}) 0%, rgb(${sky1.join(',')}) 45%, rgb(${sky2.join(',')}) 100%)`
  );
  rootStyle.setProperty('--sc-mtn-far', `rgb(${mtnFar.join(',')})`);
  rootStyle.setProperty('--sc-mtn-lit', `rgb(${mtnLit.join(',')})`);
  rootStyle.setProperty('--sc-mtn-shadow', `rgb(${mtnShadow.join(',')})`);
  rootStyle.setProperty('--sc-mtn', `rgb(${mtn.join(',')})`);
  rootStyle.setProperty('--sc-snow', snowColor);
  rootStyle.setProperty('--sc-hill', `rgb(${hill.join(',')})`);
  rootStyle.setProperty('--sc-lake', `rgb(${lake.join(',')})`);
  rootStyle.setProperty('--h-win-glow-opacity', winGlow.toFixed(3));
  rootStyle.setProperty('--star-opacity', starsOpacity.toFixed(3));
  rootStyle.setProperty('--lake-shimmer-opacity', shimmer.toFixed(3));

  // Phase badge in controller
  const activePhase = t < 0.5 ? k1 : k2;
  const phaseEl = document.getElementById('tc-phase');
  if (phaseEl) {
    phaseEl.textContent = activePhase.phase;
  }

  // 3. Continuous Sun Trajectory Arc (Active approx 5.0h to 20.0h)
  let sunX = 50;
  let sunY = 110;
  let sunOpacity = 0;
  let sunScale = 1;

  if (hour >= 4.8 && hour <= 20.2) {
    const pSun = (hour - 4.8) / 15.4; // 0 to 1
    sunX = 6 + pSun * 88; // 6% to 94% across viewport
    const sunElevation = Math.sin(pSun * Math.PI);
    sunY = 76 - sunElevation * 62; // highest at noon ~14%

    // Near horizon, dips behind mountains
    if (pSun < 0.08) {
      sunY += (0.08 - pSun) * 180;
      sunOpacity = Math.max(0, pSun / 0.08);
    } else if (pSun > 0.92) {
      sunY += (pSun - 0.92) * 180;
      sunOpacity = Math.max(0, (1 - pSun) / 0.08);
    } else {
      sunOpacity = 1;
    }

    // Sunset/sunrise atmospheric warmth factor: 0.0 at midday (noon), 1.0 near horizon
    let sunsetFactor = 0;
    if (hour <= 12) {
      sunsetFactor = Math.max(0, Math.min(1, (8.5 - hour) / 3.5));
    } else {
      sunsetFactor = Math.max(0, Math.min(1, (hour - 15.5) / 3.8));
    }

    // Photorealistic optical color interpolation
    const g1 = lerpColor([255, 240, 140], [255, 135, 45], sunsetFactor);
    const g2 = lerpColor([255, 185, 50], [255, 65, 15], sunsetFactor);
    const g3 = lerpColor([255, 130, 20], [200, 30, 0], sunsetFactor);
    const coronaCol = lerpColor([255, 225, 110], [255, 105, 30], sunsetFactor);
    const haloCol = lerpColor([255, 210, 70], [255, 80, 20], sunsetFactor);
    const ambCol = lerpColor([255, 240, 160], [255, 125, 45], sunsetFactor);
    const ambFade = lerpColor([255, 190, 60], [240, 70, 20], sunsetFactor);
    const glareOp = (0.75 - sunsetFactor * 0.32).toFixed(2);
    sunScale = +(1.0 + sunsetFactor * 0.16).toFixed(2);

    rootStyle.setProperty('--sun-glow-1', `rgba(${g1.join(',')}, 0.95)`);
    rootStyle.setProperty('--sun-glow-2', `rgba(${g2.join(',')}, 0.60)`);
    rootStyle.setProperty('--sun-glow-3', `rgba(${g3.join(',')}, 0.28)`);
    rootStyle.setProperty('--sun-corona-color', `rgba(${coronaCol.join(',')}, 0.58)`);
    rootStyle.setProperty('--sun-halo-color', `rgba(${haloCol.join(',')}, 0.48)`);
    rootStyle.setProperty('--sun-ambient-color', `rgba(${ambCol.join(',')}, 0.44)`);
    rootStyle.setProperty('--sun-ambient-fade', `rgba(${ambFade.join(',')}, 0.18)`);
    rootStyle.setProperty('--sun-glare-opacity', glareOp);

    // Realistic core gradient with always-intense white center (#FFFFFF)
    if (sunsetFactor < 0.3) {
      rootStyle.setProperty(
        '--sun-core-bg',
        'radial-gradient(circle at 48% 48%, #FFFFFF 0%, #FFFFFA 18%, #FFF6C2 42%, #FFD54F 72%, #FFA000 100%)'
      );
    } else if (sunsetFactor < 0.7) {
      rootStyle.setProperty(
        '--sun-core-bg',
        'radial-gradient(circle at 48% 48%, #FFFFFF 0%, #FFF3D6 18%, #FFC355 45%, #FF8524 75%, #F05000 100%)'
      );
    } else {
      rootStyle.setProperty(
        '--sun-core-bg',
        'radial-gradient(circle at 48% 48%, #FFFFFF 0%, #FFE8D0 16%, #FFA443 45%, #FF4F18 78%, #D81E00 100%)'
      );
    }
  }

  // When solar processing connector is running, elevate and intensify the revolving sun
  if (ScenicState.isProcessingConnector) {
    sunOpacity = 1;
    sunScale = 1.18;
    if (sunY > 30) {
      sunY = 16;
      sunX = 50;
    }
  }

  rootStyle.setProperty('--sun-x', `${sunX.toFixed(2)}%`);
  rootStyle.setProperty('--sun-y', `${sunY.toFixed(2)}%`);
  rootStyle.setProperty('--sun-opacity', sunOpacity.toFixed(3));
  rootStyle.setProperty('--sun-scale', sunScale.toFixed(2));

  // 4. Continuous Moon Trajectory Arc (Active approx 18.0h to 6.8h)
  let moonX = 50;
  let moonY = 110;
  let moonOpacity = 0;
  let moonScale = 1;

  const isNightTime = (hour >= 17.8 || hour <= 6.8);
  if (isNightTime) {
    const nightMins = (hour >= 17.8) ? (hour - 17.8) * 60 : (hour + 6.2) * 60;
    const totalNightMins = 13.0 * 60; // 780m
    const pMoon = Math.min(1, Math.max(0, nightMins / totalNightMins));

    moonX = 8 + pMoon * 84; // 8% to 92% across viewport
    const moonElevation = Math.sin(pMoon * Math.PI);
    moonY = 74 - moonElevation * 60; // highest at midnight ~14%

    if (pMoon < 0.08) {
      moonY += (0.08 - pMoon) * 160;
      moonOpacity = Math.max(0, pMoon / 0.08);
    } else if (pMoon > 0.92) {
      moonY += (pMoon - 0.92) * 160;
      moonOpacity = Math.max(0, (1 - pMoon) / 0.08);
    } else {
      moonOpacity = 1;
    }
  }

  rootStyle.setProperty('--moon-x', `${moonX.toFixed(2)}%`);
  rootStyle.setProperty('--moon-y', `${moonY.toFixed(2)}%`);
  rootStyle.setProperty('--moon-opacity', moonOpacity.toFixed(3));
  rootStyle.setProperty('--moon-scale', moonScale.toFixed(2));

  // Dock lantern: glowing warm gold in evening/night, soft in daytime
  const lantern = document.getElementById('sc-dock-lantern');
  if (lantern) {
    const isDark = (hour >= 18.0 || hour <= 6.2);
    lantern.setAttribute('opacity', isDark ? '0.98' : '0.35');
    lantern.setAttribute('fill', isDark ? '#FFE082' : '#F5D061');
  }
}

/**
 * startScenicAnimation(targetMin, duration)
 * Animates smoothly between current time and target time along shortest circular path.
 */
function startScenicAnimation(targetMin, duration = 1400) {
  if (ScenicState.animId) {
    cancelAnimationFrame(ScenicState.animId);
    ScenicState.animId = null;
  }

  ScenicState.targetMinutes = ((targetMin % 1440) + 1440) % 1440;
  ScenicState.animStartMinutes = ScenicState.currentMinutes;
  ScenicState.animDuration = duration;
  ScenicState.animStartTime = performance.now();

  // Shortest path on 1440-minute circular clock
  let diff = (ScenicState.targetMinutes - ScenicState.animStartMinutes) % 1440;
  if (diff > 720) diff -= 1440;
  if (diff < -720) diff += 1440;
  ScenicState.animDelta = diff;

  function step(now) {
    const elapsed = now - ScenicState.animStartTime;
    const progress = Math.min(1, elapsed / ScenicState.animDuration);
    const eased = easeInOutSmooth(progress);

    ScenicState.currentMinutes = (ScenicState.animStartMinutes + ScenicState.animDelta * eased + 1440) % 1440;
    renderScenicFrame(ScenicState.currentMinutes);

    if (progress < 1) {
      ScenicState.animId = requestAnimationFrame(step);
    } else {
      ScenicState.currentMinutes = ScenicState.targetMinutes;
      renderScenicFrame(ScenicState.currentMinutes);
      ScenicState.animId = null;
    }
  }

  ScenicState.animId = requestAnimationFrame(step);
}

/**
 * User inputs slider time (drag)
 */
function bgSliderInput(value) {
  if (ScenicState.animId) {
    cancelAnimationFrame(ScenicState.animId);
    ScenicState.animId = null;
  }
  ScenicState.isLive = false;
  updateLiveButtonUI(false);
  clearActivePresets();

  ScenicState.currentMinutes = parseFloat(value);
  renderScenicFrame(ScenicState.currentMinutes);
}

/**
 * User selects a preset time (Dawn, Morn, Noon, Dusk, Night)
 * Faster, silky 1400ms continuous transition
 */
function bgSetPreset(hourDecimal) {
  ScenicState.isLive = false;
  updateLiveButtonUI(false);

  // Highlight active preset button
  const presetButtons = document.querySelectorAll('.tc-presets .tc-btn');
  presetButtons.forEach(btn => {
    const attr = btn.getAttribute('onclick');
    if (attr && attr.includes(`(${hourDecimal})`)) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  const target = hourDecimal * 60;
  startScenicAnimation(target, 1400);
}

/**
 * User activates "Live" mode: syncs back to local system clock
 */
function bgSetLive() {
  ScenicState.isLive = true;
  updateLiveButtonUI(true);
  clearActivePresets();

  const now = new Date();
  const realMinutes = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  startScenicAnimation(realMinutes, 1200);
}

function updateLiveButtonUI(isActive) {
  const liveBtn = document.getElementById('tc-live');
  if (liveBtn) {
    if (isActive) {
      liveBtn.classList.add('active');
    } else {
      liveBtn.classList.remove('active');
    }
  }
}

function clearActivePresets() {
  document.querySelectorAll('.tc-presets .tc-btn').forEach(b => b.classList.remove('active'));
}

// Expose functions globally for inline HTML handlers
window.bgSliderInput = bgSliderInput;
window.bgSetPreset = bgSetPreset;
window.bgSetLive = bgSetLive;

/**
 * generateStars()
 * Creates 160 randomised star <span> elements inside #bg-stars.
 */
function generateStars() {
  const container = document.getElementById('bg-stars');
  if (!container || container.children.length > 0) return;

  const STAR_COUNT = 160;
  const fragment = document.createDocumentFragment();

  for (let i = 0; i < STAR_COUNT; i++) {
    const star = document.createElement('span');
    star.className = 'star';

    const left = (Math.random() * 100).toFixed(2);
    const top = (Math.random() * 68).toFixed(2); // Upper sky

    const sizes = [1, 1, 1, 1.5, 1.5, 2, 2, 2.5];
    const size = sizes[Math.floor(Math.random() * sizes.length)];
    const opacity = (0.35 + Math.random() * 0.65).toFixed(2);
    const duration = (2 + Math.random() * 4).toFixed(1);
    const delay = (Math.random() * 5).toFixed(1);

    star.style.cssText = [
      `left: ${left}%`,
      `top: ${top}%`,
      `width: ${size}px`,
      `height: ${size}px`,
      `--star-opacity: ${opacity}`,
      `--twinkle-dur: ${duration}s`,
      `--twinkle-delay: ${delay}s`,
      size >= 2 ? `box-shadow: 0 0 ${size * 2}px rgba(200,220,255,0.6)` : '',
    ].filter(Boolean).join('; ');

    fragment.appendChild(star);
  }

  container.appendChild(fragment);
}

/**
 * initScenicEngine()
 * Bootstraps the scenic sky, stars, lake, sun and moon.
 */
function initScenicEngine() {
  generateStars();

  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  ScenicState.currentMinutes = currentMinutes;
  ScenicState.isLive = true;

  updateLiveButtonUI(true);
  renderScenicFrame(currentMinutes);

  // Live minute ticker
  setInterval(() => {
    if (ScenicState.isLive && !ScenicState.animId) {
      const liveNow = new Date();
      ScenicState.currentMinutes = liveNow.getHours() * 60 + liveNow.getMinutes() + liveNow.getSeconds() / 60;
      renderScenicFrame(ScenicState.currentMinutes);
    }
  }, 1000);
}

/* ================================================================
   INIT — runs on DOM ready
   ================================================================ */

/**
 * init()
 * Bootstraps the application.
 */
function init() {
  /* ── Initialize scenic background and celestial controller ── */
  initScenicEngine();

  /* Inject runtime keyframes */
  injectShakeKeyframes();

  /* Wire up chips */
  initChips();

  /* Wire up keyboard shortcuts */
  initKeyboardShortcuts();

  /* Character counter & Enter key submit on input */
  const inputEl = DOM.input();
  if (inputEl) {
    inputEl.addEventListener('input', () => updateCharCount(inputEl));
    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuery();
      }
    });
  }

  console.log(
    '%c Smart Guided Troubleshooting Engine ',
    'background: linear-gradient(135deg,#6C8EF5,#A78BFA); color:#fff; font-weight:700; padding:4px 8px; border-radius:4px;'
  );
  console.log('%c Phase 2 — API Integration Active ✓', 'color:#34D399; font-weight:600;');
  console.log('%c Lakeside Scenic Engine & Celestial Physics Active ✓', 'color:#6C8EF5; font-weight:600;');
}

/* Run init when DOM is ready */
document.addEventListener('DOMContentLoaded', init);

