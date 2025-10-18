# main_scripts/os_parser.py
import argparse
import json
from os_automation.core.orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image_path", nargs='?', default=None)
    parser.add_argument("--prompt", default="Open terminal and run ls")
    parser.add_argument("--tool", default=None, help="Override executor tool (pyautogui|sikuli)")
    parser.add_argument("--detection", default=None, help="Override detection (omniparser|osatlas)")
    args = parser.parse_args()
    orch = Orchestrator(config_tool_override=args.tool, config_detection_override=args.detection)
    result = orch.run(user_prompt=args.prompt, image_path=args.image_path)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
