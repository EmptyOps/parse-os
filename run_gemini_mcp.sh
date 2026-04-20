#!/usr/bin/env bash
# run_gemini_mcp.sh
#
# CLASSIC MODE ($1 = plain task string):
#   Called by parse-os's GeminiChromeDevToolsMCPAdapter.
#   Passes the full task to Gemini. No Chrome management. No step-by-step.
#   Example: run_gemini_mcp.sh "search for python tutorials on google"
#
# PRO MODE ($1 = path to a .json file):
#   Called by parse-os-pro's MCPStepService, one step at a time.
#   Auto-launches one persistent Chrome on port 9222 if not already running.
#   All steps in the session share the same Chrome instance — same tab, same state.
#   ~/.gemini/settings.json is patched once to add --browserUrl.
#   Example: run_gemini_mcp.sh /tmp/step_payload_abc.json
#
# JSON payload format (pro mode input):
#   { "instruction": "click the login button", "url": "https://example.com" }

set -e

INPUT="$1"

if [ -z "$INPUT" ]; then
  echo "No task or payload file provided"
  exit 1
fi

export TERM=dumb
export NO_COLOR=1
export GEMINI_NO_COLOR=1

# ── Chrome management (pro mode only) ────────────────────────────────────────

CHROME_PORT=9222
CHROME_URL="http://127.0.0.1:${CHROME_PORT}"
CHROME_PROFILE_DIR="$HOME/.cache/parse-os-chrome-profile"
GEMINI_SETTINGS="$HOME/.gemini/settings.json"

_find_chrome() {
  for bin in google-chrome-stable google-chrome chromium-browser chromium chrome; do
    if command -v "$bin" &>/dev/null; then
      echo "$bin"
      return 0
    fi
  done
  return 1
}

_chrome_running() {
  curl -sf --max-time 2 "${CHROME_URL}/json/version" > /dev/null 2>&1
}

_patch_gemini_settings() {
  if [ ! -f "$GEMINI_SETTINGS" ]; then
    return 0
  fi
  # Idempotent — only writes if --browserUrl not already present
  python3 -c "
import json, sys
path = '$GEMINI_SETTINGS'
with open(path) as f:
    d = json.load(f)
args = d.get('mcpServers', {}).get('chrome-devtools', {}).get('args', [])
if '--browserUrl' in args:
    sys.exit(0)
servers = d.setdefault('mcpServers', {})
chrome  = servers.setdefault('chrome-devtools', {})
args    = chrome.setdefault('args', ['chrome-devtools-mcp@latest'])
clean = []
skip  = False
for a in args:
    if skip:
        skip = False
        continue
    if a == '--browserUrl':
        skip = True
        continue
    clean.append(a)
clean.extend(['--browserUrl', '$CHROME_URL'])
chrome['args'] = clean
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
print('[run_gemini_mcp] patched settings.json with --browserUrl $CHROME_URL', file=sys.stderr)
" 2>&1 >&2
}

_launch_chrome() {
  local chrome_bin
  if ! chrome_bin=$(_find_chrome); then
    echo '[run_gemini_mcp] ERROR: no Chrome binary found. Install google-chrome or chromium.' >&2
    exit 1
  fi
  echo "[run_gemini_mcp] launching ${chrome_bin} on port ${CHROME_PORT}..." >&2
  mkdir -p "$CHROME_PROFILE_DIR"
  nohup "$chrome_bin" \
    --remote-debugging-port="${CHROME_PORT}" \
    --no-first-run \
    --no-default-browser-check \
    --disable-background-networking \
    --disable-client-side-phishing-detection \
    --disable-sync \
    --user-data-dir="$CHROME_PROFILE_DIR" \
    about:blank \
    > /tmp/parse-os-chrome.log 2>&1 &
  local waited=0
  while ! _chrome_running; do
    if [ "$waited" -ge 10 ]; then
      echo '[run_gemini_mcp] ERROR: Chrome did not start within 10s. See /tmp/parse-os-chrome.log' >&2
      exit 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
  echo "[run_gemini_mcp] Chrome ready on ${CHROME_URL}" >&2
}

# ── Mode detection ────────────────────────────────────────────────────────────

if [[ "$INPUT" == *.json ]]; then

  # ── PRO MODE ──────────────────────────────────────────────────────────────

  if [ ! -f "$INPUT" ]; then
    echo '{"error": "payload file not found"}' >&2
    exit 1
  fi

  if ! _chrome_running; then
    _launch_chrome
  else
    echo "[run_gemini_mcp] reusing Chrome on ${CHROME_URL}" >&2
  fi

  _patch_gemini_settings

  INSTRUCTION=$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print(d.get('instruction', ''))
" "$INPUT")

  URL=$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print(d.get('url', ''))
" "$INPUT" 2>/dev/null || echo "")

  if [ -n "$URL" ]; then
    TASK_TEXT="The browser is already open. Current page context is $URL. Perform ONLY this single action: $INSTRUCTION"
  else
    TASK_TEXT="Perform ONLY this single action: $INSTRUCTION"
  fi

  PROMPT="$TASK_TEXT

