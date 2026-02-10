#!/usr/bin/env bash
set -e

TASK="$1"

if [ -z "$TASK" ]; then
  echo "No task provided"
  exit 1
fi

export TERM=dumb
export NO_COLOR=1
export GEMINI_NO_COLOR=1

gemini --yolo <<EOF
/ide disable
Using chrome-devtools MCP.
$TASK
/quit
EOF