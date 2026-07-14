import sys
from pathlib import Path

# Add services/api to sys.path so app module can be found
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
