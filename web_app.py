"""
Production Status Tracking System — Flask website.

Reads and writes the existing MySQL database `production_db`.
Does not drop, truncate, or recreate any tables.
Database credentials come from environment variables (see .env.example).
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import secrets
from datetime import date, datetime
from functools import wraps

import mysql.connector
from flask import (
    Flask,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

STATUSES = ("Not Started", "In Progress", "On Hold", "Completed", "Cancelled")
INSPECTION_RESULTS = ("Pending", "Passed", "Failed", "Rework Required")


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["DB"] = {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "database": os.environ.get("MYSQL_DATABASE", "production_db"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
    }

    @app.before_request
    def before_request():
        g.db_error = None
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)

    @app.teardown_appcontext
    def teardown_db(_exc):
        conn = g.pop("db", None)
        if conn is not None and conn.is_connected():
            conn.close()

    def get_db():
        if "db" not in g:
            try:
                g.db = mysql.connector.connect(**app.config["DB"])
            except Error as exc:
                g.db = None
                g.db_error = str(exc)
        return g.db

    def query_rows(sql, params=None):
        conn = get_db()
        if conn is None:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params or ())
            return cursor.fetchall()
        finally:
            cursor.close()

    def query_one(sql, params=None):
        rows = query_rows(sql, params)
        return rows[0] if rows else None

    def execute(sql, params=None, commit=True):
        conn = get_db()
        if conn is None:
            raise Error(g.db_error or "Not connected to MySQL")
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or ())
            if commit:
                conn.commit()
            return cursor.lastrowid
        except Error:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def call_proc(name, args):
        conn = get_db()
        if conn is None:
            raise Error(g.db_error or "Not connected to MySQL")
        cursor = conn.cursor()
        try:
            cursor.callproc(name, args)
            conn.commit()
        except Error:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    def user_role():
        username = session.get("user")
        if not username or get_db() is None:
            return None
        ensure_login_table()
        row = query_one("SELECT role FROM app_users WHERE username=%s", (username,))
        return row["role"] if row else None

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user"):
                return redirect(url_for("login", next=request.path))
            if user_role() != "Administrator":
                flash("Only an administrator can do that.", "error")
                return redirect(url_for("projects"))
            return view(*args, **kwargs)

        return wrapped

    def check_csrf():
        token = request.form.get("csrf_token", "")
        if not secrets.compare_digest(token, session.get("csrf_token", "")):
            flash("The form could not be verified. Please try again.", "error")
            return False
        return True

    def hash_password(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
        ).hex()
        return salt, digest

    def ensure_login_table():
        """Create app_users only if missing, and add role if missing. Never drops rows."""
        if getattr(g, "schema_ready", False):
            return
        database = app.config["DB"]["database"]
        exists = query_one(
            """
            SELECT COUNT(*) AS n
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'app_users'
            """,
            (database,),
        )
        if exists and exists["n"] == 0:
            execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    user_id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(60) NOT NULL UNIQUE,
                    password_salt VARCHAR(64) NOT NULL,
                    password_hash VARCHAR(128) NOT NULL,
                    role ENUM('Administrator','Employee') NOT NULL DEFAULT 'Employee',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        role_col = query_one(
            """
            SELECT COUNT(*) AS n
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'app_users' AND column_name = 'role'
            """,
            (database,),
        )
        if role_col and role_col["n"] == 0:
            execute(
                """
                ALTER TABLE app_users
                ADD COLUMN role ENUM('Administrator','Employee') NOT NULL DEFAULT 'Employee'
                """
            )
            execute("UPDATE app_users SET role='Administrator' WHERE username=%s", ("admin",))
        g.schema_ready = True

    def parse_date(value):
        value = (value or "").strip()
        if not value:
            return None
        return date.fromisoformat(value)

    def parse_int(value, allow_empty=True):
        value = (value or "").strip()
        if value == "":
            return None if allow_empty else 0
        return int(value)

    def project_choices():
        return query_rows(
            """
            SELECT project_id, project_no, project_name
            FROM projects
            ORDER BY project_no
            """
        )

    def employee_choices(active_only=True):
        sql = "SELECT employee_id, employee_name, department, job_title, is_active FROM employees"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY employee_name"
        return query_rows(sql)

    def customer_choices():
        return query_rows(
            "SELECT customer_id, customer_name FROM customers ORDER BY customer_name"
        )

    @app.context_processor
    def inject_globals():
        connected = False
        db_name = app.config["DB"]["database"]
        error = g.get("db_error")
        role = None
        if session.get("user"):
            conn = get_db()
            connected = conn is not None and conn.is_connected()
            role = user_role()
        return {
            "csrf_token": session.get("csrf_token", ""),
            "current_user": session.get("user"),
            "is_admin": role == "Administrator",
            "current_role": role,
            "db_connected": connected,
            "db_name": db_name,
            "db_error": error,
            "today": date.today().isoformat(),
            "statuses": STATUSES,
            "inspection_results": INSPECTION_RESULTS,
        }

    @app.route("/login", methods=["GET", "POST"])
    def login():
        conn = get_db()
        if conn is None:
            return render_template(
                "login.html",
                error=f"Could not connect to MySQL: {g.db_error}",
            )
        try:
            ensure_login_table()
        except Error as exc:
            return render_template("login.html", error=f"Could not prepare login table: {exc}")

        if request.method == "POST":
            if not check_csrf():
                return render_template("login.html")
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            if not username or not password:
                flash("Enter both username and password.", "error")
                return render_template("login.html")
            row = query_one(
                "SELECT username, role, password_salt, password_hash FROM app_users WHERE username=%s",
                (username,),
            )
            if not row:
                flash("Invalid username or password.", "error")
                return render_template("login.html")
            _, digest = hash_password(password, row["password_salt"])
            if secrets.compare_digest(digest, row["password_hash"]):
                session.clear()
                session["user"] = row["username"]
                session["role"] = row["role"]
                session["csrf_token"] = secrets.token_hex(16)
                session.permanent = True
                dest = request.args.get("next") or url_for("dashboard")
                if not dest.startswith("/"):
                    dest = url_for("dashboard")
                return redirect(dest)
            flash("Invalid username or password.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        if get_db() is None:
            flash(f"Database connection failed: {g.db_error}", "error")
            counts = {"projects": None, "in_progress": None, "on_hold": None}
            return render_template("dashboard.html", counts=counts, rows=[])

        counts = query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM projects) AS projects,
                (SELECT COUNT(*) FROM projects WHERE current_status='In Progress') AS in_progress,
                (SELECT COUNT(*) FROM projects WHERE current_status='On Hold') AS on_hold
            """
        ) or {}
        rows = query_rows(
            """
            SELECT project_id, project_no, project_name, customer_name, project_status
            FROM vw_project_status
            ORDER BY project_no
            """
        )
        return render_template("dashboard.html", counts=counts, rows=rows)

    def resolve_customer(raw_name):
        """Reuse a customer when the name matches, ignoring case and extra spaces."""
        customer_name = " ".join((raw_name or "").split())
        if not customer_name:
            return None, "Customer is required."
        if len(customer_name) > 100:
            return None, "Customer name must be 100 characters or less."
        if not any(character.isalnum() for character in customer_name):
            return None, "Enter a valid customer name."
        existing = query_one(
            "SELECT customer_id FROM customers WHERE customer_name = %s",
            (customer_name,),
        )
        if existing:
            return existing["customer_id"], None
        try:
            customer_id = execute(
                "INSERT INTO customers (customer_name) VALUES (%s)",
                (customer_name,),
            )
            return customer_id, None
        except Error:
            existing = query_one(
                "SELECT customer_id FROM customers WHERE customer_name = %s",
                (customer_name,),
            )
            if existing:
                return existing["customer_id"], None
            return None, "Could not save that customer. Check the name and try again."

    def project_form_values():
        project_no = (request.form.get("project_no") or "").strip()
        project_name = (request.form.get("project_name") or "").strip()
        description = (request.form.get("project_description") or "").strip() or None
        status = request.form.get("current_status") or "Not Started"
        try:
            start_date = parse_date(request.form.get("start_date"))
            planned_end = parse_date(request.form.get("planned_end_date"))
        except ValueError:
            return None, "Dates must use YYYY-MM-DD."
        if not project_no or not project_name:
            return None, "Project number and project name are required."
        if len(project_no) > 50 or len(project_name) > 120:
            return None, "Project number or name is too long."
        if description and len(description) > 4000:
            return None, "Description is too long."
        if status not in STATUSES:
            return None, "Invalid status."
        customer_id, error = resolve_customer(request.form.get("customer_name"))
        if error:
            return None, error
        return {
            "project_no": project_no,
            "project_name": project_name,
            "customer_id": customer_id,
            "start_date": start_date,
            "planned_end": planned_end,
            "status": status,
            "description": description,
        }, None

    def related_project_counts(project_id):
        return query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM production_updates WHERE project_id=%s) AS updates,
                (SELECT COUNT(*) FROM project_manpower WHERE project_id=%s) AS manpower,
                (SELECT COUNT(*) FROM quality_inspections WHERE project_id=%s) AS inspections,
                (SELECT COUNT(*) FROM status_history WHERE project_id=%s) AS history
            """,
            (project_id, project_id, project_id, project_id),
        ) or {}

    @app.route("/projects", methods=["GET", "POST"])
    @login_required
    def projects():
        if request.method == "POST":
            if user_role() != "Administrator":
                flash("Only an administrator can create projects.", "error")
                return redirect(url_for("projects"))
            if not check_csrf():
                return redirect(url_for("projects"))
            values, error = project_form_values()
            if error:
                flash(error, "error")
                return redirect(url_for("projects"))
            try:
                execute(
                    """
                    INSERT INTO projects
                        (project_no, project_name, customer_id, start_date, planned_end_date,
                         current_status, project_description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        values["project_no"],
                        values["project_name"],
                        values["customer_id"],
                        values["start_date"],
                        values["planned_end"],
                        values["status"],
                        values["description"],
                    ),
                )
                flash("Project saved to the database.", "success")
            except Error as exc:
                flash(f"Could not add project: {exc}", "error")
            return redirect(url_for("projects"))

        rows = query_rows(
            """
            SELECT p.project_id, p.project_no, p.project_name, c.customer_name,
                   p.current_status, p.start_date, p.planned_end_date
            FROM projects p
            JOIN customers c ON c.customer_id = p.customer_id
            ORDER BY p.project_no
            """
        )
        return render_template("projects.html", rows=rows, customers=customer_choices())

    @app.route("/projects/<int:project_id>")
    @login_required
    def project_detail(project_id):
        project = query_one(
            """
            SELECT p.*, c.customer_name, c.contact_person, c.phone AS customer_phone, c.email AS customer_email
            FROM projects p
            JOIN customers c ON c.customer_id = p.customer_id
            WHERE p.project_id = %s
            """,
            (project_id,),
        )
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("projects"))
        updates = query_rows(
            """
            SELECT pu.*, e.employee_name
            FROM production_updates pu
            LEFT JOIN employees e ON e.employee_id = pu.updated_by
            WHERE pu.project_id = %s
            ORDER BY pu.update_date DESC, pu.update_id DESC
            """,
            (project_id,),
        )
        manpower = query_rows(
            """
            SELECT pm.*, e.employee_name, e.department, e.job_title
            FROM project_manpower pm
            JOIN employees e ON e.employee_id = pm.employee_id
            WHERE pm.project_id = %s
            ORDER BY pm.assigned_date DESC, e.employee_name
            """,
            (project_id,),
        )
        inspections = query_rows(
            """
            SELECT qi.*, e.employee_name
            FROM quality_inspections qi
            LEFT JOIN employees e ON e.employee_id = qi.inspected_by
            WHERE qi.project_id = %s
            ORDER BY qi.inspection_date DESC, qi.inspection_id DESC
            """,
            (project_id,),
        )
        history = query_rows(
            """
            SELECT * FROM status_history
            WHERE project_id = %s
            ORDER BY changed_at DESC, history_id DESC
            """,
            (project_id,),
        )
        return render_template(
            "project_detail.html",
            project=project,
            updates=updates,
            manpower=manpower,
            inspections=inspections,
            history=history,
            customers=customer_choices(),
            related=related_project_counts(project_id),
        )

    @app.route("/projects/<int:project_id>/edit", methods=["POST"])
    @admin_required
    def project_edit(project_id):
        if not check_csrf():
            return redirect(url_for("project_detail", project_id=project_id))
        values, error = project_form_values()
        if error:
            flash(error, "error")
            return redirect(url_for("project_detail", project_id=project_id))
        existing = query_one("SELECT project_id FROM projects WHERE project_id=%s", (project_id,))
        if not existing:
            flash("Project not found.", "error")
            return redirect(url_for("projects"))
        try:
            execute(
                """
                UPDATE projects
                SET project_no=%s, project_name=%s, customer_id=%s, start_date=%s,
                    planned_end_date=%s, current_status=%s, project_description=%s
                WHERE project_id=%s
                """,
                (
                    values["project_no"],
                    values["project_name"],
                    values["customer_id"],
                    values["start_date"],
                    values["planned_end"],
                    values["status"],
                    values["description"],
                    project_id,
                ),
            )
            flash("Project updated in the database.", "success")
        except Error as exc:
            flash(f"Could not update project: {exc}", "error")
        return redirect(url_for("project_detail", project_id=project_id))

    @app.route("/projects/<int:project_id>/delete", methods=["POST"])
    @admin_required
    def project_delete(project_id):
        if not check_csrf():
            return redirect(url_for("project_detail", project_id=project_id))
        if request.form.get("confirm") != "yes":
            flash("Deletion was not confirmed.", "error")
            return redirect(url_for("project_detail", project_id=project_id))
        project = query_one(
            "SELECT project_id, project_no, current_status FROM projects WHERE project_id=%s",
            (project_id,),
        )
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("projects"))
        counts = related_project_counts(project_id)
        related = sum(int(counts.get(key) or 0) for key in ("updates", "manpower", "inspections", "history"))
        if related:
            if project["current_status"] != "Cancelled":
                try:
                    execute(
                        "UPDATE projects SET current_status=%s WHERE project_id=%s",
                        ("Cancelled", project_id),
                    )
                except Error as exc:
                    flash(f"Could not archive project: {exc}", "error")
                    return redirect(url_for("project_detail", project_id=project_id))
            flash(
                "Project "
                + project["project_no"]
                + " was archived as Cancelled. Related updates ("
                + str(counts.get("updates"))
                + "), manpower ("
                + str(counts.get("manpower"))
                + "), inspections ("
                + str(counts.get("inspections"))
                + "), and history ("
                + str(counts.get("history"))
                + ") were kept. The database would otherwise delete those rows automatically.",
                "success",
            )
            return redirect(url_for("project_detail", project_id=project_id))
        try:
            execute("DELETE FROM projects WHERE project_id=%s", (project_id,))
            flash("Project " + project["project_no"] + " was deleted. It had no related records.", "success")
        except Error as exc:
            flash(f"Could not delete project: {exc}", "error")
            return redirect(url_for("project_detail", project_id=project_id))
        return redirect(url_for("projects"))

    @app.route("/users", methods=["GET", "POST"])
    @admin_required
    def users():
        if request.method == "POST":
            if not check_csrf():
                return redirect(url_for("users"))
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            role = request.form.get("role") or "Employee"
            if not username.replace(".", "").replace("_", "").replace("-", "").isalnum() or not (3 <= len(username) <= 60):
                flash("Username must be 3–60 letters, numbers, dots, underscores, or hyphens.", "error")
                return redirect(url_for("users"))
            if len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
                return redirect(url_for("users"))
            if role not in ("Administrator", "Employee"):
                flash("Invalid role.", "error")
                return redirect(url_for("users"))
            salt, digest = hash_password(password)
            try:
                execute(
                    """
                    INSERT INTO app_users (username, password_salt, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (username, salt, digest, role),
                )
                flash("User saved. The password is stored as a hash.", "success")
            except Error as exc:
                flash(f"Could not create user: {exc}", "error")
            return redirect(url_for("users"))
        rows = query_rows(
            "SELECT user_id, username, role, created_at FROM app_users ORDER BY username"
        )
        return render_template("users.html", rows=rows)

    @app.route("/account", methods=["GET", "POST"])
    @login_required
    def account():
        if request.method == "POST":
            if not check_csrf():
                return redirect(url_for("account"))
            current = request.form.get("current_password") or ""
            new_password = request.form.get("new_password") or ""
            if len(new_password) < 8:
                flash("New password must be at least 8 characters.", "error")
                return redirect(url_for("account"))
            row = query_one(
                "SELECT password_salt, password_hash FROM app_users WHERE username=%s",
                (session.get("user"),),
            )
            if not row:
                flash("Account not found.", "error")
                return redirect(url_for("logout"))
            _, digest = hash_password(current, row["password_salt"])
            if not secrets.compare_digest(digest, row["password_hash"]):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("account"))
            salt, new_digest = hash_password(new_password)
            execute(
                "UPDATE app_users SET password_salt=%s, password_hash=%s WHERE username=%s",
                (salt, new_digest, session.get("user")),
            )
            flash("Password updated.", "success")
            return redirect(url_for("account"))
        return render_template("account.html")

    @app.route("/updates", methods=["GET", "POST"])
    @login_required
    def updates():
        if request.method == "POST":
            if not check_csrf():
                return redirect(url_for("updates"))
            try:
                project_id = int(request.form.get("project_id") or 0)
                update_date = parse_date(request.form.get("update_date"))
                inspection_date = parse_date(request.form.get("inspection_date"))
                planned = parse_int(request.form.get("quantity_planned"))
                completed = parse_int(request.form.get("quantity_completed"), allow_empty=False) or 0
            except (ValueError, TypeError):
                flash("Check dates (YYYY-MM-DD) and quantities (whole numbers).", "error")
                return redirect(url_for("updates"))
            task = (request.form.get("todays_task") or "").strip()
            remarks = (request.form.get("remarks") or "").strip() or None
            status = request.form.get("status") or "In Progress"
            updated_by = request.form.get("updated_by")
            employee_id = int(updated_by) if updated_by else None
            if not project_id or not update_date or not task:
                flash("Project, update date, and today's task are required.", "error")
                return redirect(url_for("updates"))
            if status not in STATUSES:
                flash("Invalid status.", "error")
                return redirect(url_for("updates"))
            if completed < 0 or (planned is not None and (planned < 0 or completed > planned)):
                flash("Quantities must be non-negative; completed cannot exceed planned.", "error")
                return redirect(url_for("updates"))
            try:
                call_proc(
                    "sp_add_production_update",
                    (
                        project_id,
                        update_date,
                        task,
                        remarks,
                        inspection_date,
                        status,
                        planned,
                        completed,
                        employee_id,
                    ),
                )
                call_proc("sp_update_project_status", (project_id, status))
                flash("Daily production update saved.", "success")
            except Error as exc:
                flash(f"Could not save update: {exc}", "error")
            return redirect(url_for("updates"))

        rows = query_rows(
            """
            SELECT pu.update_id, pu.update_date, p.project_id, p.project_no, p.project_name,
                   pu.todays_task, pu.remarks, pu.status, pu.quantity_planned,
                   pu.quantity_completed, pu.inspection_date, e.employee_name
            FROM production_updates pu
            JOIN projects p ON p.project_id = pu.project_id
            LEFT JOIN employees e ON e.employee_id = pu.updated_by
            ORDER BY pu.update_date DESC, pu.update_id DESC
            """
        )
        return render_template(
            "updates.html",
            rows=rows,
            projects=project_choices(),
            employees=employee_choices(),
        )

    @app.route("/manpower", methods=["GET", "POST"])
    @login_required
    def manpower():
        if request.method == "POST":
            if not check_csrf():
                return redirect(url_for("manpower"))
            try:
                project_id = int(request.form.get("project_id") or 0)
                employee_id = int(request.form.get("employee_id") or 0)
                assigned_date = parse_date(request.form.get("assigned_date"))
            except (ValueError, TypeError):
                flash("Choose a project, employee, and a valid assigned date.", "error")
                return redirect(url_for("manpower"))
            role = (request.form.get("assignment_role") or "").strip() or "Production"
            if not project_id or not employee_id or not assigned_date:
                flash("Project, employee, and assigned date are required.", "error")
                return redirect(url_for("manpower"))
            try:
                execute(
                    """
                    INSERT INTO project_manpower
                        (project_id, employee_id, assigned_date, assignment_role)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (project_id, employee_id, assigned_date, role),
                )
                flash("Employee assigned to project.", "success")
            except Error as exc:
                flash(
                    "Could not assign manpower. The employee may already be assigned "
                    f"for this project and date. {exc}",
                    "error",
                )
            return redirect(url_for("manpower"))

        by_project = query_rows("SELECT * FROM vw_manpower_by_project ORDER BY project_no")
        assignments = query_rows(
            """
            SELECT pm.project_id, p.project_no, p.project_name, e.employee_name,
                   e.department, pm.assigned_date, pm.unassigned_date, pm.assignment_role
            FROM project_manpower pm
            JOIN projects p ON p.project_id = pm.project_id
            JOIN employees e ON e.employee_id = pm.employee_id
            ORDER BY p.project_no, e.employee_name
            """
        )
        return render_template(
            "manpower.html",
            by_project=by_project,
            assignments=assignments,
            projects=project_choices(),
            employees=employee_choices(),
        )

    @app.route("/employees", methods=["GET", "POST"])
    @login_required
    def employees():
        if request.method == "POST":
            if user_role() != "Administrator":
                flash("Only an administrator can add employees.", "error")
                return redirect(url_for("employees"))
            if not check_csrf():
                return redirect(url_for("employees"))
            employee_name = " ".join((request.form.get("employee_name") or "").split())
            department = " ".join((request.form.get("department") or "").split()) or "Production"
            job_title = " ".join((request.form.get("job_title") or "").split()) or None
            phone = " ".join((request.form.get("phone") or "").split()) or None
            is_active = 1 if request.form.get("is_active") else 0
            if not employee_name:
                flash("Employee name is required.", "error")
                return redirect(url_for("employees"))
            if len(employee_name) > 100 or len(department) > 60:
                flash("Employee name or department is too long.", "error")
                return redirect(url_for("employees"))
            if job_title and len(job_title) > 80:
                flash("Job title must be 80 characters or less.", "error")
                return redirect(url_for("employees"))
            if phone and (len(phone) > 25 or not all(ch.isdigit() or ch in " +-()" for ch in phone)):
                flash("Enter a phone number using up to 25 digits, spaces, or + - ( ).", "error")
                return redirect(url_for("employees"))
            try:
                execute(
                    """
                    INSERT INTO employees (employee_name, department, job_title, phone, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (employee_name, department, job_title, phone, is_active),
                )
                flash("Employee saved to the database.", "success")
            except Error as exc:
                flash(f"Could not add employee: {exc}", "error")
            return redirect(url_for("employees"))

        rows = query_rows(
            """
            SELECT employee_id, employee_name, department, job_title, phone, is_active, created_at
            FROM employees
            ORDER BY employee_name
            """
        )
        return render_template("employees.html", rows=rows)

    @app.route("/inspections", methods=["GET", "POST"])
    @login_required
    def inspections():
        if request.method == "POST":
            if not check_csrf():
                return redirect(url_for("inspections"))
            try:
                project_id = int(request.form.get("project_id") or 0)
                inspection_date = parse_date(request.form.get("inspection_date"))
                inspected_by = request.form.get("inspected_by")
                employee_id = int(inspected_by) if inspected_by else None
                qty_inspected = parse_int(request.form.get("quantity_inspected"), allow_empty=False) or 0
                qty_passed = parse_int(request.form.get("quantity_passed"), allow_empty=False) or 0
                qty_rejected = parse_int(request.form.get("quantity_rejected"), allow_empty=False) or 0
            except (ValueError, TypeError):
                flash("Check the date and quantity values.", "error")
                return redirect(url_for("inspections"))
            result = request.form.get("result") or "Pending"
            notes = (request.form.get("defect_notes") or "").strip() or None
            if not project_id or not inspection_date:
                flash("Project and inspection date are required.", "error")
                return redirect(url_for("inspections"))
            if result not in INSPECTION_RESULTS:
                flash("Invalid inspection result.", "error")
                return redirect(url_for("inspections"))
            if min(qty_inspected, qty_passed, qty_rejected) < 0 or (qty_passed + qty_rejected) > qty_inspected:
                flash("Passed plus rejected cannot exceed quantity inspected.", "error")
                return redirect(url_for("inspections"))
            try:
                execute(
                    """
                    INSERT INTO quality_inspections
                        (project_id, inspection_date, inspected_by, quantity_inspected,
                         quantity_passed, quantity_rejected, result, defect_notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        project_id,
                        inspection_date,
                        employee_id,
                        qty_inspected,
                        qty_passed,
                        qty_rejected,
                        result,
                        notes,
                    ),
                )
                flash("Quality inspection saved.", "success")
            except Error as exc:
                flash(f"Could not save inspection: {exc}", "error")
            return redirect(url_for("inspections"))

        rows = query_rows(
            """
            SELECT qi.inspection_id, qi.inspection_date, p.project_id, p.project_no, p.project_name,
                   e.employee_name, qi.quantity_inspected, qi.quantity_passed, qi.quantity_rejected,
                   qi.result, qi.defect_notes
            FROM quality_inspections qi
            JOIN projects p ON p.project_id = qi.project_id
            LEFT JOIN employees e ON e.employee_id = qi.inspected_by
            ORDER BY qi.inspection_date DESC, qi.inspection_id DESC
            """
        )
        pending = query_rows("SELECT * FROM vw_pending_inspections ORDER BY inspection_date")
        return render_template(
            "inspections.html",
            rows=rows,
            pending=pending,
            projects=project_choices(),
            employees=employee_choices(),
        )

    @app.route("/reports")
    @login_required
    def reports():
        by_status = query_rows(
            """
            SELECT current_status, COUNT(*) AS project_count
            FROM projects
            GROUP BY current_status
            ORDER BY current_status
            """
        )
        latest = query_rows("SELECT * FROM vw_project_status ORDER BY project_no")
        pending = query_rows("SELECT * FROM vw_pending_inspections ORDER BY inspection_date")
        history = query_rows(
            """
            SELECT sh.history_id, p.project_no, p.project_name, sh.old_status, sh.new_status,
                   sh.changed_at, sh.note
            FROM status_history sh
            JOIN projects p ON p.project_id = sh.project_id
            ORDER BY sh.changed_at DESC, sh.history_id DESC
            """
        )
        return render_template(
            "reports.html",
            by_status=by_status,
            latest=latest,
            pending=pending,
            history=history,
        )

    def csv_response(filename, headers, rows):
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["" if row.get(h) is None else row.get(h) for h in headers])
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/reports/export/projects.csv")
    @login_required
    def export_projects():
        rows = query_rows(
            """
            SELECT p.project_no, p.project_name, c.customer_name, p.current_status,
                   p.start_date, p.planned_end_date, p.project_description
            FROM projects p
            JOIN customers c ON c.customer_id = p.customer_id
            ORDER BY p.project_no
            """
        )
        headers = [
            "project_no",
            "project_name",
            "customer_name",
            "current_status",
            "start_date",
            "planned_end_date",
            "project_description",
        ]
        return csv_response("projects.csv", headers, rows)

    @app.route("/reports/export/updates.csv")
    @login_required
    def export_updates():
        rows = query_rows(
            """
            SELECT pu.update_date, p.project_no, p.project_name, pu.todays_task, pu.remarks,
                   pu.status, pu.quantity_planned, pu.quantity_completed, pu.inspection_date,
                   e.employee_name
            FROM production_updates pu
            JOIN projects p ON p.project_id = pu.project_id
            LEFT JOIN employees e ON e.employee_id = pu.updated_by
            ORDER BY pu.update_date DESC, pu.update_id DESC
            """
        )
        headers = [
            "update_date",
            "project_no",
            "project_name",
            "todays_task",
            "remarks",
            "status",
            "quantity_planned",
            "quantity_completed",
            "inspection_date",
            "employee_name",
        ]
        return csv_response("production_updates.csv", headers, rows)

    @app.route("/reports/export/inspections.csv")
    @login_required
    def export_inspections():
        rows = query_rows(
            """
            SELECT qi.inspection_date, p.project_no, p.project_name, e.employee_name,
                   qi.quantity_inspected, qi.quantity_passed, qi.quantity_rejected,
                   qi.result, qi.defect_notes
            FROM quality_inspections qi
            JOIN projects p ON p.project_id = qi.project_id
            LEFT JOIN employees e ON e.employee_id = qi.inspected_by
            ORDER BY qi.inspection_date DESC, qi.inspection_id DESC
            """
        )
        headers = [
            "inspection_date",
            "project_no",
            "project_name",
            "employee_name",
            "quantity_inspected",
            "quantity_passed",
            "quantity_rejected",
            "result",
            "defect_notes",
        ]
        return csv_response("quality_inspections.csv", headers, rows)

    @app.template_filter("fmt_date")
    def fmt_date(value):
        if value is None:
            return "—"
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M")
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    return app


app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)
