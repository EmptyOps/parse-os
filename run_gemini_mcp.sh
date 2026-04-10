#!/usr/bin/env bash
# run_gemini_mcp.sh
#
# Two modes depending on what $1 is:
#
# CLASSIC MODE ($1 = plain task string):
#   Called by parse-os's GeminiChromeDevToolsMCPAdapter for full browser tasks.
#   Passes the task string directly to Gemini. Gemini handles the full task.
#   Example: run_gemini_mcp.sh "search for python tutorials on google"
#
# PRO MODE ($1 = path to a .json file):
#   Called by parse-os-pro's MCPStepService for one step at a time.
#   Reads instruction + url from the JSON file.
#   Instructs Gemini to respond with structured JSON containing the selector.
#   Example: run_gemini_mcp.sh /tmp/step_payload_abc.json
#
# JSON file format (pro mode input):
#   { "instruction": "click the login button", "url": "https://example.com" }
#
# Gemini response format (pro mode output):
#   {
#     "action": "click",
#     "element": {
#       "css_selector": "#login-btn",
#       "id": "login-btn",
#       "data-testid": "login-button",
#       "aria-label": "Login",
#       "xpath": "//button[@id='login-btn']"
#     }
#   }

set -e

INPUT="$1"

if [ -z "$INPUT" ]; then
  echo "No task or payload file provided"
  exit 1
fi

export TERM=dumb
export NO_COLOR=1
export GEMINI_NO_COLOR=1

# ── Detect pro vs classic ─────────────────────────────────────────────────────

if [[ "$INPUT" == *.json ]]; then

  # ── PRO MODE: read instruction and url from JSON file ─────────────────────
  if [ ! -f "$INPUT" ]; then
    echo '{"error": "payload file not found"}' >&2
    exit 1
  fi

  INSTRUCTION=$(python3 -c "import json; d=json.load(open('$INPUT')); print(d.get('instruction',''))")
  URL=$(python3 -c "import json; d=json.load(open('$INPUT')); print(d.get('url',''))" 2>/dev/null || echo "")

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

  # ── CLASSIC MODE: pass plain task string directly to Gemini ───────────────
  TASK="$INPUT"

  gemini --yolo <<EOF
/ide disable
Using chrome-devtools MCP.
$TASK
/quit
EOF

fi