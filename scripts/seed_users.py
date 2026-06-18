from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from models import DEFAULT_USERS, seed_default_users


# Default credentials are intentionally grouped here for easy local changes.
# Edit this list or call models.create_user from a Python shell to recreate users.
DEFAULT_TEST_USERS = DEFAULT_USERS


app = create_app()
with app.app_context():
    seed_default_users()
    print("Seeded users:")
    for username, password, role in DEFAULT_TEST_USERS:
        print(f"- {username} / {password} ({role})")
