from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from models import init_db


app = create_app()
with app.app_context():
    init_db()
    print("Database migration complete. Missing columns were added without deleting data.")
