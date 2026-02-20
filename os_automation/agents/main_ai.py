# os_automation/agents/main_ai.py

import os
import platform
import yaml
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI   # Official client
from os_automation.core.lifecycle import lifecycle

logger = logging.getLogger(__name__)


import re  # you already use re in decide_event_llm, but if it's not imported globally, add this.

def _extract_raw_yaml_block(text: str) -> str:
    """
    Normalize model output:
    - If it contains a ```yaml ... ``` fenced block, extract the inner YAML.
    - Otherwise, return the text as-is.
    """
    if not text:
        return text

    # Match ```yaml ... ``` or ```yml ... ``` or just ``` ... ```
    fence_pattern = re.compile(
        r"```(?:yaml|yml)?\s*(.*?)```",
        re.DOTALL | re.IGNORECASE
    )
    m = fence_pattern.search(text)
    if m:
        return m.group(1).strip()

    return text.strip()


class MainAIAgent:
    """
    LLM-driven planner + replan logic.
    Produces atomic OS micro-steps compatible with ExecutorAgent + ValidatorAgent.
    """

    def __init__(self, model: str = "gpt-4o"):
      
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # ==== NEW FIELDS FOR OPENCOMPUTERUSE STYLE FEEDBACK LOOPS ====
        self.history: List[Dict[str, Any]] = []
        self.original_prompt: Optional[str] = None
        
        
    def can_use_mcp(self, user_prompt: str) -> Optional[str]:
        """
        Decide whether this task should be routed to an MCP server.
        Returns adapter name if yes, otherwise None.
        """

        text = user_prompt.lower()

        # Browser / web / devtools signals
        chrome_keywords = [
            "browser",
            "website",
            "web page",
            "open url",
            "inspect",
            "devtools",
            "dom",
            "css",
            "html",
            "console",
            "network tab",
            "elements tab",
            "run javascript",
            "click button",
            "fill form",
            "web automation",
            "browser automation",
            "test website"
        ]

        if any(k in text for k in chrome_keywords):
            # return "mcp_chrome_devtools"
            return "gemini_mcp_chrome_devtools"

        return None

    # -----------------------------------------------------
    # Step 1 — High-level → micro-plan
    # -----------------------------------------------------
    def plan(self, user_prompt: str) -> str:
        """
        Use an LLM to convert a natural-language task into micro-steps.
        MUST produce atomic actions, never combined steps.
        """
        system_os = platform.system()  # Linux / Darwin / Windows
        
        # # 🔥 MCP ROUTING DECISION (NEW)
        # mcp_adapter = self.can_use_mcp(user_prompt)
        # if mcp_adapter:
        #     return yaml.safe_dump(
        #         {
        #             "mcp": {
        #                 "adapter": mcp_adapter,
        #                 "task": user_prompt
        #             }
        #         },
        #         sort_keys=False
        #     )

        # # existing logic continues unchanged
        # # 🔥 REQUIRED FOR OBSERVATION-DRIVEN PLANNING
        # self.original_prompt = user_prompt
        # self.history = []
        
        mcp_adapter = self.can_use_mcp(user_prompt)
        if mcp_adapter:
            return yaml.safe_dump(
                {
                    "mcp": {
                        "adapter": mcp_adapter,
                        "task": user_prompt
                    }
                },
                sort_keys=False
            )
        
        # ⬇️ ONLY NON-MCP TASKS REACH HERE
        self.original_prompt = user_prompt
        self.history = []

        system_prompt = """
        
SYSTEM CONTEXT
--------------
- Current operating system: {system_os}
- Plan the steps according to system os

You are an OS automation planner for a 3-agent system:
- Main planner (you)
- Executor (does clicks/typing using PyAutoGUI + OS-Atlas)
- Validator (checks screenshots + OCR + LLM)

Your job:
- Read the user's instruction.
- Think about the most reliable way to complete it (GUI vs terminal).
- Output a **YAML-only micro-plan** that the Executor can follow step-by-step.

COMMAND RULES
-------------
- Linux screenshot command: gnome-screenshot -f <path>
- macOS screenshot command: screencapture <path>
- Windows screenshot command: powershell screenshot / snipping tool

NAVIGATION RULE (MANDATORY)
--------------------------
- NEVER use abstract verbs like:
  "navigate", "go to", "move to", "open location"

- File navigation MUST be expressed as:
  - "Click <folder> folder"
  - "Double click <folder> folder in file list"

- If a location exists in a sidebar or tree, ALWAYS click it.
- NEVER type navigation text unless explicitly stated.

APPLICATION LAUNCH RULE (CRITICAL)
---------------------------------
If the task involves opening ANY OS application:

You MUST:
1) Open the OS application launcher using os launcher action according to the OS system type
2) Type the application name
3) Press Enter
4) Wait for the application window

NEVER attempt to click application icons directly on the desktop or taskbar.
This rule applies to ALL applications except File Explorer, Visual Studio Code(VS Code).

OS LAUNCHER ACTIONS (MANDATORY)
------------------------------
When opening any OS application, use these exact steps:

Windows:
- "Press Windows key"

macOS:
- "Press Command+Space"

Linux:
- "Press Super key"

KEYBOARD-FIRST RULE (CRITICAL)
------------------------------
If a task can be completed using only keyboard input
(numbers, operators, Enter, shortcuts, typing):

- ALWAYS prefer keyboard actions over GUI clicks.
- Use "Type 'text'" or "Press <key>" instead of clicking buttons.
- DO NOT use "Click <button>" when a direct keypress exists.

Examples:
- Calculator:
  - Use "Type '10'", "Press '+'", "Type '500'", "Press '='"
  - NOT "Click '+' button" or "Click '=' button"

- Forms:
  - Use typing + Enter instead of clicking submit buttons

- Search:
  - Use Enter instead of clicking search icon


WAIT RULE (CRITICAL)
-------------------
After opening any application or launcher, you MUST include:
- "Wait for application to open"

This step is NOT optional.

CORE BEHAVIOR
-------------
1) Use reasoning + common sense:
   - If the task clearly belongs to a GUI app → plan GUI steps.
   - If the task is purely file/terminal oriented and user never mentions GUI → plan terminal steps.
   - If user says “using terminal / with command / in shell” → use terminal only.
   - If user mentions an app (Chrome, VS Code, Excel, etc.) → open/operate *inside that app*.
   - Do not assume app is open unless user clearly implies it.

2) VS CODE + FILES (IMPORTANT)
   - ✅ If user says anything like:
        "open VS Code and create hello.py"
        "in VS Code create a new file"
     → You MUST work through the VS Code UI:
        - Open VS Code (see rules below)
        - Click VSCode Explorer icon
        - Click New File button
        - Type 'hello.py'
        - Press Enter
   - ✅ Default way to open VS Code (when user wants VS Code) is:
        - "Open Terminal"
        - "Type 'code --new-window'"
        - "Press Enter"
   - ❌ DO NOT use touch/echo/cat to create files when the user wants to work in an editor.
   - ✅ If user only says "create file hello.py" with no editor mention:
        - Use terminal: open terminal, run command, etc.

3) TERMINAL vs GUI
   - If the user mentions websites, browsers, buttons, menus → use GUI steps.
   - If the user says "list files", "run script", "git status" with no GUI → use terminal.
   - Avoid mixing GUI and terminal randomly. Choose a coherent path per task.

4) STEP FORMAT (MUST BE ATOMIC)
Each step must represent exactly ONE atomic action.
Description MUST start with one of:

  ### TERMINAL / GENERIC ###
  - "Open Terminal"
  - "Run command 'xxx'"
  - "Type 'text'"
  - "Press Enter"

  ### APPLICATION / GUI ###
  - "Open the browser"
  - "Open Chrome"
  - "Open VS Code"
  - "Click <target>"
  - "Double click <target>"
  - "Right click <target>"
  - "Scroll Down"
  - "Scroll Up"

  ### VS CODE SPECIFIC ###
  - "Click VSCode Explorer icon"
  - "Click New File button"
  - "Click File menu"
  - "Click Save As option"
  - "Click filename field"
  - "Click Run button"
  - "Click Extensions icon"

RULES
-----
- NEVER combine actions in one step. One step = one event.
- Always wrap typed text in single quotes: Type 'hello.py'
- Be specific: "Click New File button" instead of "Click button".
- Do NOT invent irrelevant apps (no random browser open if user asked for terminal).

FORBIDDEN DESCRIPTIONS
---------------------
Do NOT use vague actions such as:
- wait for
- ensure
- focus
- verify

Use only explicit actions:
- Press
- Click
- Type
- Wait

OUTPUT FORMAT (VERY IMPORTANT)
------------------------------
- Output MUST be **pure YAML**, no explanations.
- DO NOT wrap it in ```yaml ... ``` or any code fences.
- Structure:

steps:
  - step_id: 1
    description: "..."
  - step_id: 2
    description: "..."
  - step_id: 3
    description: "..."

EXAMPLES
--------

User: "Open text editor in system and types 'Meeting at 5' and save it using CTRL+S on Documents/Vedanshi folder as TestingNote.txt"
steps:
  - step_id: 1
    description: "Press Super key"
  - step_id: 2
    description: "Type 'Text Editor'"
  - step_id: 3
    description: "Press Enter"
  - step_id: 4
    description: "Wait for application to open"
  - step_id: 5
    description: "Type 'Meeting at 5'"
  - step_id: 6
    description: "Press Ctrl+S"
  - step_id: 7
    description: "Type '/home/emptyops/Documents/Vedanshi/TestingNote.txt'"
  - step_id: 8
    description: "Press Enter"

User: "take a screenshot of current screen and save it as imageTest.png on Documents folder"
steps:
  - step_id: 1
    description: "Open Terminal"
  - step_id: 2
    description: "Type 'gnome-screenshot -f /home/emptyops/Documents/imageTest.png'"
  - step_id: 3
    description: "Press Enter"


User: "Search for dogs on Google"
steps:
  - step_id: 1
    description: "Open the browser"
  - step_id: 2
    description: "Click browser address bar"
  - step_id: 3
    description: "Type 'dogs'"
  - step_id: 4
    description: "Press Enter"

User: "Create python file hello.py in VS Code"
steps:
  - step_id: 1
    description: "Open Terminal"
  - step_id: 2
    description: "Type 'code --new-window'"
  - step_id: 3
    description: "Press Enter"
  - step_id: 4
    description: "Wait for application to open"
  - step_id: 5
    description: "Press Ctrl+N"
  - step_id: 6
    description: "Press Ctrl+S"
  - step_id: 7
    description: "Type 'hello.py'"
  - step_id: 8
    description: "Press Enter"
    
User: "Create python file hello.py in VS Code, write 'Hello World' code and save it on Documents/Vedanshi"
steps:
  - step_id: 1
    description: "Open Terminal"
  - step_id: 2
    description: "Type 'code --new-window'"
  - step_id: 3
    description: "Press Enter"
  - step_id: 4
    description: "Wait for application to open"
  - step_id: 5
    description: "Press Ctrl+N"
  - step_id: 6
    description: "Type 'print(\"Hello World\")'"
  - step_id: 7
    description: "Press Ctrl+S"
  - step_id: 8
    description: "Type '/home/emptyops/Documents/Vedanshi/hello.py'"
  - step_id: 9
    description: "Press Enter"
""".strip()

        #lifecycle - emit  
        context = {
            "user_prompt": user_prompt,
            "system_prompt": system_prompt,
        }

        lifecycle.emit("before_plan", context)
        system_prompt = context.get("system_prompt", system_prompt)
        

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )

        raw_text = response.choices[0].message.content or ""
        print("\n===== PLANNER RAW OUTPUT =====\n", raw_text, "\n========================\n")

        # 🔧 Strip ```yaml fences or any code formatting if model ignored instructions
        yaml_text = _extract_raw_yaml_block(raw_text)

        # Ensure valid YAML
        try:
            parsed = yaml.safe_load(yaml_text)
            if not isinstance(parsed, dict) or "steps" not in parsed:
                raise ValueError("Planner returned invalid YAML structure")
              
            # lifecycle - emit
            context = {
                "user_prompt": user_prompt,
                "yaml_text": yaml_text,
            }
            lifecycle.emit("after_plan", context)
            yaml_text = context.get("yaml_text", yaml_text)
                
            return yaml_text
        except Exception as e:
            logger.error("Planner failed to produce YAML: %s", yaml_text)
            raise e
        
        

    # -----------------------------------------------------
    # Step 2 — Replan on failure
    # -----------------------------------------------------
    def replan_on_failure(self, user_prompt: str, failed_step_yaml: str, failure_details_yaml: str) -> str:
        """
        Ask the LLM to fix ONLY the failed part of the plan.
        Produce new micro-steps as YAML (same format as plan()).
        """

        system_prompt = """
SYSTEM CONTEXT
--------------
- Current operating system: {system_os}        

You are an OS automation planner performing a REPLAN.

Context:
- The original user prompt describes the overall task.
- One step (or a small set of steps) failed during execution/validation.
- You must use reasoning and common sense to produce a better plan around that failure.

GENERAL RULES
-------------
- Think about WHY it failed:
  - Was the target ambiguous?
  - Was a window not open yet?
  - Did we skip an obvious prerequisite step?
  - Did we choose terminal when GUI was expected, or vice versa?

- Fix ONLY what is necessary:
  - You can replace the failed step with a short sequence of more robust steps.
  - You can insert missing prerequisite steps.
  - Do NOT replan the entire world if a local fix is enough.

- Respect the same behavior rules as the main planner:
  - Prefer GUI for GUI tasks.
  - Use terminal only when appropriate or explicitly requested.
  - For VS Code file creation/editing, use proper VS Code UI steps (Explorer → New File, etc.).
  - Use terminal to launch VS Code by default:
      "Open Terminal" → "Type 'code --new-window'" → "Press Enter"

STEP FORMAT (MUST MATCH MAIN PLANNER)
-------------------------------------
Each step description MUST start with one of:

  - "Open Terminal"
  - "Run command 'xxx'"
  - "Type 'text'"
  - "Press Enter"
  - "Open the browser"
  - "Open Chrome"
  - "Open VS Code"
  - "Click <target>"
  - "Double click <target>"
  - "Right click <target>"
  - "Scroll Down"
  - "Scroll Up"
  - "Click VSCode Explorer icon"
  - "Click New File button"
  - "Click File menu"
  - "Click Save As option"
  - "Click filename field"
  - "Click Run button"
  - "Click Extensions icon"

RULES
-----
- One atomic action per step.
- Be explicit and clear about targets (e.g., "Click New File button", not "Click button").
- Wrap typed text in single quotes.
- Do NOT invent irrelevant steps or applications.

If a step failed, you may assume the application is NOT open,
unless explicitly proven otherwise.


OUTPUT FORMAT
-------------
- Output MUST be pure YAML, no explanations, no code fences.
- Only this structure:

steps:
  - step_id: 1
    description: "..."
  - step_id: 2
    description: "..."

Example (conceptual):

User: "Create hello.py in VS Code"
If "Click New File button" failed, you might output:

steps:
  - step_id: 1
    description: "Click VSCode Explorer icon"
  - step_id: 2
    description: "Click New File button"
  - step_id: 3
    description: "Click filename field"
  - step_id: 4
    description: "Type 'hello.py'"
  - step_id: 5
    description: "Press Enter"
""".strip()

        content = f"""
The user prompt was:
{user_prompt}

The failing step (YAML) was:
{failed_step_yaml}

Execution + validation details were:
{failure_details_yaml}

Now generate a corrected sequence of micro-steps (YAML only, no fences) that can fix or bypass this failure.
"""

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ]
        )

        raw_text = response.choices[0].message.content or ""
        # Clean up any ```yaml fences just in case
        yaml_text = _extract_raw_yaml_block(raw_text)

        # Validate YAML
        try:
            parsed = yaml.safe_load(yaml_text)
            if isinstance(parsed, dict) and "steps" in parsed:
                return yaml_text
            else:
                raise ValueError("Replan output invalid structure")
        except Exception:
            # deterministic escalation
            return yaml.safe_dump({
                "escalation": {
                    "reason": "step_failed_4_times",
                    "original_prompt": user_prompt,
                    "failed_step": yaml.safe_load(failed_step_yaml),
                    "failure_details": yaml.safe_load(failure_details_yaml),
                    "raw_replan_text": raw_text,
                    "suggested_manual_steps": [
                        "Manually inspect the before/after screenshots.",
                        "Check if the UI changed (layout, theme, language).",
                        "Try writing a more explicit instruction for the failed step."
                    ]
                }
            }, sort_keys=False)
            
    def decide_event_llm(self, description: str, bbox: Optional[list] = None, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Ask the LLM what action to take for this step given a bbox (or screenshot).
        Returns a dict like: {"event": "click"} or {"event": "type", "text": "X"} or {"event": "keypress", "key":"enter"}.
        This method uses a constrained-response prompt and attempts to parse JSON from the model.
        """
        import json, textwrap
        system = textwrap.dedent("""
        You are an OS automation decision helper. Given a single short GUI instruction and optionally
        a bounding box (area) or screenshot context, choose the best action from the following:
         - click
         - click_at (include coords)
         - double_click
         - right_click
         - type (include text)
         - keypress (include key like 'enter')
         - scroll (direction up/down)
         - noop (do nothing / wait)
        Output MUST be a single JSON object on one line with keys:
         - event: one of the above
         - text: optional (for type)
         - key: optional (for keypress)
         - coords: optional [x,int,y,int] for click_at
        Example valid output: {"event":"click"} or {"event":"type","text":"hello"}.
        Keep output strictly JSON (no extra commentary).
        """)
        user_content = f"Instruction: {description}\nBbox: {bbox}\nImagePath: {image_path}\nDecide the best single event."
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=200
            )
            text = resp.choices[0].message.content.strip()

            # Try parse JSON (model might reply clean JSON). If it returns code fence, strip it.
            import re
            m = re.search(r"\{.*\}", text, re.DOTALL)
            jtext = m.group(0) if m else text

            parsed = json.loads(jtext)
            # normalize keys
            evt = {"event": parsed.get("event")}
            if parsed.get("text"):
                evt["text"] = parsed.get("text")
            if parsed.get("key"):
                evt["key"] = parsed.get("key")
            if parsed.get("coords"):
                evt["coords"] = parsed.get("coords")
            return evt
        except Exception as e:
            # on failure, fallback to safe local heuristic (caller can handle)
            logger.debug("decide_event_llm failed: %s", e)
            return {"event": "unknown"}


    def rewrite_ui_query(self, description: str) -> Optional[str]:
        """
        Convert a UI description like:
            'Click first link'
        into a short visual query like:
            'YouTube'
            'first video'
            'YouTube icon'
            'video thumbnail'
        """
        system = """
You rewrite UI descriptions into short text target queries that help detect
GUI elements visually. 
Output a single short phrase, no JSON, no explanation.
Examples:
- 'Click first link' → 'YouTube'
- 'Click first result' → 'YouTube'
- 'Open Gmail button' → 'Gmail'
- 'Click profile icon' → 'profile'
The output must be <= 3 words.
"""

        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": description},
            ]
        )

        return resp.choices[0].message.content.strip()


    def receive_observation(self, step_id: int, description: str, observation: str):
        """
          Store the effect of each action so the LLM can reason about what happened.
        """
        self.history.append({
            "step_id": step_id,
            "description": description,
            "observation": observation
        })


    def decide_next_step(self) -> Optional[List[Dict[str, Any]]]:
        """
        Ask LLM whether plan should change based on recent observations.
        If no change needed → return None.
        If plan should adjust → return a list of new steps (same YAML structure as planner).
        """

        if not self.history:
            return None

        prompt = f"""
    User objective:
    {self.original_prompt}

    Steps executed so far:
    {yaml.safe_dump(self.history)}

    Should we continue with the original next step OR adjust the plan?
    IF adjustment needed, output YAML of new steps (same format as planner).
    IF no adjustment needed, output: `continue` only.
    """

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.choices[0].message.content.strip()

        if raw.lower() == "continue":
            return None

        raw = _extract_raw_yaml_block(raw)
        try:
            parsed = yaml.safe_load(raw)
            if isinstance(parsed, dict) and "steps" in parsed:
                return parsed["steps"]
        except:
            return None

        return None
