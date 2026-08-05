const path = require('path');

// Computed relative to this file's own location, same idea as
// scripts/00_utils/paths.py on the Python side -- one shared source of
// truth instead of every route file redefining its own relative walk-up.
const SCRIPTS_DIR = path.join(__dirname, '..', '..', '..', 'scripts');
const DATA_DIR = path.join(__dirname, '..', '..', '..', 'data');

// PYTHON_BIN env var is an escape hatch; otherwise pick the venv binary by
// platform so this works unchanged on Windows dev and a Linux container --
// venv layouts differ (Scripts/python.exe vs bin/python3).
const PYTHON = process.env.PYTHON_BIN || path.join(
  SCRIPTS_DIR, 'venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3'
);

module.exports = { SCRIPTS_DIR, DATA_DIR, PYTHON };
