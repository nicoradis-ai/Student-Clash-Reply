"""Entry point requested for the Streamlit application.

The project also has an ``app/`` package containing the backend modules. This
small launcher registers that package explicitly before starting the UI, so
both ``streamlit run app.py`` and the existing module imports work together.
"""
import importlib.util
import runpy
import sys
from pathlib import Path


root = Path(__file__).resolve().parent
package_dir = root / "app"
package_init = package_dir / "__init__.py"
spec = importlib.util.spec_from_file_location(
    "app",
    package_init,
    submodule_search_locations=[str(package_dir)],
)
package = importlib.util.module_from_spec(spec)
sys.modules["app"] = package
assert spec.loader is not None
spec.loader.exec_module(package)
runpy.run_path(str(root / "streamlit_app.py"), run_name="__main__")
