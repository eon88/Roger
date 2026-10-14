"""Import hq_owner.py from the application directory in repo tests."""
import importlib.util
import pathlib
path = pathlib.Path(__file__).resolve().parent.parent / "stage-clone" / "hq_owner.py"
spec = importlib.util.spec_from_file_location("hq_owner", path)
hq_owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hq_owner)
