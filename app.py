from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager

from config import Config
from models import Admin, db
from routes import main_bp

import os

login_manager = LoginManager()


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Register blueprint
    app.register_blueprint(main_bp)

    # Load user for Flask-Login
    @login_manager.user_loader
    def load_user(user_id: str):
        if not user_id.isdigit():
            return None
        return db.session.get(Admin, int(user_id))

    # Handle unauthorized access
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({
                "status": "error",
                "message": "Authentication required"
            }), 401
        return redirect(url_for("main.home", view="login"))

    # Create DB tables
    with app.app_context():
        db.create_all()

    return app


# Create app instance
app = create_app()


# ✅ IMPORTANT: Deployment-ready run block
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Render provides PORT
    app.run(host="0.0.0.0", port=port, debug=True)