RULES:
- Perform ONLY the one action described. Do not navigate, scroll, or click anything extra.
- If the instruction says 'press Enter', 'submit', or 'perform the search': dispatch a keyboard Enter keypress on the currently focused element using the keyboard API. Set action=key and key=Enter. Do NOT type any text.
- If the instruction says 'wait for page to load' or 'wait for results': take a screenshot to observe the current page state. Set action=navigate and leave element fields empty.
- After performing the action, respond ONLY with a single JSON object. No markdown fences. No explanation. No extra text. Just valid JSON.

Required JSON structure:
{
  \"action\": \"click\" or \"type\" or \"key\" or \"scroll\" or \"hover\" or \"navigate\",
  \"text\": \"exact text typed — include ONLY when action is type\",
  \"key\": \"key name e.g. Enter — include ONLY when action is key\",
  \"element\": {
    \"css_selector\": \"exact CSS selector of the element you interacted with\",
    \"id\": \"id attribute value or empty string\",
    \"data-testid\": \"data-testid value or empty string\",
    \"aria-label\": \"aria-label value or empty string\",
    \"xpath\": \"XPath as fallback\"
  }
}"

  gemini --yolo <<EOF
/ide disable
Using chrome-devtools MCP.
$PROMPT
/quit
EOF

else

  # ── CLASSIC MODE ──────────────────────────────────────────────────────────
  TASK="$INPUT"

  gemini --yolo <<EOF
/ide disable
Using chrome-devtools MCP.
$TASK
/quit
EOF

fi




####### below is the before additing about chrome dev tool mcp opening new chrome at every step





# #!/usr/bin/env bash
# # run_gemini_mcp.sh
# #
# # Two modes depending on what $1 is:
# #
# # CLASSIC MODE ($1 = plain task string):
# #   Called by parse-os's GeminiChromeDevToolsMCPAdapter for full browser tasks.
# #   Passes the task string directly to Gemini. Gemini handles the full task.
# #   Example: run_gemini_mcp.sh "search for python tutorials on google"
# #
# # PRO MODE ($1 = path to a .json file):
# #   Called by parse-os-pro's MCPStepService for one step at a time.
# #   Reads instruction + url from the JSON file.
# #   Instructs Gemini to respond with structured JSON containing the selector.
# #   Example: run_gemini_mcp.sh /tmp/step_payload_abc.json
# #
# # JSON file format (pro mode input):
# #   { "instruction": "click the login button", "url": "https://example.com" }
# #
# # Gemini response format (pro mode output):
# #   {
# #     "action": "click",
# #     "element": {
# #       "css_selector": "#login-btn",
# #       "id": "login-btn",
# #       "data-testid": "login-button",
# #       "aria-label": "Login",
# #       "xpath": "//button[@id='login-btn']"
# #     }
# #   }

# set -e

# INPUT="$1"

# if [ -z "$INPUT" ]; then
#   echo "No task or payload file provided"
#   exit 1
# fi

# export TERM=dumb
# export NO_COLOR=1
# export GEMINI_NO_COLOR=1

# # ── Detect pro vs classic ─────────────────────────────────────────────────────

# if [[ "$INPUT" == *.json ]]; then

#   # ── PRO MODE: read instruction and url from JSON file ─────────────────────
#   if [ ! -f "$INPUT" ]; then
#     echo '{"error": "payload file not found"}' >&2
#     exit 1
#   fi


#   INSTRUCTION=$(python3 -c "
# import json, sys
# with open(sys.argv[1]) as f:
#     d = json.load(f)
# print(d.get('instruction', ''))
# " "$INPUT")

#   URL=$(python3 -c "
# import json, sys
# with open(sys.argv[1]) as f:
#     d = json.load(f)
# print(d.get('url', ''))
# " "$INPUT" 2>/dev/null || echo "")

#   # INSTRUCTION=$(python3 -c "import json; d=json.load(open('$INPUT')); print(d.get('instruction',''))")

#   URL=$(python3 -c "import json; d=json.load(open('$INPUT')); print(d.get('url',''))" 2>/dev/null || echo "")

#   if [ -n "$URL" ]; then
#     TASK_TEXT="Navigate to $URL. Then: $INSTRUCTION"
#   else
#     TASK_TEXT="$INSTRUCTION"
#   fi

#   PROMPT="$TASK_TEXT

# IMPORTANT: After performing the action, respond ONLY with a single JSON object.
# No markdown fences. No explanation. No extra text. Just the JSON.

# Required JSON structure:
# {
#   \"action\": \"click\" or \"type\" or \"scroll\" or \"hover\" or \"navigate\",
#   \"text\": \"text you typed (only include if action is type)\",
#   \"element\": {
#     \"css_selector\": \"the exact CSS selector of the element you interacted with\",
#     \"id\": \"element id attribute if it has one\",
#     \"data-testid\": \"data-testid value if present\",
#     \"aria-label\": \"aria-label value if present\",
#     \"xpath\": \"XPath expression as fallback\"
#   }
# }"

#   gemini --yolo <<EOF
# /ide disable
# Using chrome-devtools MCP.
# $PROMPT
# /quit
# EOF

# else

#   # ── CLASSIC MODE: pass plain task string directly to Gemini ───────────────
#   TASK="$INPUT"

#   gemini --yolo <<EOF
# /ide disable
# Using chrome-devtools MCP.
# $TASK
# /quit
# EOF

# fi