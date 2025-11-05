# os_automation/repos/osatlas_adapter.py
# For now OS-Atlas will behave the same as OmniParser (alias). You can replace internals later.
from os_automation.repos.omniparser_adapter import OmniParserAdapter


class OSAtlasAdapter(OmniParserAdapter):
    # Inherit all behavior for now; override detect() when you replace with API logic.
    pass
