# os_automation/agents/main_ai.py
from typing import List
from os_automation.core.tal import PlannedStep

class MainAIAgent:
    def plan(self, user_prompt: str) -> List[PlannedStep]:
        steps = []
        if "terminal" in user_prompt.lower() and "ls" in user_prompt.lower():
            steps.append(PlannedStep(step_id=1, description="Open the terminal application"))
            steps.append(PlannedStep(step_id=2, description="Type 'ls' and execute"))
        else:
            steps.append(PlannedStep(step_id=1, description=user_prompt))
        return steps
