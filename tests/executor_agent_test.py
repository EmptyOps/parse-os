from os_automation.agents.executor_agent import ExecutorAgent

agent = ExecutorAgent()
out = agent.detect_and_execute(image_path="tests/sample.png")
print(out)


# ouyput :
#     ✅ Should print detection + execution dict:

# {
#   "detection": {"text_0": {...}, "icon_0": {...}},
#   "chosen_bbox": [x, y, w, h],
#   "execution": {"status": "success"}
# }
