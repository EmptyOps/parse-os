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
from os_automation.repos.chrome_devtools_mcp_adapter import ChromeDevToolsMCPAdapter
from os_automation.repos.gemini_chrome_devtools_mcp_adapter import GeminiChromeDevToolsMCPAdapter

def _load_config():
    cfg_path = Path(__file__).resolve().parents[2] / "configs" / "repos.yaml"
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f) or {}
    
class Orchestrator:
    def __init__(self, config_tool_override: str = None, config_detection_override: str = None,
                 detection_name: str = None, executor_name: str = None, mcp_adapter: str = None):
        self.config = _load_config()

        # Register adapters (store classes or factory lambdas)
        registry.register_adapter("omniparser", OmniParserAdapter)
        registry.register_adapter("osatlas", OSAtlasAdapter)
        registry.register_adapter("pyautogui", PyAutoGUIAdapter)
        registry.register_adapter("sikuli", SikuliAdapter)
        registry.register_adapter("mcp_filesystem", MCPFileSystemAdapter)
        registry.register_adapter("mcp_chrome_devtools", ChromeDevToolsMCPAdapter)
        registry.register_adapter("gemini_mcp_chrome_devtools", GeminiChromeDevToolsMCPAdapter)

        # Dynamically register OpenComputerUse adapter if available
        try:
            from os_automation.repos.open_computer_use_adapter import OpenComputerUseAdapter
            registry.register_adapter("open_computer_use", OpenComputerUseAdapter)
        except ImportError:
            pass
        
        # # Auto-register MCP adapters
        # try:
        #     from os_automation.repos.chrome_devtools_mcp_adapter import ChromeDevToolsMCPAdapter
        #     registry.register_adapter("mcp_chrome_devtools", ChromeDevToolsMCPAdapter)
        # except Exception:
        #     pass

        # Determine defaults from config.yaml
        default_detection = (self.config.get("default_tools", {}) or {}).get("detection", "omniparser")
        default_executor = (self.config.get("default_tools", {}) or {}).get("executor", "pyautogui")
        default_mcp = (self.config.get("default_tools", {}) or {}).get("mcp", None)

        # Prioritize explicit parameters: detection_name / executor_name > overrides > config defaults
        self.detection_choice = detection_name or config_detection_override or default_detection
        self.executor_choice = executor_name or config_tool_override or default_executor
        self.mcp_choice = mcp_adapter or default_mcp

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

    def _dispatch_mcp(self, parsed_plan: dict):
        mcp = parsed_plan.get("mcp")
        if not mcp:
            return None

        adapter_name = mcp.get("adapter")
        task = mcp.get("task")

        adapter_factory = registry.get_adapter(adapter_name)
        if adapter_factory is None:
            raise RuntimeError(f"MCP adapter not found: {adapter_name}")

        adapter = adapter_factory() if callable(adapter_factory) else adapter_factory

        print(f"[MCP] Executing via adapter '{adapter_name}'")

        result = adapter.execute({"task": task})

        # 🔒 TERMINAL RESULT
        return {
            "mode": "mcp",
            "adapter": adapter_name,
            "result": result,
        }


    def run(self, user_prompt: str, image_path: str = None):
        """
        Adaptive run:
        - If executor adapter is FULL => delegate to adapter.execute with the prompt.
        - If PARTIAL => run local plan -> execute via executor_agent -> validate.
        - If HYBRID => mix responsibilities (example stub, customize per-repo).
        """
        
        # =====================================================
        # 🔥 MCP HARD ROUTING (NO PLANNING)
        # =====================================================
        mcp_adapter = self.main_agent.can_use_mcp(user_prompt)
        if mcp_adapter:
            adapter_factory = registry.get_adapter(mcp_adapter)
            if adapter_factory is None:
                raise RuntimeError(f"MCP adapter '{mcp_adapter}' not registered")

            adapter = adapter_factory() if callable(adapter_factory) else adapter_factory

            print(f"[MCP] Direct routing to '{mcp_adapter}' (planner skipped)")
            return {
                "mode": "mcp",
                "adapter": mcp_adapter,
                "result": adapter.execute({"task": user_prompt}),
            }
            
        # =====================================================
        # 🔥 1️⃣ PLANNER FIRST (MCP-aware)
        # =====================================================
        yaml_text = self.main_agent.plan(user_prompt)
        parsed = yaml.safe_load(yaml_text)
        
        # # 🔥 MCP = TERMINAL EXECUTION MODE
        # mcp_result = self._dispatch_mcp(parsed)
        # if mcp_result is not None:
        #     return mcp_result

        # # 🔥 MCP SHORT-CIRCUIT
        # if isinstance(parsed, dict) and "mcp" in parsed:
        #     mcp_info = parsed["mcp"]
        #     adapter_name = mcp_info.get("adapter")

        #     adapter_factory = registry.get_adapter(adapter_name)
        #     if adapter_factory is None:
        #         raise ValueError(f"MCP adapter '{adapter_name}' not registered")

        #     adapter = adapter_factory() if callable(adapter_factory) else adapter_factory

        #     print(f"[MCP] Routing task to '{adapter_name}'")
        #     return adapter.execute(mcp_info)

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
            # yaml_text = self.main_agent.plan(user_prompt)

            # Convert YAML → PlannedStep list
            try:
                
                parsed = yaml.safe_load(yaml_text)
                
                if not isinstance(parsed, dict) or "steps" not in parsed:
                    raise ValueError(f"Planner returned invalid YAML: {yaml_text}")

                from os_automation.core.tal import PlannedStep
                planned_steps = [
                    PlannedStep(step_id=s["step_id"], description=s["description"])
                    for s in parsed["steps"]
                ]

            except Exception as e:
                
                return {
                    "user_prompt": user_prompt,
                    "overall_status": "failed",
                    "reason": f"Planner error: {e}",
                    "raw_yaml": yaml_text,
                    "mode": "partial"
                }

            final_step_reports = []


            for step in planned_steps:
                print(f"\n========== RUNNING STEP {step.step_id}: {step.description} ==========")

                step_result = self.executor_agent.run_step(
                    step_id=step.step_id,
                    step_description=step.description,
                    validator_agent=self.validator_agent,
                    max_attempts=3
                )

                # ---- Store into final report list ----
                step_report = {
                    "step": step.dict(),
                    "execution": step_result.get("execution"),
                    "validation": step_result.get("validation")
                }
                final_step_reports.append(step_report)

                # ---- Feed observation into planner memory ----
                observation = step_result.get("validation", {}).get("observation")
                self.main_agent.receive_observation(step.step_id, step.description, observation)

                # ---- Ask main agent if next step should change ----
                next_steps = self.main_agent.decide_next_step()

                if next_steps is None:
                    continue  # proceed normally

                # ---- Run replacement steps (dynamic replanning engine) ----
                for ns in next_steps:
                    ns_desc = ns["description"]
                    tmp = self.executor_agent.run_step(
                        step_id=ns.get("step_id", 9999),
                        step_description=ns_desc,
                        validator_agent=self.validator_agent,
                        max_attempts=1
                    )

                    final_step_reports.append({
                        "step": {"step_id": ns.get("step_id", 9999), "description": ns_desc},
                        "execution": tmp.get("execution"),
                        "validation": tmp.get("validation")
                    })
        
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
