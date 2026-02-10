#!/usr/bin/env bash
set -e

export TERM=dumb
export NO_COLOR=1
export GEMINI_NO_COLOR=1

gemini --yolo <<EOF
/ide disable
Using chrome-devtools MCP.
EOF