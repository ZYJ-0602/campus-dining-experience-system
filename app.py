import os
import sys
import importlib.util


PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
DINING_SYSTEM_DIR = os.path.join(PROJECT_ROOT, 'dining_system')
if DINING_SYSTEM_DIR not in sys.path:
    sys.path.insert(0, DINING_SYSTEM_DIR)

spec = importlib.util.spec_from_file_location('dining_system_main', os.path.join(DINING_SYSTEM_DIR, 'app.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app


if __name__ == '__main__':
    app.run(debug=True, port=5000)
