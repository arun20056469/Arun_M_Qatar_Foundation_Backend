from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager

from config import Config
from models import Admin, db
from routes import main_bp


login_manager = LoginManager()


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(main_bp)

    @login_manager.user_loader
    def load_user(user_id: str):
        if not user_id.isdigit():
            return None
        return db.session.get(Admin, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        return redirect(url_for("main.home", view="login"))

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])
