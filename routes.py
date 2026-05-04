import re
from datetime import date
from typing import Dict, Optional, Tuple

from flask import Blueprint, current_app, jsonify, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from models import Admin, Opportunity, db


main_bp = Blueprint("main", __name__)

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_CATEGORIES = {
    "technology",
    "business",
    "design",
    "marketing",
    "data",
    "other",
}


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _json_data() -> Dict[str, object]:
    return request.get_json(silent=True) or request.form.to_dict()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _success(message: str, status_code: int = 200, **payload):
    response = {"status": "success", "message": message}
    response.update(payload)
    return jsonify(response), status_code


def _error(message: str, status_code: int = 400, **payload):
    response = {"status": "error", "message": message}
    response.update(payload)
    return jsonify(response), status_code


def _validate_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email))


def _load_reset_email(token: str) -> str:
    return _serializer().loads(
        token,
        salt=current_app.config["RESET_PASSWORD_SALT"],
        max_age=3600,
    )


def _validate_opportunity_payload(data: Dict[str, object]) -> Tuple[Dict[str, object], Dict[str, str]]:
    errors = {}

    name = str(data.get("name", "")).strip()
    duration = str(data.get("duration", "")).strip()
    start_date_raw = str(data.get("start_date", "")).strip()
    description = str(data.get("description", "")).strip()
    future_opportunities = str(data.get("future_opportunities", "")).strip()

    raw_skills = data.get("skills", "")
    if isinstance(raw_skills, list):
        skills_list = [str(skill).strip() for skill in raw_skills if str(skill).strip()]
    else:
        skills_list = [skill.strip() for skill in str(raw_skills).split(",") if skill.strip()]

    category = str(data.get("category", "")).strip().lower()
    max_applicants_raw = str(data.get("max_applicants", "")).strip()

    if not name:
        errors["name"] = "Opportunity name is required."
    if not duration:
        errors["duration"] = "Duration is required."
    if not start_date_raw:
        errors["start_date"] = "Start date is required."
    if not description:
        errors["description"] = "Description is required."
    if not skills_list:
        errors["skills"] = "At least one skill is required."
    if category not in ALLOWED_CATEGORIES:
        errors["category"] = "Category must match the allowed list."
    if not future_opportunities:
        errors["future_opportunities"] = "Future opportunities are required."

    start_date_value = None
    if start_date_raw:
        try:
            start_date_value = date.fromisoformat(start_date_raw)
        except ValueError:
            errors["start_date"] = "Start date must be a valid date."

    max_applicants_value = None
    if max_applicants_raw:
        try:
            max_applicants_value = int(max_applicants_raw)
            if max_applicants_value < 1:
                raise ValueError
        except ValueError:
            errors["max_applicants"] = "Maximum applicants must be a positive whole number."

    cleaned = {
        "name": name,
        "duration": duration,
        "start_date": start_date_value,
        "description": description,
        "skills": ", ".join(skills_list),
        "category": category,
        "future_opportunities": future_opportunities,
        "max_applicants": max_applicants_value,
    }
    return cleaned, errors


def _get_owned_opportunity(opportunity_id: int) -> Optional[Opportunity]:
    return Opportunity.query.filter_by(id=opportunity_id, admin_id=current_user.id).first()


@main_bp.get("/")
def home():
    return render_template("index.html", requested_view=request.args.get("view", "login"))


@main_bp.get("/login")
def login_page():
    return render_template("login.html")


