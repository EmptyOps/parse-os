# # os_automation/core/orchestrator.py
import yaml
from pathlib import Path
from os_automation.core.tal import ExecutionResult
from os_automation.core.registry import registry
from os_automation.repos.omniparser_adapter import OmniParserAdapter
from os_automation.repos.osatlas_adapter import OSAtlasAdapter
from os_automation.repos.pyautogui_adapter import PyAutoGUIAdapter
from os_automation.repos.sikuli_adapter import SikuliAdapter
from os_automation.agents.main_ai import MainAIAgent
from os_automation.agents.executor_agent import ExecutorAgent
from os_automation.agents.validator_agent import ValidatorAgent
from os_automation.repos.mcp_adapter import MCPFileSystemAdapter
from os_automation.core.integration_contract import IntegrationMode

def _load_config():
    cfg_path = Path(__file__).resolve().parents[2] / "configs" / "repos.yaml"
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f) or {}

# class Orchestrator:
#     def __init__(self, config_tool_override: str = None, config_detection_override: str = None,
#                  detection_name: str = None, executor_name: str = None):
#         self.config = _load_config()

#         # Register adapters (store classes or factory lambdas)
#         registry.register_adapter("omniparser", OmniParserAdapter)
#         registry.register_adapter("osatlas", OSAtlasAdapter)
#         registry.register_adapter("pyautogui", PyAutoGUIAdapter)
#         registry.register_adapter("sikuli", SikuliAdapter)
#         registry.register_adapter("mcp_filesystem", MCPFileSystemAdapter)
#         # Dynamically register OpenComputerUse adapter if available
#         try:
#             from os_automation.repos.open_computer_use_adapter import OpenComputerUseAdapter
#             registry.register_adapter("open_computer_use", OpenComputerUseAdapter)
#         except ImportError:
#             # Keep the system usable even if that repo isn't present.
#             pass

#         # Determine defaults from config.yaml
#         default_detection = (self.config.get("default_tools", {}) or {}).get("detection", "omniparser")
#         default_executor = (self.config.get("default_tools", {}) or {}).get("executor", "pyautogui")

#         # Prioritize explicit parameters: detection_name / executor_name > overrides > config defaults
#         self.detection_choice = detection_name or config_detection_override or default_detection
#         self.executor_choice = executor_name or config_tool_override or default_executor

#         # Validate that registry contains the adapters
#         for choice_name, adapter_type in [("detection", self.detection_choice), ("executor", self.executor_choice)]:
#             if registry.get_adapter(adapter_type) is None:
#                 raise ValueError(f"{choice_name.capitalize()} adapter '{adapter_type}' is not registered in registry!")

#         # Agents
#         self.main_agent = MainAIAgent()
#         self.executor_agent = ExecutorAgent(
#             default_detection=self.detection_choice,
#             default_executor=self.executor_choice
#         )
#         self.validator_agent = ValidatorAgent()

#         # Cache adapter contracts
#         self.executor_contract = registry.get_contract(self.executor_choice)
#         self.detection_contract = registry.get_contract(self.detection_choice)


#     def run(self, user_prompt: str, image_path: str = None):
#         """
#         Adaptive run:
#         - If executor adapter is FULL => delegate to adapter.execute with the prompt.
#         - If PARTIAL => run local plan -> execute via executor_agent -> validate.
#         - If HYBRID => mix responsibilities (example stub, customize per-repo).
#         """
#         # Resolve adapter factory/class
#         exec_adapter_factory = registry.get_adapter(self.executor_choice)
#         exec_adapter = exec_adapter_factory() if callable(exec_adapter_factory) else exec_adapter_factory

#         mode = self.executor_contract.integration_mode if self.executor_contract else IntegrationMode.PARTIAL

        
#         if mode == IntegrationMode.FULL:
#             try:
#                 print(f"[IntegrationMode: FULL] Handing full control to '{self.executor_choice}' adapter…")

#                 # FULL adapters run their own planning, execution, validation internally.
#                 result = exec_adapter.execute({"text": user_prompt})

#                 # 🔧 If adapter already runs sandbox/streaming internally, no extra wrapping.
#                 if isinstance(result, dict) and result.get("status") == "success":
#                     print("[OpenComputerUse] Execution completed successfully.")
#                     return result

