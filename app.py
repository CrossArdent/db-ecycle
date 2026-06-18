from pathlib import Path

from flask import Flask

from auth import current_user, generate_csrf_token
from config import Config, env_config, load_env_file
from models import close_db, init_db, seed_default_users, seed_sample_jobs
from routes import bp


def create_app(test_config=None):
    load_env_file()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config.update(env_config())

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(close_db)
    app.register_blueprint(bp)

    @app.context_processor
    def inject_globals():
        return {
            "current_user": current_user(),
            "csrf_token": generate_csrf_token,
        }

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("Initialized the SQLite database.")

    @app.cli.command("seed-users")
    def seed_users_command():
        seed_default_users()
        print("Seeded default local test users.")

    @app.cli.command("seed-sample-jobs")
    def seed_jobs_command():
        seed_sample_jobs()
        print("Seeded sample jobs.")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
