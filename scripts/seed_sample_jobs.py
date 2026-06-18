from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from models import seed_sample_jobs


app = create_app()
with app.app_context():
    seed_sample_jobs()
    print("Seeded sample jobs.")