#                 # Allow adapters that return raw text or structured logs
#                 return {
#                     "status": "success",
#                     "adapter_output": result,
#                     "mode": "full",
#                     "executor": self.executor_choice
#                 }

#             except Exception as e:
#                 print(f"[OpenComputerUseAdapter] ❌ Error in FULL mode execution: {e}")
#                 return {"status": "failed", "detail": str(e)}


#         # PARTIAL mode: your original pipeline (planner -> executor_agent -> validator)
#         elif mode == IntegrationMode.PARTIAL:
#             planned_steps = self.main_agent.plan(user_prompt)
#             step_reports = []

#             # Determine if the detection adapter needs an image
#             det_adapter_factory = registry.get_adapter(self.detection_choice)
#             det_adapter = det_adapter_factory() if callable(det_adapter_factory) else det_adapter_factory

#             detections = None
#             selected_bbox = None

#             if image_path or self.detection_choice != "open_computer_use":
#                 # Only require image_path for adapters other than OpenComputerUse
#                 if not image_path:
#                     raise ValueError(f"Adapter '{self.detection_choice}' requires an image_path.")
#                 detections = det_adapter.detect({"image_path": image_path})
#                 # pick first bbox if present
#                 bboxes = []
#                 for v in (detections or {}).values():
#                     if isinstance(v, dict) and "bbox" in v:
#                         bboxes.append(v["bbox"])
#                 selected_bbox = bboxes[0] if bboxes else [10,10,50,50]
#             else:
#                 # OpenComputerUse handles screenshots internally
#                 detections = det_adapter.detect()
#                 bboxes = []
#                 for v in (detections or {}).values():
#                     if isinstance(v, dict) and "bbox" in v:
#                         bboxes.append(v["bbox"])
#                 selected_bbox = bboxes[0] if bboxes else [10,10,50,50]

#             for plan in planned_steps:
#                 desc = plan.description.lower()
#                 if "type" in desc:
#                     decided_event = "type"
#                     text = None
#                     import re
#                     m = re.search(r"['\"]([^'\"]+)['\"]", plan.description)
#                     if m:
#                         text = m.group(1)
#                 elif "enter" in desc or "press" in desc:
#                     decided_event = "keypress"
#                     text = None
#                 else:
#                     decided_event = "click"
#                     text = None

#                 bbox = selected_bbox or [10,10,50,50]
#                 exec_out = self.executor_agent.execute(
#                     bbox=bbox,
#                     event=decided_event,
#                     executor_name=self.executor_choice,
#                     text=text
#                 )
#                 # exec_result = ExecutionResult(
#                 #     step_id=plan.step_id,
#                 #     repo_used=self.executor_choice,
#                 #     decided_event=decided_event,
#                 #     status=exec_out.get("status", "failed"),
#                 #     raw={"detection": detections, "exec_details": exec_out}
#                 # )
#                 exec_result = ExecutionResult(
#                     step_id=plan.step_id,
#                     repo_used=self.executor_choice,
#                     decided_event=decided_event,
#                     status=exec_out.get("status", "failed"),
#                     screenshot_before=exec_out.get("before"),
#                     screenshot_after=exec_out.get("after"),
#                     raw={"detection": detections, "exec_details": exec_out}
#                 )

#                 val = self.validator_agent.validate_step(plan.dict(), exec_result.dict())
#                 step_reports.append({
#                     "step": plan.dict(),
#                     "execution": exec_result.dict(),
#                     "validation": val
#                 })

#             overall_status = "success" if all(r["validation"]["validation_status"] == "pass" for r in step_reports) else "failed"
#             return {
#                 "user_prompt": user_prompt,
#                 "overall_status": overall_status,
#                 "mode": "partial",
#                 "steps": step_reports
#             }

#         # HYBRID: a general example — tailor this to your adapter capabilities
#         elif mode == IntegrationMode.HYBRID:
#             # Example: external repo handles detection/planning, local executes
#             detected = None
#             try:
#                 detected = exec_adapter.detect({"image_path": image_path}) if hasattr(exec_adapter, "detect") else None
#             except Exception:
#                 detected = None

#             # Try to get a plan from the adapter if available
#             sub_plan = []
#             if hasattr(exec_adapter, "plan"):
#                 try:
#                     sub_plan = exec_adapter.plan(user_prompt) or []
#                 except Exception:
#                     sub_plan = []

#             if not sub_plan:
#                 sub_plan = self.main_agent.plan(user_prompt)

