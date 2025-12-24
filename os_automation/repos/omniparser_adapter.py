# os_automation/repos/omniparser_adapter.py
from os_automation.tools.omni_parser_tool import OmniParserTool

from os_automation.core.adapters import BaseAdapter

class OmniParserAdapter(BaseAdapter):
    def __init__(self):
        self.tool = OmniParserTool()

    def detect(self, step):
        image_path = step.get("image_path")
        if image_path is None:
            raise ValueError("image_path required")
        return self.tool.process_image(image_path)

    def execute(self, step):
        return {"status": "noop"}

    def validate(self, step):
        return {"validation": "ok"}
    