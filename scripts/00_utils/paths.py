"""
Shared path resolution -- everything computed relative to this file's own
location instead of hardcoded absolute paths, so the codebase runs the same
whether it's on this dev machine or a deployed container. Same pattern
already used correctly for MODEL_PATH in compare_swing.py, extended here
into one shared module other files import from instead of each redefining
their own relative walk-up.
"""
import os

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT   = os.path.dirname(SCRIPTS_DIR)
DATA_DIR    = os.path.join(REPO_ROOT, 'data')
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
