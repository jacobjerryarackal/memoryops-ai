import sys
import dotenv
from pathlib import Path

# Load environment variables globally before any tests or module imports
dotenv.load_dotenv()

# Add services/api to sys.path so app module can be found
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent))

