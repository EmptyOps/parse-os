from main_scripts.omniparser_tool_wrapper import ToolWrapper
from pathlib import Path

class ImageAssistant:
    def __init__(self):
        self.tool = ToolWrapper()

    def analyze(self, image_path):
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        return self.tool.process_image(image_path)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python image_assistant.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    assistant = ImageAssistant()
    results = assistant.analyze(image_path)
    
    print("Extracted content from image using OmniParser:")
    for key, value in results.items():
        print(f"{key}: {value}")