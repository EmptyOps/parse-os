# os_automation/repos/omniparser_adapter.py
from os_automation.core.adapters import BaseAdapter
from main_scripts.omniparser_tool_wrapper import ToolWrapper

class OmniParserAdapter(BaseAdapter):
    def __init__(self):
        self.tool = ToolWrapper()

    def detect(self, step):
        image_path = step.get("image_path")
        if image_path is None:
            raise ValueError("image_path required")
        return self.tool.process_image(image_path)

    def execute(self, step):
        return {"status": "noop"}

    def validate(self, step):
        return {"validation": "ok"}