@main_bp.get("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@main_bp.post("/api/signup")
def signup():
    data = _json_data()

    full_name = str(data.get("full_name", "")).strip()
    email = _normalize_email(str(data.get("email", "")))
    password = str(data.get("password", ""))
    confirm_password = str(data.get("confirm_password", ""))

    errors = {}
    if not full_name:
        errors["full_name"] = "Full name is required."
    if not email or not _validate_email(email):
        errors["email"] = "Please enter a valid email address."
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters long."
    if password != confirm_password:
        errors["confirm_password"] = "Passwords must match."
    if errors:
        return _error("Please fix the highlighted fields.", 400, errors=errors)

    existing_admin = Admin.query.filter_by(email=email).first()
    if existing_admin:
        return _error(
            "An account with this email already exists.",
            409,
            errors={"email": "Email is already registered."},
        )

    admin = Admin(full_name=full_name, email=email)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    return _success("Account created successfully. Please log in.", 201)


@main_bp.post("/api/login")
def login():
    data = _json_data()

    email = _normalize_email(str(data.get("email", "")))
    password = str(data.get("password", ""))
    remember_me = bool(data.get("remember_me"))

    if not email or not password:
        return _error("Invalid email or password", 401)

    admin = Admin.query.filter_by(email=email).first()
    if not admin or not admin.check_password(password):
        return _error("Invalid email or password", 401)

    login_user(admin, remember=remember_me)
    session.permanent = remember_me

    return _success("Login successful.", user=admin.to_public_dict())


@main_bp.post("/api/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return _success("Signed out successfully.")


@main_bp.post("/api/forgot-password")
def forgot_password():
    data = _json_data()
    email = _normalize_email(str(data.get("email", "")))

    if not email or not _validate_email(email):
        return _error("Please enter a valid email address.", 400)

    admin = Admin.query.filter_by(email=email).first()
    if admin:
        token = _serializer().dumps(
            admin.email,
            salt=current_app.config["RESET_PASSWORD_SALT"],
        )
        reset_link = url_for("main.reset_password", token=token, _external=True)
        current_app.logger.warning("Password reset link for %s: %s", admin.email, reset_link)

    return _success(
        "If an account exists for this email, a password reset link has been generated."
    )


@main_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    try:
        email = _load_reset_email(token)
    except SignatureExpired:
        return render_template(
            "reset_password.html",
            token=token,
            valid=False,
            success=False,
            message="This reset link expired after 1 hour. Please request a new one.",
        )
    except BadSignature:
        return render_template(
            "reset_password.html",
            token=token,
            valid=False,
            success=False,
            message="This password reset link is invalid.",
        )

    if request.method == "POST":
        password = str(request.form.get("password", ""))
        confirm_password = str(request.form.get("confirm_password", ""))

        if len(password) < 8:
            return render_template(
                "reset_password.html",
                token=token,
                valid=True,
                success=False,
                message="Password must be at least 8 characters long.",
            )
        if password != confirm_password:
            return render_template(
                "reset_password.html",
                token=token,
                valid=True,
                success=False,
                message="Passwords do not match.",
            )

        admin = Admin.query.filter_by(email=email).first()
        if admin:
            admin.set_password(password)
            db.session.commit()

        return render_template(
            "reset_password.html",
            token=token,
            valid=True,
            success=True,
            message="Password updated successfully. You can return to the login page.",
        )

    return render_template(
        "reset_password.html",
        token=token,
        valid=True,
        success=False,
        message=f"Resetting password for {email}",
    )


@main_bp.get("/api/session")
def session_status():
    if current_user.is_authenticated:
        return _success("Session active.", authenticated=True, user=current_user.to_public_dict())
    return _success("No active session.", authenticated=False, user=None)


@main_bp.get("/api/opportunities")
@login_required
def list_opportunities():
    opportunities = (
        Opportunity.query.filter_by(admin_id=current_user.id)
        .order_by(Opportunity.created_at.desc())
        .all()
    )
    return _success(
        "Opportunities loaded successfully.",
        data=[opportunity.to_dict() for opportunity in opportunities],
    )


@main_bp.post("/api/opportunities")
@login_required
def create_opportunity():
    cleaned, errors = _validate_opportunity_payload(_json_data())
    if errors:
        return _error("Please fix the opportunity details.", 400, errors=errors)

    opportunity = Opportunity(admin_id=current_user.id, **cleaned)
    db.session.add(opportunity)
    db.session.commit()

    return _success(
        "Opportunity created successfully.",
        201,
        data=opportunity.to_dict(),
    )


@main_bp.get("/api/opportunities/<int:opportunity_id>")
@login_required
def get_opportunity(opportunity_id: int):
    opportunity = _get_owned_opportunity(opportunity_id)
    if not opportunity:
        return _error("Opportunity not found.", 404)
    return _success("Opportunity loaded successfully.", data=opportunity.to_dict())


@main_bp.route("/api/opportunities/<int:opportunity_id>", methods=["PUT", "POST"])
@login_required
def update_opportunity(opportunity_id: int):
    opportunity = _get_owned_opportunity(opportunity_id)
    if not opportunity:
        return _error("Opportunity not found.", 404)

    cleaned, errors = _validate_opportunity_payload(_json_data())
    if errors:
        return _error("Please fix the opportunity details.", 400, errors=errors)

    for field, value in cleaned.items():
        setattr(opportunity, field, value)

    db.session.commit()
    return _success("Opportunity updated successfully.", data=opportunity.to_dict())


@main_bp.delete("/api/opportunities/<int:opportunity_id>")
@login_required
def delete_opportunity(opportunity_id: int):
    opportunity = _get_owned_opportunity(opportunity_id)
    if not opportunity:
        return _error("Opportunity not found.", 404)

    db.session.delete(opportunity)
    db.session.commit()
    return _success("Opportunity deleted successfully.")
