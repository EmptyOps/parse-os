import logging
import sys

# Create a standard logger
log = logging.getLogger("os_automation")
log.setLevel(logging.DEBUG)

# Console handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)

# Formatter
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
ch.setFormatter(formatter)

# Add handler to logger
log.addHandler(ch)
