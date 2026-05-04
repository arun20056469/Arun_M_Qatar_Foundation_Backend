import re
from datetime import date
from typing import Dict, Optional, Tuple

from flask import Blueprint, current_app, jsonify, render_template, request, session, url_for, redirect
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


#
@main_bp.get("/")
def home():
    return render_template("index.html", requested_view=request.args.get("view", "login"))


@main_bp.get("/login")
def login_page():
    return redirect(url_for("main.home", view="login"))



@main_bp.get("/dashboard")
def dashboard_page():
    return redirect(url_for("main.home", view="dashboard"))


# ================= AUTH ================= #

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

    if Admin.query.filter_by(email=email).first():
        return _error("Email already registered.", 409)

    admin = Admin(full_name=full_name, email=email)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    return _success("Account created successfully.", 201)


@main_bp.post("/api/login")
def login():
    data = _json_data()

    email = _normalize_email(str(data.get("email", "")))
    password = str(data.get("password", ""))

    admin = Admin.query.filter_by(email=email).first()
    if not admin or not admin.check_password(password):
        return _error("Invalid email or password", 401)

    login_user(admin)
    return _success("Login successful.", user=admin.to_public_dict())


@main_bp.post("/api/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return _success("Logged out successfully.")




@main_bp.get("/api/opportunities")
@login_required
def list_opportunities():
    ops = Opportunity.query.filter_by(admin_id=current_user.id).all()
    return _success("Loaded", data=[o.to_dict() for o in ops])


@main_bp.post("/api/opportunities")
@login_required
def create_opportunity():
    cleaned, errors = _validate_opportunity_payload(_json_data())
    if errors:
        return _error("Validation failed", 400, errors=errors)

    op = Opportunity(admin_id=current_user.id, **cleaned)
    db.session.add(op)
    db.session.commit()

    return _success("Created", data=op.to_dict())


@main_bp.delete("/api/opportunities/<int:id>")
@login_required
def delete_opportunity(id):
    op = _get_owned_opportunity(id)
    if not op:
        return _error("Not found", 404)

    db.session.delete(op)
    db.session.commit()
    return _success("Deleted")