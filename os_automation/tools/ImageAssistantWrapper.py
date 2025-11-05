# os_automation/tools/ImageAssistantWrapper.py

from pathlib import Path

from os_automation.tools.omni_parser_tool import OmniParserTool


class ImageAssistantWrapper:
    def __init__(self):
        self.tool = OmniParserTool()

    def analyze(self, image_path):
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        return self.tool.process_image(image_path)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python ImageAssistantWrapper.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    assistant = ImageAssistantWrapper()
    results = assistant.analyze(image_path)
    
    print("Extracted content from image using OmniParser:")
    for key, value in results.items():
        print(f"{key}: {value}")