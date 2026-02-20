# Contribution Areas & Ongoing Work

---

## 🚧 On-going Development

### **Core Automation Capability**
- Architecture refinement
- Execution flow improvements

### **ParseOS MCP – Kilo Code**
- Test automation within browser
- Test automation beyond browser
- Current focus: Web development

---

## 🧪 Contribution Required

### Testing in Different Environments
- 15 test cases will be shared soon
- Help is needed to test across multiple environments

---

# 🎥 End-to-End Test Execution – Parse-OS

This Section explains how to manually execute real OS-level automation flows in Parse-OS.

⚠️ These are NOT unit tests.
They are real OS-level execution validations.

---

## 🧪 Using `agents_testing.py`

This method allows you to manually trigger real OS-level automation flows.

### 📂 File Location

```
os_automation/tests/agents_testing.py
```


### ▶️ How to Run

From project root:

```
PYTHONPATH=parse-os python3 -m parse-os.tests.agents_testing
```

### 🔍 Available Test Coverage Includes


- 📁 File system operations
- 🌐 Browser automation
- 📝 Text editor actions
- ⚙️ System settings
- 💻 VS Code automation
- 🌍 FTP advanced workflow

### 👉 This script allows contributors to:

- Provide a natural language instruction
- Capture current screen state
- Pass screenshot to Orchestrator
- Execute automation workflow

---

## 🎥 Using Demo Video

You can also follow the step-by-step demo here:

>  **[Test Execution Demo – Parse-OS](https://youtu.be/aEsTHG5_Vf8)**

### If you are testing by following the video:

- Duplicate the provided [Test Case Reporting Sheet](https://docs.google.com/spreadsheets/d/1GXh1E_0dnz-w2zWnyath26RlVSZmbo4dymnuDVxKgcU/edit?usp=sharing).
- Execute the test cases shown in the video.
- Continuously update your duplicated sheet with execution results.
- When creating a Pull Request, include the link to your duplicated test case sheet in the PR description.

This ensures proper validation and execution traceability.


---