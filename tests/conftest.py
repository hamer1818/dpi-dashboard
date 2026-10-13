import os

# The UI test runs without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
