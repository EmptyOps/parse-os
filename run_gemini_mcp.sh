#!/usr/bin/env bash
# run_gemini_mcp.sh
#
# Two modes depending on what $1 is:
#
# CLASSIC MODE ($1 = plain task string):
#   Called by parse-os's GeminiChromeDevToolsMCPAdapter for full browser tasks.
#   Passes the task string directly to Gemini. Gemini handles the full task.
#   No Chrome management — Gemini/MCP handles its own browser lifecycle.
#
# PRO MODE ($1 = path to a .json file):
#   Called by parse-os-pro's MCPStepService for one step at a time.
#   Automatically ensures ONE persistent Chrome instance is running on port 9222.
#   All steps in a session share the same Chrome — same tab, same state.
#   On first step: Chrome is launched if not already running.
#   On subsequent steps: existing Chrome is reused.
#   ~/.gemini/settings.json is patched once to add --browserUrl so every
#   Gemini invocation connects to this shared instance.

set -e

INPUT="$1"

if [ -z "$INPUT" ]; then
  echo "No task or payload file provided"
  exit 1
fi

export TERM=dumb
export NO_COLOR=1
export GEMINI_NO_COLOR=1

# ── Chrome configuration ───────────────────────────────────────────────────────
CHROME_PORT=9222
CHROME_URL="http://127.0.0.1:${CHROME_PORT}"
CHROME_PROFILE_DIR="$HOME/.cache/parse-os-chrome-profile"
GEMINI_SETTINGS="$HOME/.gemini/settings.json"

# Find the chrome binary — try common names in order
_find_chrome() {
  for bin in google-chrome-stable google-chrome chromium-browser chromium chrome; do
    if command -v "$bin" &>/dev/null; then
      echo "$bin"
      return 0
    fi
  done
  return 1
}

# Returns 0 if Chrome is already listening on CHROME_PORT, 1 otherwise
_chrome_running() {
  curl -sf --max-time 2 "${CHROME_URL}/json/version" > /dev/null 2>&1
}

# Patch ~/.gemini/settings.json so chrome-devtools MCP connects to our Chrome.
# Only writes if the --browserUrl arg is not already present.
_patch_gemini_settings() {
  if [ ! -f "$GEMINI_SETTINGS" ]; then
    return 0
  fi

  # Check if already patched
  if python3 -c "
import json, sys
d = json.load(open('$GEMINI_SETTINGS'))
args = d.get('mcpServers', {}).get('chrome-devtools', {}).get('args', [])
sys.exit(0 if '--browserUrl' in args else 1)
" 2>/dev/null; then
    return 0  # already patched
  fi

  # Patch: add --browserUrl and value to the args array
  python3 -c "
import json, sys

path = '$GEMINI_SETTINGS'
with open(path) as f:
    d = json.load(f)

servers = d.setdefault('mcpServers', {})
chrome  = servers.setdefault('chrome-devtools', {})
args    = chrome.setdefault('args', ['chrome-devtools-mcp@latest'])

# Remove any existing --browserUrl and its value to avoid duplicates
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

print('[run_gemini_mcp] patched ~/.gemini/settings.json with --browserUrl $CHROME_URL')
" 2>&1
}

# Launch Chrome with remote debugging and wait until it's ready (max 10s)
_launch_chrome() {
  local chrome_bin
  if ! chrome_bin=$(_find_chrome); then
    echo '[run_gemini_mcp] ERROR: no Chrome binary found. Install google-chrome or chromium.' >&2
    exit 1
  fi

  echo "[run_gemini_mcp] launching Chrome ($chrome_bin) on port ${CHROME_PORT}..." >&2

  mkdir -p "$CHROME_PROFILE_DIR"

  # Launch detached — survives this script exiting
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

  # Wait until Chrome is accepting connections (max 10 seconds)
  local waited=0
  while ! _chrome_running; do
    if [ "$waited" -ge 10 ]; then
      echo '[run_gemini_mcp] ERROR: Chrome did not start within 10s. Check /tmp/parse-os-chrome.log' >&2
      exit 1
    fi
    sleep 1
    waited=$((waited + 1))
  done

  echo "[run_gemini_mcp] Chrome ready on ${CHROME_URL}" >&2
}

# ── Detect pro vs classic ─────────────────────────────────────────────────────

if [[ "$INPUT" == *.json ]]; then

  # ── PRO MODE ─────────────────────────────────────────────────────────────

  if [ ! -f "$INPUT" ]; then
    echo '{"error": "payload file not found"}' >&2
    exit 1
  fi

  # Ensure one persistent Chrome is running before the first Gemini call
  if ! _chrome_running; then
    _launch_chrome
  else
    echo "[run_gemini_mcp] reusing existing Chrome on ${CHROME_URL}" >&2
  fi

  # Ensure ~/.gemini/settings.json routes MCP to our Chrome
  _patch_gemini_settings

  # Read instruction and url from the JSON payload file
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
    TASK_TEXT="Navigate to $URL. Then: $INSTRUCTION"
  else
    TASK_TEXT="$INSTRUCTION"
  fi

  PROMPT="$TASK_TEXT

IMPORTANT: After performing the action, respond ONLY with a single JSON object.
No markdown fences. No explanation. No extra text. Just the JSON.

Required JSON structure:
{
  \"action\": \"click\" or \"type\" or \"scroll\" or \"hover\" or \"navigate\",
  \"text\": \"text you typed (only include if action is type)\",
  \"element\": {
    \"css_selector\": \"the exact CSS selector of the element you interacted with\",
    \"id\": \"element id attribute if it has one\",
    \"data-testid\": \"data-testid value if present\",
    \"aria-label\": \"aria-label value if present\",
    \"xpath\": \"XPath expression as fallback\"
  }
}"

  gemini --yolo <<EOF
/ide disable
Using chrome-devtools MCP.
$PROMPT
/quit
EOF

else

  # ── CLASSIC MODE ─────────────────────────────────────────────────────────
  # No Chrome management. Gemini/MCP handles its own browser lifecycle.
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