#             step_reports = []
#             selected_bbox = None
#             # pick bbox if provided by detection
#             if detected:
#                 for v in (detected or {}).values():
#                     if isinstance(v, dict) and "bbox" in v:
#                         selected_bbox = v["bbox"]
#                         break
#             selected_bbox = selected_bbox or [10,10,50,50]

#             for plan in sub_plan:
#                 # let local executor execute steps (you can also call exec_adapter.execute for parts)
#                 exec_out = self.executor_agent.execute(
#                     bbox=selected_bbox, event="click", executor_name=self.executor_choice
#                 )
#                 exec_result = ExecutionResult(
#                     step_id=getattr(plan, "step_id", 0),
#                     repo_used=self.executor_choice,
#                     decided_event="click",
#                     status=exec_out.get("status", "failed"),
#                     raw={"detection": detected, "exec_details": exec_out}
#                 )
#                 val = self.validator_agent.validate_step(plan.dict() if hasattr(plan, "dict") else dict(plan), exec_result.dict())
#                 step_reports.append({
#                     "step": plan.dict() if hasattr(plan, "dict") else dict(plan),
#                     "execution": exec_result.dict(),
#                     "validation": val
#                 })

#             overall_status = "success" if all(r["validation"]["validation_status"] == "pass" for r in step_reports) else "failed"
#             return {
#                 "user_prompt": user_prompt,
#                 "overall_status": overall_status,
#                 "mode": "hybrid",
#                 "steps": step_reports
#             }

#         else:
#             raise ValueError(f"Unsupported integration mode: {mode}")


# Other imports remain the same...
# import yaml, requests, logging, etc.

