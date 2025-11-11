# os_automation/repos/open_computer_use_adapter.py
import asyncio
import importlib.util
import os
import sys
from typing import Any, Optional
from os_automation.core.adapters import BaseAdapter
from os_automation.core.integration_contract import IntegrationMode
from os_automation.utils.logger import log

class OpenComputerUseAdapter(BaseAdapter):
    """
    Adapter for fully interactive OpenComputerUse integration.
    This version manages its own asyncio lifecycle so Parse OS can call it synchronously.
    """
    integration_mode = IntegrationMode.FULL
    capabilities = ["planning", "execution", "validation"]

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = base_path or os.path.expanduser(
            "~/Documents/Vedanshi/OpenComputerUse/open-computer-use"
        )
        self.oc_module: Optional[Any] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.sandbox_task: Optional[asyncio.Task] = None

    def _load_oc_module(self):
        """Load the OpenComputerUse main.py module dynamically."""
        if self.oc_module:
            return self.oc_module

        main_path = os.path.join(self.base_path, "main.py")
        if not os.path.exists(main_path):
            raise FileNotFoundError(f"OpenComputerUse main.py not found at {main_path}")

        # ensure repo path is importable
        if self.base_path not in sys.path:
            sys.path.insert(0, self.base_path)

        spec = importlib.util.spec_from_file_location("open_computer_use.main", main_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["open_computer_use.main"] = module
        spec.loader.exec_module(module)
        self.oc_module = module
        return self.oc_module

    def detect(self, params=None):
        """Simulate screen detection (keeps previous behavior)."""
        log.info("🖼️ Running OpenComputerUse detection...")
        result = {"screen": {"bbox": [0, 0, 1920, 1080], "status": "detected"}}
        log.info("✅ Detection finished.")
        return result

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """
        Ensure there is a usable event loop for this adapter.
        If an asyncio loop is already running in the current thread, return it.
        Otherwise create a new loop and set it as the running loop for this thread.
        """
        try:
            # If code is running inside an async context, get_running_loop() will succeed.
            return asyncio.get_running_loop()
        except RuntimeError:
            # No running loop in this thread — create one and set it.
            if self.loop and not self.loop.is_closed():
                return self.loop
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            return self.loop

    def start(self):
        """Start the OpenComputerUse event loop interactively (if needed)."""
        oc = self._load_oc_module()
        loop = self._ensure_loop()

        # If the repository itself expects a long-running background task, we can start it.
        # But we avoid starting duplicate tasks if already present.
        if self.sandbox_task and not self.sandbox_task.done():
            return

        # create task in this loop (only valid if loop is running)
        try:
            # If loop is running (rare for CLI callers), create_task directly
            if loop.is_running():
                self.sandbox_task = loop.create_task(oc.start())
            else:
                # run the start coroutine until it yields control (start background agent)
                # we run it briefly to allow repo to initialize
                self.sandbox_task = loop.create_task(oc.start())
                # allow the loop to process one iteration so the task can start
                loop.run_until_complete(asyncio.sleep(0))
        except Exception as e:
            log.error(f"Failed to start OpenComputerUse sandbox: {e}")

    def execute(self, step_payload: dict):
        """
        Persistent passthrough execution (interactive session):
        Keeps OpenComputerUse running so the user can enter multiple USER commands.
        """
        import os
        import pty
        import select
        import subprocess
        import sys
        import time

        prompt = step_payload.get("text") or step_payload.get("event") or None
        main_path = os.path.join(self.base_path, "main.py")

        if not os.path.exists(main_path):
            raise FileNotFoundError(f"OpenComputerUse main.py not found at {main_path}")

        env = os.environ.copy()
        cwd = self.base_path

        log.info("[OpenComputerUseAdapter] 🔁 Starting persistent OpenComputerUse interactive session...")
        if prompt:
            log.info(f"🧠 Initial prompt: {prompt}")

        try:
            # Create pseudo-terminal for full interaction
            master_fd, slave_fd = pty.openpty()
            proc = subprocess.Popen(
                [sys.executable, main_path],
                cwd=cwd,
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                text=True,
                bufsize=1,
                close_fds=True,
            )
            os.close(slave_fd)

            buffer = ""
            initial_sent = False

            while True:
                # Read process output
                rlist, _, _ = select.select([master_fd, sys.stdin], [], [], 0.1)

                # Handle agent output
                if master_fd in rlist:
                    out = os.read(master_fd, 1024).decode(errors="ignore")
                    if not out:
                        break
                    sys.stdout.write(out)
                    sys.stdout.flush()
                    buffer += out

                    # Automatically send first prompt if provided
                    if not initial_sent and prompt and "USER:" in buffer:
                        time.sleep(0.3)
                        os.write(master_fd, (prompt + "\n").encode())
                        initial_sent = True

                # Handle user typing directly in terminal (live interactive mode)
                if sys.stdin in rlist:
                    user_input = sys.stdin.readline().strip()
                    if user_input.lower() in {"exit", "quit"}:
                        log.info("[OpenComputerUseAdapter] 👋 Exiting interactive session...")
                        proc.terminate()
                        break
                    os.write(master_fd, (user_input + "\n").encode())

                # Exit if process ends
                if proc.poll() is not None:
                    break

            os.close(master_fd)
            proc.wait()
            log.info("[OpenComputerUseAdapter] ✅ Session closed cleanly.")
            return {
                "status": "success",
                "detail": "Interactive OpenComputerUse session ended.",
                "mode": "persistent",
            }

        except KeyboardInterrupt:
            log.warning("🛑 User interrupted interactive session.")
            try:
                proc.terminate()
            except Exception:
                pass
            return {"status": "aborted", "detail": "Session terminated manually."}

        except Exception as e:
            log.error(f"❌ Persistent session error: {e}")
            try:
                os.close(master_fd)
            except Exception:
                pass
            return {"status": "failed", "detail": str(e)}


    def validate(self, step):
        # If OpenComputerUse can validate, call into it; else return a generic pass.
        try:
            oc = self._load_oc_module()
            if hasattr(oc, "validate"):
                return oc.validate(step)
        except Exception:
            pass
        return {"validation_status": "unknown", "reason": "validation not implemented in adapter"}
    
    def stop(self):
        """Stop OpenComputerUse sandbox/agent if we started one."""
        try:
            if self.sandbox_task:
                self.sandbox_task.cancel()
                self.sandbox_task = None
            if self.loop and not self.loop.is_closed():
                # attempt to stop and close our loop if it's not running other tasks
                if not self.loop.is_running():
                    self.loop.stop()
                    self.loop.close()
                self.loop = None
            log.info("🛑 Stopped OpenComputerUse sandbox.")
        except Exception as e:
            log.error(f"Error stopping OpenComputerUse sandbox: {e}")
