from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, Response, g, jsonify, request, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)


class Task(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(400), nullable=False, default="")
    due = db.Column(db.String(10), nullable=False, default="")
    priority = db.Column(db.String(10), nullable=False, default="normal")
    space = db.Column(db.String(20), nullable=False, default="Personal")
    completed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.BigInteger, nullable=False)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SESSION_SECRET") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'fieldnote.sqlite3').as_posix()}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    @app.before_request
    def protect_browser_requests() -> Response | None:
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return api_error("Request origin is not allowed.", 403)

            auth_route = request.path in {"/api/auth/login", "/api/auth/register"}
            if session.get("user_id") and not auth_route:
                if request.headers.get("X-CSRF-Token") != session.get("csrf_token"):
                    return api_error("A valid CSRF token is required.", 403)

        user_id = session.get("user_id")
        g.current_user = db.session.get(User, user_id) if user_id else None
        if user_id and g.current_user is None:
            session.clear()
        return None

    def login_required(route: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(route)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if g.current_user is None:
                return api_error("Sign in to access this resource.", 401)
            return route(*args, **kwargs)

        return wrapped

    def issue_session(user: User) -> dict[str, Any]:
        session.clear()
        session.permanent = True
        session["user_id"] = user.id
        session["csrf_token"] = secrets.token_urlsafe(32)
        return {"user": serialize_user(user), "csrfToken": session["csrf_token"]}

    @app.get("/")
    def index() -> Response:
        return send_file(BASE_DIR / "index.html")

    @app.get("/styles.css")
    def styles() -> Response:
        return send_file(BASE_DIR / "styles.css", mimetype="text/css")

    @app.get("/app.js")
    def script() -> Response:
        return send_file(BASE_DIR / "app.js", mimetype="text/javascript")

    @app.get("/api/auth/session")
    def auth_session() -> Response:
        if g.current_user is None:
            return jsonify(user=None, csrfToken=None)
        return jsonify(user=serialize_user(g.current_user), csrfToken=session["csrf_token"])

    @app.post("/api/auth/register")
    def register() -> tuple[Response, int] | Response:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return api_error("A JSON request body is required.", 400)

        name = str(body.get("name", "")).strip()
        email = str(body.get("email", "")).strip().lower()
        password = body.get("password")
        if not name or len(name) > 80:
            return api_error("Enter a name of 1 to 80 characters.", 400)
        if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return api_error("Enter a valid email address.", 400)
        if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
            return api_error("Password must be between 8 and 128 characters.", 400)
        if db.session.scalar(db.select(User.id).where(User.email == email)) is not None:
            return api_error("An account with that email already exists.", 409)

        user = User(name=name, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        return jsonify(issue_session(user)), 201

    @app.post("/api/auth/login")
    def login() -> tuple[Response, int] | Response:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return api_error("A JSON request body is required.", 400)
        email = str(body.get("email", "")).strip().lower()
        password = body.get("password")
        user = db.session.scalar(db.select(User).where(User.email == email))
        if user is None or not isinstance(password, str) or not check_password_hash(user.password_hash, password):
            return api_error("Email or password is incorrect.", 401)
        return jsonify(issue_session(user))

    @app.post("/api/auth/logout")
    @login_required
    def logout() -> Response:
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/tasks")
    @login_required
    def list_tasks() -> Response:
        tasks = db.session.scalars(
            db.select(Task).where(Task.user_id == g.current_user.id).order_by(Task.created_at.desc())
        ).all()
        return jsonify([serialize_task(task) for task in tasks])

    @app.post("/api/tasks")
    @login_required
    def create_task() -> tuple[Response, int] | Response:
        body = request.get_json(silent=True)
        validated, error = validate_task(body)
        if error:
            return api_error(error, 400)
        task = Task(id=str(uuid.uuid4()), user_id=g.current_user.id, created_at=int(datetime.now(timezone.utc).timestamp() * 1000), **validated)
        db.session.add(task)
        db.session.commit()
        return jsonify(serialize_task(task)), 201

    @app.patch("/api/tasks/<task_id>")
    @login_required
    def update_task(task_id: str) -> tuple[Response, int] | Response:
        task = db.session.scalar(
            db.select(Task).where(Task.id == task_id, Task.user_id == g.current_user.id)
        )
        if task is None:
            return api_error("Task not found.", 404)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return api_error("A JSON request body is required.", 400)
        values = serialize_task(task)
        values.update(body)
        validated, error = validate_task(values)
        if error:
            return api_error(error, 400)
        for field, value in validated.items():
            setattr(task, field, value)
        db.session.commit()
        return jsonify(serialize_task(task))

    @app.delete("/api/tasks/<task_id>")
    @login_required
    def delete_task(task_id: str) -> tuple[str, int] | tuple[Response, int]:
        task = db.session.scalar(
            db.select(Task).where(Task.id == task_id, Task.user_id == g.current_user.id)
        )
        if task is None:
            return api_error("Task not found.", 404)
        db.session.delete(task)
        db.session.commit()
        return "", 204

    return app


def api_error(message: str, status: int) -> tuple[Response, int]:
    return jsonify(error=message), status


def serialize_user(user: User) -> dict[str, Any]:
    return {"id": user.id, "name": user.name, "email": user.email}


def serialize_task(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "due": task.due,
        "priority": task.priority,
        "space": task.space,
        "completed": task.completed,
        "createdAt": task.created_at,
    }


def validate_task(body: Any) -> tuple[dict[str, Any], str | None]:
    if not isinstance(body, dict):
        return {}, "A JSON request body is required."
    title = str(body.get("title", "")).strip()
    description = str(body.get("description", "")).strip()
    due = body.get("due") or ""
    priority = body.get("priority", "normal")
    space = body.get("space", "Personal")
    completed = body.get("completed", False)
    if not title or len(title) > 100:
        return {}, "Task name must be between 1 and 100 characters."
    if len(description) > 400:
        return {}, "Task details must be 400 characters or fewer."
    if not isinstance(due, str) or (due and not valid_date(due)):
        return {}, "Enter a valid due date."
    if priority not in {"normal", "high", "low"}:
        return {}, "Choose a valid priority."
    if space not in {"Personal", "Work"}:
        return {}, "Choose a valid space."
    if not isinstance(completed, bool):
        return {}, "Task completion must be true or false."
    return {
        "title": title,
        "description": description,
        "due": due,
        "priority": priority,
        "space": space,
        "completed": completed,
    }, None


def valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return len(value) == 10
    except ValueError:
        return False


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))