class Orchestrator:
    def __init__(self, config_tool_override: str = None, config_detection_override: str = None,
                 detection_name: str = None, executor_name: str = None):
        self.config = _load_config()

        # Register adapters (store classes or factory lambdas)
        registry.register_adapter("omniparser", OmniParserAdapter)
        registry.register_adapter("osatlas", OSAtlasAdapter)
        registry.register_adapter("pyautogui", PyAutoGUIAdapter)
        registry.register_adapter("sikuli", SikuliAdapter)
        registry.register_adapter("mcp_filesystem", MCPFileSystemAdapter)
        # Dynamically register OpenComputerUse adapter if available
        try:
            from os_automation.repos.open_computer_use_adapter import OpenComputerUseAdapter
            registry.register_adapter("open_computer_use", OpenComputerUseAdapter)
        except ImportError:
            pass

        # Determine defaults from config.yaml
        default_detection = (self.config.get("default_tools", {}) or {}).get("detection", "omniparser")
        default_executor = (self.config.get("default_tools", {}) or {}).get("executor", "pyautogui")

        # Prioritize explicit parameters: detection_name / executor_name > overrides > config defaults
        self.detection_choice = detection_name or config_detection_override or default_detection
        self.executor_choice = executor_name or config_tool_override or default_executor

        # Validate that registry contains the adapters
        for choice_name, adapter_type in [("detection", self.detection_choice), ("executor", self.executor_choice)]:
            if registry.get_adapter(adapter_type) is None:
                raise ValueError(f"{choice_name.capitalize()} adapter '{adapter_type}' is not registered in registry!")

        # Agents
        self.main_agent = MainAIAgent()
        self.executor_agent = ExecutorAgent(
            default_detection=self.detection_choice,
            default_executor=self.executor_choice
        )
        self.validator_agent = ValidatorAgent()

        # Cache adapter contracts
        self.executor_contract = registry.get_contract(self.executor_choice)
        self.detection_contract = registry.get_contract(self.detection_choice)


    def run(self, user_prompt: str, image_path: str = None):
        """
        Adaptive run:
        - If executor adapter is FULL => delegate to adapter.execute with the prompt.
        - If PARTIAL => run local plan -> execute via executor_agent -> validate.
        - If HYBRID => mix responsibilities (example stub, customize per-repo).
        """
        # Resolve adapter factory/class
        exec_adapter_factory = registry.get_adapter(self.executor_choice)
        exec_adapter = exec_adapter_factory() if callable(exec_adapter_factory) else exec_adapter_factory

        mode = self.executor_contract.integration_mode if self.executor_contract else IntegrationMode.PARTIAL

        if mode == IntegrationMode.FULL:
            try:
                print(f"[IntegrationMode: FULL] Handing full control to '{self.executor_choice}' adapter…")

                # FULL adapters run their own planning, execution, validation internally.
                result = exec_adapter.execute({"text": user_prompt})

                if isinstance(result, dict) and result.get("status") == "success":
                    print("[OpenComputerUse] Execution completed successfully.")
                    return result

                return {
                    "status": "success",
                    "adapter_output": result,
                    "mode": "full",
                    "executor": self.executor_choice
                }

            except Exception as e:
                print(f"[OpenComputerUseAdapter] ❌ Error in FULL mode execution: {e}")
                return {"status": "failed", "detail": str(e)}

        # PARTIAL mode: your original pipeline (planner -> executor_agent -> validator)
        elif mode == IntegrationMode.PARTIAL:
            print(f"[IntegrationMode: PARTIAL] Running enhanced 3-agent flow...")

            # ---------------------------
            # 1️⃣ Planner Agent → YAML steps
            # ---------------------------
            planned_steps = self.main_agent.plan(user_prompt)

            if not planned_steps:
                return {
                    "user_prompt": user_prompt,
                    "overall_status": "failed",
                    "reason": "Planner agent returned no steps",
                    "mode": "partial"
                }

            final_step_reports = []

            # ---------------------------
            # 2️⃣ Execute each step with:
            #     OSAtlas detection
            #     LLM event planning
            #     PyAutoGUI/Sikuli execution
            #     screenshot before/after
            #     validation and retry
            # ---------------------------
            for step in planned_steps:
                print(f"\n========== RUNNING STEP {step.step_id}: {step.description} ==========")

                step_result = self.executor_agent.run_step(
                    step_description=step.description,
                    validator_agent=self.validator_agent,
                    max_attempts=3
                )

                final_step_reports.append({
                    "step": step.dict(),
                    "execution": step_result.get("execution"),
                    "validation": step_result.get("validation")
                })

                # Anything except "pass" = stop workflow
                if step_result.get("validation", {}).get("validation_status") != "pass":
                    print(f"❌ Step {step.step_id} FAILED — stopping execution.")
                    return {
                        "user_prompt": user_prompt,
                        "overall_status": "failed",
                        "mode": "partial",
                        "steps": final_step_reports
                    }

            # ---------------------------
            # 3️⃣ All steps passed
            # ---------------------------
            return {
                "user_prompt": user_prompt,
                "overall_status": "success",
                "mode": "partial",
                "steps": final_step_reports
            }

        
        # HYBRID: a general example — tailor this to your adapter capabilities
        elif mode == IntegrationMode.HYBRID:
            detected = None
            try:
                detected = exec_adapter.detect({"image_path": image_path}) if hasattr(exec_adapter, "detect") else None
            except Exception:
                detected = None

            sub_plan = []
            if hasattr(exec_adapter, "plan"):
                try:
                    sub_plan = exec_adapter.plan(user_prompt) or []
                except Exception:
                    sub_plan = []

            if not sub_plan:
                sub_plan = self.main_agent.plan(user_prompt)

            step_reports = []
            selected_bbox = None
            if detected:
                for v in (detected or {}).values():
                    if isinstance(v, dict) and "bbox" in v:
                        selected_bbox = v["bbox"]
                        break
            selected_bbox = selected_bbox or [10,10,50,50]

            for plan in sub_plan:
                exec_out = self.executor_agent.execute(
                    bbox=selected_bbox, event="click", executor_name=self.executor_choice
                )
                exec_result = ExecutionResult(
                    step_id=getattr(plan, "step_id", 0),
                    repo_used=self.executor_choice,
                    decided_event="click",
                    status=exec_out.get("status", "failed"),
                    raw={"detection": detected, "exec_details": exec_out}
                )
                val = self.validator_agent.validate_step(plan.dict() if hasattr(plan, "dict") else dict(plan), exec_result.dict())
                step_reports.append({
                    "step": plan.dict() if hasattr(plan, "dict") else dict(plan),
                    "execution": exec_result.dict(),
                    "validation": val
                })

            overall_status = "success" if all(r["validation"]["validation_status"] == "pass" for r in step_reports) else "failed"
            return {
                "user_prompt": user_prompt,
                "overall_status": overall_status,
                "mode": "hybrid",
                "steps": step_reports
            }

        else:
            raise ValueError(f"Unsupported integration mode: {mode}")
