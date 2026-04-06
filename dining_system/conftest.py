import os
import sys


# Ensure imports like `from app import app` resolve to dining_system/app.py.
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
