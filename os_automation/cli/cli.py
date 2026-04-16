# os_automation/cli/cli.py
import click
import json
from os_automation.core.orchestrator import Orchestrator

@click.group()
def cli():
    pass

@cli.command()
@click.argument("prompt")
@click.option("--image", default=None, help="Path to image for detection")
@click.option("--tool", default=None, help="Override executor tool (pyautogui|sikuli)")
@click.option("--detection", default=None, help="Override detection (omniparser|osatlas)")
def run(prompt, image, tool, detection):
    orch = Orchestrator(config_tool_override=tool, config_detection_override=detection)
    result = orch.run(prompt, image_path=image)
    click.echo(json.dumps(result, indent=2))

if __name__ == "__main__":
    cli()

