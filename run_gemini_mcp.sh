# #!/usr/bin/env bash
# set -e

# TASK="$1"

# if [ -z "$TASK" ]; then
#   echo "No task provided"
#   exit 1
# fi

# export TERM=dumb
# export NO_COLOR=1
# export GEMINI_NO_COLOR=1

# gemini --yolo <<EOF
# /ide disable
# Using chrome-devtools MCP.
# $TASK
# /quit
# EOF



#!/usr/bin/env bash
# run_gemini_mcp.sh
#
# CHANGES FROM ORIGINAL (marked <<< CHANGED):
#   Detects whether $1 is a .json file (pro mode) or a plain string (classic).
#
#   Classic mode ($1 = plain task string):
#     Behaviour IDENTICAL to original — same heredoc, same Gemini call.
#
#   Pro mode ($1 = path to JSON payload file):
#     Reads instruction + url from the JSON file.
#     Asks Gemini to respond ONLY with structured JSON containing an
#     "element" key so parse-os-pro can extract the CSS selector.
#
#   JSON response shape parse-os-pro expects:
#   {
#     "action":  "click"|"type"|"scroll"|"hover",
#     "text":    "value to type" (type actions only),
#     "element": {
#       "data-testid":  "...",
#       "id":           "...",
#       "aria-label":   "...",
#       "css_selector": "full CSS selector",
#       "xpath":        "XPath fallback"
#     }
#   }


#!/usr/bin/env bash


set -e

INPUT="$1"

if [ -z "$INPUT" ]; then
  echo "No task or payload file provided"
  exit 1
fi

export TERM=dumb
export NO_COLOR=1
export GEMINI_NO_COLOR=1

# ── Detect mode ───────────────────────────────────────────────────────────────

if [[ "$INPUT" == *.json ]]; then
  # <<< CHANGED: pro mode — JSON file payload

  if [ ! -f "$INPUT" ]; then
    echo '{"error": "payload file not found"}' >&2
    exit 1
  fi

  INSTRUCTION=$(python3 -c "import json,sys; d=json.load(open('$INPUT')); print(d.get('instruction',''))")
  URL=$(python3 -c "import json,sys; d=json.load(open('$INPUT')); print(d.get('url',''))" 2>/dev/null || echo "")

  if [ -n "$URL" ]; then
    TASK_TEXT="Navigate to $URL. Then: $INSTRUCTION"
  else
    TASK_TEXT="$INSTRUCTION"
  fi

  PROMPT="$TASK_TEXT

IMPORTANT: Respond ONLY with a single JSON object. No markdown, no explanation.
Required structure:
{
  \"action\": \"click\" or \"type\" or \"scroll\" or \"hover\",
  \"text\": \"text to type if action is type, otherwise omit this key\",
  \"element\": {
    \"data-testid\": \"value if present, otherwise omit\",
    \"id\": \"element id if present, otherwise omit\",
    \"aria-label\": \"value if present, otherwise omit\",
    \"css_selector\": \"full CSS selector\",
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
  # <<< UNCHANGED: classic mode — identical to original

  TASK="$INPUT"

  gemini --yolo <<EOF
/ide disable
Using chrome-devtools MCP.
$TASK
/quit
EOF

fi