"""
Production Status Tracking System
Frontend: Python + Tkinter
Backend: MySQL (production_db)

Before running:
1. Install the connector:
   python -m pip install mysql-connector-python
2. Edit DB_CONFIG below and enter your MySQL password.
3. Save/run this file using Python 3.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
import hashlib
import secrets
import mysql.connector
from mysql.connector import Error

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Hello@123",
    "database": "production_db",
    "port": 3306,
}


class ProductionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Production Status Tracking System")
        self.root.geometry("1180x720")
        self.root.minsize(900, 600)

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        # Modern light theme using built-in ttk; no extra UI package is required.
        self.root.configure(bg="#F3F6FB")
        self.style.configure("TFrame", background="#F3F6FB")
        self.style.configure("TLabel", background="#F3F6FB", foreground="#243247", font=("Segoe UI", 9))
        self.style.configure("Title.TLabel", background="#F3F6FB", foreground="#12233F", font=("Segoe UI", 21, "bold"))
        self.style.configure("Heading.TLabel", background="#F3F6FB", foreground="#18365D", font=("Segoe UI", 11, "bold"))
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=(10, 7))
        self.style.configure("TNotebook", background="#F3F6FB", borderwidth=0)
        self.style.configure("TNotebook.Tab", padding=(15, 9), font=("Segoe UI", 9, "bold"))
        self.style.map("TNotebook.Tab", background=[("selected", "#FFFFFF")], foreground=[("selected", "#155EEF")])
        self.style.configure("TLabelframe", background="#FFFFFF", bordercolor="#D9E2F0")
        self.style.configure("TLabelframe.Label", background="#FFFFFF", foreground="#18365D", font=("Segoe UI", 10, "bold"))
        self.style.configure("Treeview", rowheight=31, font=("Segoe UI", 9), background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#26364B")
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#E8EEF7", foreground="#18365D", padding=(7, 8))
        self.style.map("Treeview", background=[("selected", "#D9E8FF")], foreground=[("selected", "#12233F")])

        self.connection = None
        self.build_ui()
        self.connect_database()

    def connect_database(self):
        try:
            self.connection = mysql.connector.connect(**DB_CONFIG)
            if self.connection.is_connected():
                self.status_var.set("Connected to MySQL • production_db")
                self.load_customers()
                self.load_projects()
                self.load_dashboard()
                self.load_employees()
        except Error as exc:
            self.status_var.set("Database connection failed")
            messagebox.showerror(
                "MySQL connection error",
                "Python could not connect to MySQL.\n\n"
                "Check that:\n"
                "• MySQL Server is running\n"
                "• The password in DB_CONFIG is correct\n"
                "• The database is named production_db\n\n"
                f"Details: {exc}"
            )

    def ensure_connection(self):
        try:
            if self.connection is None or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**DB_CONFIG)
            return True
        except Error as exc:
            messagebox.showerror("Database error", str(exc))
            return False

    def query_rows(self, sql, params=None):
        if not self.ensure_connection():
            return []
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(sql, params or ())
            return cursor.fetchall()
        except Error as exc:
            messagebox.showerror("Query error", str(exc))
            return []
        finally:
            if cursor:
                cursor.close()

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, padding=(0, 4, 0, 8))
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Production Status Tracking System",
                  style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Refresh All", command=self.refresh_all).pack(side="right")

        self.status_var = tk.StringVar(value="Connecting to MySQL...")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(0, 8))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)

        self.dashboard_tab = ttk.Frame(self.tabs, padding=10)
        self.projects_tab = ttk.Frame(self.tabs, padding=10)
        self.update_tab = ttk.Frame(self.tabs, padding=10)
        self.manpower_tab = ttk.Frame(self.tabs, padding=10)

        self.tabs.add(self.dashboard_tab, text="Dashboard")
        self.tabs.add(self.projects_tab, text="Projects")
        self.tabs.add(self.update_tab, text="Daily Production Update")
        self.tabs.add(self.manpower_tab, text="Manpower")

        self.build_dashboard_tab()
        self.build_projects_tab()
        self.build_updates_tab()
        self.build_manpower_tab()

    def build_dashboard_tab(self):
        cards = ttk.Frame(self.dashboard_tab)
        cards.pack(fill="x", pady=(0, 12))
        self.count_vars = {
            "projects": tk.StringVar(value="—"),
            "in_progress": tk.StringVar(value="—"),
            "on_hold": tk.StringVar(value="—"),
            "customers": tk.StringVar(value="—"),
        }
        card_data = [
            ("Total Projects", self.count_vars["projects"]),
            ("In Progress", self.count_vars["in_progress"]),
            ("On Hold", self.count_vars["on_hold"]),
            ("Customers", self.count_vars["customers"]),
        ]
        for title, var in card_data:
            card = ttk.LabelFrame(cards, text=title, padding=12)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ttk.Label(card, textvariable=var, font=("Segoe UI", 20, "bold")).pack()

        ttk.Label(self.dashboard_tab, text="Latest Production Status",
                  style="Heading.TLabel").pack(anchor="w", pady=(4, 6))
        cols = ("project_no", "project_name", "customer_name", "project_status",
                "update_date", "todays_task", "remarks", "inspection_date")
        headings = ("Project No.", "Project Name", "Customer", "Status",
                    "Update Date", "Today's Task", "Remarks", "Inspection Date")
        self.dashboard_tree = self.make_tree(self.dashboard_tab, cols, headings)
        self.dashboard_tree.pack(fill="both", expand=True)

    def build_projects_tab(self):
        form = ttk.LabelFrame(self.projects_tab, text="Add New Project", padding=10)
        form.pack(fill="x", pady=(0, 12))
        self.project_no_var = tk.StringVar()
        self.project_name_var = tk.StringVar()
        self.project_customer_var = tk.StringVar()
        self.project_start_var = tk.StringVar(value=date.today().isoformat())
        self.project_end_var = tk.StringVar()
        self.project_status_var = tk.StringVar(value="Not Started")

        fields = [
            ("Project Number*", self.project_no_var, 18),
            ("Project Name*", self.project_name_var, 22),
            ("Start Date (YYYY-MM-DD)", self.project_start_var, 15),
            ("Planned End (YYYY-MM-DD)", self.project_end_var, 18),
        ]
        for i, (label, var, width) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=0, column=i, sticky="w", padx=4, pady=3)
            ttk.Entry(form, textvariable=var, width=width).grid(
                row=1, column=i, sticky="ew", padx=4, pady=3
            )

        ttk.Label(form, text="Customer*").grid(row=2, column=0, sticky="w", padx=4, pady=(8, 3))
        self.customer_combo = ttk.Combobox(form, textvariable=self.project_customer_var,
                                           state="readonly", width=20)
        self.customer_combo.grid(row=3, column=0, sticky="ew", padx=4, pady=3)

        ttk.Label(form, text="Initial Status").grid(row=2, column=1, sticky="w", padx=4, pady=(8, 3))
        ttk.Combobox(form, textvariable=self.project_status_var, state="readonly",
                     values=("Not Started", "In Progress", "On Hold", "Completed", "Cancelled"),
                     width=18).grid(row=3, column=1, sticky="w", padx=4, pady=3)

        ttk.Button(form, text="Add Project", command=self.add_project).grid(
            row=3, column=2, padx=4, pady=3, sticky="w"
        )
        ttk.Button(form, text="Clear Form", command=self.clear_project_form).grid(
            row=3, column=3, padx=4, pady=3, sticky="w"
        )

        ttk.Label(self.projects_tab, text="Existing Projects",
                  style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        cols = ("project_no", "project_name", "customer_name", "current_status",
                "start_date", "planned_end_date")
        heads = ("Project No.", "Project Name", "Customer", "Status", "Start Date", "Planned End")
        self.projects_tree = self.make_tree(self.projects_tab, cols, heads)
        self.projects_tree.pack(fill="both", expand=True)

    def build_updates_tab(self):
        form = ttk.LabelFrame(self.update_tab, text="Record Today's Production Work", padding=10)
        form.pack(fill="x", pady=(0, 12))

        self.update_project_var = tk.StringVar()
        self.update_date_var = tk.StringVar(value=date.today().isoformat())
        self.task_var = tk.StringVar()
        self.remarks_var = tk.StringVar()
        self.inspection_var = tk.StringVar()
        self.update_status_var = tk.StringVar(value="In Progress")
        self.planned_var = tk.StringVar()
        self.completed_var = tk.StringVar(value="0")
        self.updated_by_var = tk.StringVar()

        ttk.Label(form, text="Project*").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        self.update_project_combo = ttk.Combobox(
            form, textvariable=self.update_project_var, state="readonly", width=32
        )
        self.update_project_combo.grid(row=1, column=0, sticky="ew", padx=4, pady=3)

        form_fields = [
            ("Update Date* (YYYY-MM-DD)", self.update_date_var),
            ("Today's Task*", self.task_var),
            ("Remarks", self.remarks_var),
            ("Inspection Date (YYYY-MM-DD)", self.inspection_var),
        ]
        for idx, (label, var) in enumerate(form_fields, start=1):
            ttk.Label(form, text=label).grid(row=0, column=idx, sticky="w", padx=4, pady=3)
            ttk.Entry(form, textvariable=var, width=22).grid(
                row=1, column=idx, sticky="ew", padx=4, pady=3
            )

        extra = ttk.Frame(form)
        extra.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        ttk.Label(extra, text="Status").pack(side="left", padx=(4, 3))
        ttk.Combobox(extra, textvariable=self.update_status_var, state="readonly",
                     values=("Not Started", "In Progress", "On Hold", "Completed", "Cancelled"),
                     width=15).pack(side="left", padx=(0, 10))
        ttk.Label(extra, text="Planned Qty").pack(side="left", padx=(0, 3))
        ttk.Entry(extra, textvariable=self.planned_var, width=8).pack(side="left", padx=(0, 10))
        ttk.Label(extra, text="Completed Qty").pack(side="left", padx=(0, 3))
        ttk.Entry(extra, textvariable=self.completed_var, width=8).pack(side="left", padx=(0, 10))
        ttk.Label(extra, text="Updated By").pack(side="left", padx=(0, 3))
        self.employee_combo = ttk.Combobox(extra, textvariable=self.updated_by_var,
                                           state="readonly", width=18)
        self.employee_combo.pack(side="left", padx=(0, 10))
        ttk.Button(extra, text="Save Update", command=self.add_update).pack(side="left", padx=4)

        ttk.Label(self.update_tab, text="Production Update History",
                  style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        cols = ("update_date", "project_no", "project_name", "todays_task",
                "remarks", "status", "quantity_planned", "quantity_completed", "inspection_date")
        heads = ("Date", "Project No.", "Project", "Task", "Remarks", "Status",
                 "Planned Qty", "Completed Qty", "Inspection Date")
        self.updates_tree = self.make_tree(self.update_tab, cols, heads)
        self.updates_tree.pack(fill="both", expand=True)

    def build_manpower_tab(self):
        ttk.Label(self.manpower_tab, text="Current Manpower by Project",
                  style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        cols = ("project_no", "project_name", "manpower_count", "employees")
        heads = ("Project No.", "Project Name", "Manpower Count", "Assigned Employees")
        self.manpower_tree = self.make_tree(self.manpower_tab, cols, heads)
        self.manpower_tree.pack(fill="both", expand=True)

        form = ttk.LabelFrame(self.manpower_tab, text="Assign Employee to Project", padding=10)
        form.pack(fill="x", pady=(12, 0))
        self.assign_project_var = tk.StringVar()
        self.assign_employee_var = tk.StringVar()
        self.assign_date_var = tk.StringVar(value=date.today().isoformat())
        self.assign_role_var = tk.StringVar(value="Production")

        ttk.Label(form, text="Project").grid(row=0, column=0, sticky="w", padx=4)
        self.assign_project_combo = ttk.Combobox(form, textvariable=self.assign_project_var,
                                                 state="readonly", width=30)
        self.assign_project_combo.grid(row=1, column=0, padx=4, pady=4)
        ttk.Label(form, text="Employee").grid(row=0, column=1, sticky="w", padx=4)
        self.assign_employee_combo = ttk.Combobox(form, textvariable=self.assign_employee_var,
                                                  state="readonly", width=25)
        self.assign_employee_combo.grid(row=1, column=1, padx=4, pady=4)
        ttk.Label(form, text="Assigned Date (YYYY-MM-DD)").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Entry(form, textvariable=self.assign_date_var, width=18).grid(
            row=1, column=2, padx=4, pady=4
        )
        ttk.Label(form, text="Role").grid(row=0, column=3, sticky="w", padx=4)
        ttk.Entry(form, textvariable=self.assign_role_var, width=18).grid(
            row=1, column=3, padx=4, pady=4
        )
        ttk.Button(form, text="Assign Manpower", command=self.assign_manpower).grid(
            row=1, column=4, padx=4, pady=4
        )

    @staticmethod
    def make_tree(parent, columns, headings):
        wrapper = ttk.Frame(parent)
        tree = ttk.Treeview(wrapper, columns=columns, show="headings")
        ybar = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(wrapper, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        for col, heading in zip(columns, headings):
            tree.heading(col, text=heading)
            tree.column(col, width=max(105, min(220, len(heading) * 9)), anchor="w")
        # Return a frame-like wrapper that exposes tree methods through attribute.
        wrapper.tree = tree
        return wrapper

    def insert_rows(self, widget, rows, columns):
        tree = widget.tree
        for item in tree.get_children():
            tree.delete(item)
        for row in rows:
            values = []
            for col in columns:
                value = row.get(col)
                values.append("" if value is None else str(value))
            tree.insert("", "end", values=values)

    def load_customers(self):
        rows = self.query_rows("SELECT customer_id, customer_name FROM Customers ORDER BY customer_name")
        self.customer_lookup = {r["customer_name"]: r["customer_id"] for r in rows}
        self.customer_combo["values"] = list(self.customer_lookup.keys())
        if rows and not self.project_customer_var.get():
            self.project_customer_var.set(rows[0]["customer_name"])

    def load_projects(self):
        rows = self.query_rows("""
            SELECT p.project_no, p.project_name, c.customer_name, p.current_status,
                   p.start_date, p.planned_end_date
            FROM Projects p JOIN Customers c ON c.customer_id = p.customer_id
            ORDER BY p.project_no
        """)
        cols = ("project_no", "project_name", "customer_name", "current_status",
                "start_date", "planned_end_date")
        self.insert_rows(self.projects_tree, rows, cols)
        self.project_lookup = {
            f'{r["project_no"]} - {r["project_name"]}': r["project_id"]
            for r in self.query_rows("SELECT project_id, project_no, project_name FROM Projects ORDER BY project_no")
        }
        options = list(self.project_lookup.keys())
        self.update_project_combo["values"] = options
        self.assign_project_combo["values"] = options
        if options:
            if not self.update_project_var.get():
                self.update_project_var.set(options[0])
            if not self.assign_project_var.get():
                self.assign_project_var.set(options[0])

    def load_employees(self):
        rows = self.query_rows("""
            SELECT employee_id, employee_name FROM Employees
            WHERE is_active = TRUE ORDER BY employee_name
        """)
        self.employee_lookup = {r["employee_name"]: r["employee_id"] for r in rows}
        self.employee_combo["values"] = list(self.employee_lookup.keys())
        self.assign_employee_combo["values"] = list(self.employee_lookup.keys())
        if rows:
            if not self.updated_by_var.get():
                self.updated_by_var.set(rows[0]["employee_name"])
            if not self.assign_employee_var.get():
                self.assign_employee_var.set(rows[0]["employee_name"])

    def load_dashboard(self):
        if not self.ensure_connection():
            return
        rows = self.query_rows("""
            SELECT p.project_no, p.project_name, c.customer_name,
                   p.current_status AS project_status,
                   latest.update_date, latest.todays_task, latest.remarks,
                   latest.inspection_date
            FROM Projects p
            JOIN Customers c ON c.customer_id = p.customer_id
            LEFT JOIN (
                SELECT pu.*
                FROM Production_Updates pu
                JOIN (
                    SELECT project_id, MAX(update_date) AS latest_date
                    FROM Production_Updates GROUP BY project_id
                ) d ON d.project_id = pu.project_id AND d.latest_date = pu.update_date
            ) latest ON latest.project_id = p.project_id
            ORDER BY p.project_no
        """)
        cols = ("project_no", "project_name", "customer_name", "project_status",
                "update_date", "todays_task", "remarks", "inspection_date")
        self.insert_rows(self.dashboard_tree, rows, cols)

        counts = self.query_rows("""
            SELECT
                (SELECT COUNT(*) FROM Projects) AS projects,
                (SELECT COUNT(*) FROM Projects WHERE current_status='In Progress') AS in_progress,
                (SELECT COUNT(*) FROM Projects WHERE current_status='On Hold') AS on_hold,
                (SELECT COUNT(*) FROM Customers) AS customers
        """)
        if counts:
            for key, value in counts[0].items():
                self.count_vars[key].set(str(value))

        update_rows = self.query_rows("""
            SELECT pu.update_date, p.project_no, p.project_name, pu.todays_task,
                   pu.remarks, pu.status, pu.quantity_planned, pu.quantity_completed,
                   pu.inspection_date
            FROM Production_Updates pu
            JOIN Projects p ON p.project_id = pu.project_id
            ORDER BY pu.update_date DESC, pu.update_id DESC
        """)
        self.insert_rows(
            self.updates_tree, update_rows,
            ("update_date", "project_no", "project_name", "todays_task", "remarks",
             "status", "quantity_planned", "quantity_completed", "inspection_date")
        )

        manpower_rows = self.query_rows("""
            SELECT p.project_no, p.project_name,
                   COUNT(pm.employee_id) AS manpower_count,
                   COALESCE(GROUP_CONCAT(e.employee_name ORDER BY e.employee_name SEPARATOR ', '), '')
                       AS employees
            FROM Projects p
            LEFT JOIN Project_Manpower pm ON pm.project_id = p.project_id
                 AND pm.unassigned_date IS NULL
            LEFT JOIN Employees e ON e.employee_id = pm.employee_id
            GROUP BY p.project_id, p.project_no, p.project_name
            ORDER BY p.project_no
        """)
        self.insert_rows(self.manpower_tree, manpower_rows,
                         ("project_no", "project_name", "manpower_count", "employees"))

    def add_project(self):
        project_no = self.project_no_var.get().strip()
        project_name = self.project_name_var.get().strip()
        customer_name = self.project_customer_var.get().strip()
        start_date = self.project_start_var.get().strip() or None
        end_date = self.project_end_var.get().strip() or None
        status = self.project_status_var.get()

        if not project_no or not project_name or not customer_name:
            messagebox.showwarning("Missing information", "Project number, project name, and customer are required.")
            return
        if not self.valid_date(start_date) or not self.valid_date(end_date):
            messagebox.showwarning("Invalid date", "Use YYYY-MM-DD for dates, or leave the end date blank.")
            return
        if not self.ensure_connection():
            return
        try:
            customer_id = self.customer_lookup[customer_name]
            cur = self.connection.cursor()
            cur.execute("""
                INSERT INTO Projects
                    (project_no, project_name, customer_id, start_date, planned_end_date, current_status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (project_no, project_name, customer_id, start_date, end_date, status))
            self.connection.commit()
            cur.close()
            messagebox.showinfo("Success", "Project added successfully.")
            self.clear_project_form()
            self.refresh_all()
        except Error as exc:
            self.connection.rollback()
            messagebox.showerror("Could not add project", str(exc))

    def add_update(self):
        project_label = self.update_project_var.get()
        task = self.task_var.get().strip()
        update_date = self.update_date_var.get().strip()
        remarks = self.remarks_var.get().strip() or None
        inspection_date = self.inspection_var.get().strip() or None
        status = self.update_status_var.get()
        planned_text = self.planned_var.get().strip()
        completed_text = self.completed_var.get().strip() or "0"
        employee_name = self.updated_by_var.get().strip()

        if not project_label or not task or not update_date:
            messagebox.showwarning("Missing information", "Choose a project and enter the update date and task.")
            return
        if not self.valid_date(update_date) or not self.valid_date(inspection_date):
            messagebox.showwarning("Invalid date", "Dates must use YYYY-MM-DD. Inspection date can be blank.")
            return
        try:
            planned = int(planned_text) if planned_text else None
            completed = int(completed_text)
            if completed < 0 or (planned is not None and (planned < 0 or completed > planned)):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid quantity", "Enter non-negative whole numbers; completed cannot exceed planned.")
            return

        if not self.ensure_connection():
            return
        try:
            project_id = self.project_lookup[project_label]
            employee_id = self.employee_lookup.get(employee_name) if employee_name else None
            cur = self.connection.cursor()
            cur.execute("""
                INSERT INTO Production_Updates
                    (project_id, update_date, todays_task, remarks, inspection_date,
                     status, quantity_planned, quantity_completed, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (project_id, update_date, task, remarks, inspection_date, status,
                  planned, completed, employee_id))
            cur.execute("UPDATE Projects SET current_status=%s WHERE project_id=%s",
                        (status, project_id))
            self.connection.commit()
            cur.close()
            messagebox.showinfo("Success", "Daily production update saved.")
            self.task_var.set("")
            self.remarks_var.set("")
            self.inspection_var.set("")
            self.planned_var.set("")
            self.completed_var.set("0")
            self.refresh_all()
        except Error as exc:
            self.connection.rollback()
            messagebox.showerror("Could not save update", str(exc))

    def assign_manpower(self):
        project_label = self.assign_project_var.get()
        employee_name = self.assign_employee_var.get()
        assigned_date = self.assign_date_var.get().strip()
        role = self.assign_role_var.get().strip() or "Production"
        if not project_label or not employee_name or not self.valid_date(assigned_date):
            messagebox.showwarning("Missing or invalid information",
                                   "Choose a project and employee and enter the date as YYYY-MM-DD.")
            return
        if not self.ensure_connection():
            return
        try:
            project_id = self.project_lookup[project_label]
            employee_id = self.employee_lookup[employee_name]
            cur = self.connection.cursor()
            cur.execute("""
                INSERT INTO Project_Manpower
                    (project_id, employee_id, assigned_date, assignment_role)
                VALUES (%s, %s, %s, %s)
            """, (project_id, employee_id, assigned_date, role))
            self.connection.commit()
            cur.close()
            messagebox.showinfo("Success", "Employee assigned to project.")
            self.refresh_all()
        except Error as exc:
            self.connection.rollback()
            messagebox.showerror("Could not assign manpower",
                                 "The employee may already have an assignment for this project and date.\n\n"
                                 + str(exc))

    @staticmethod
    def valid_date(value):
        if value in (None, ""):
            return True
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False

    def clear_project_form(self):
        self.project_no_var.set("")
        self.project_name_var.set("")
        self.project_start_var.set(date.today().isoformat())
        self.project_end_var.set("")
        self.project_status_var.set("Not Started")
        if self.customer_combo["values"]:
            self.project_customer_var.set(self.customer_combo["values"][0])

    def refresh_all(self):
        if not self.ensure_connection():
            return
        self.load_customers()
        self.load_projects()
        self.load_employees()
        self.load_dashboard()
        self.status_var.set("Connected to MySQL • production_db • Data refreshed")

    def close(self):
        try:
            if self.connection and self.connection.is_connected():
                self.connection.close()
        except Error:
            pass
        self.root.destroy()



class LoginWindow:
    """Database-backed login screen with salted password hashes."""
    def __init__(self, root):
        self.root = root
        self.root.title("Sign in | Production Status Tracking System")
        self.root.geometry("480x570")
        self.root.resizable(False, False)
        self.root.configure(bg="#F3F6FB")
        self.authenticated = False
        self.username = None

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Login.TFrame", background="#FFFFFF")
        style.configure("LoginTitle.TLabel", background="#FFFFFF", foreground="#13294B", font=("Segoe UI", 21, "bold"))
        style.configure("LoginSub.TLabel", background="#FFFFFF", foreground="#64748B", font=("Segoe UI", 10))
        style.configure("LoginLabel.TLabel", background="#FFFFFF", foreground="#334155", font=("Segoe UI", 9, "bold"))
        style.configure("Login.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 10), background="#155EEF", foreground="#FFFFFF")
        style.map("Login.TButton", background=[("active", "#124BC4")])

        card = ttk.Frame(root, style="Login.TFrame", padding=30)
        card.pack(fill="both", expand=True, padx=28, pady=28)
        mark = tk.Label(card, text="P", bg="#155EEF", fg="white", font=("Segoe UI", 19, "bold"), width=3, height=1)
        mark.pack(pady=(10, 16))
        ttk.Label(card, text="Production Status", style="LoginTitle.TLabel").pack()
        ttk.Label(card, text="TRACKING SYSTEM", style="LoginSub.TLabel").pack(pady=(2, 8))
        ttk.Label(card, text="Sign in to continue to your workspace", style="LoginSub.TLabel").pack(pady=(0, 25))

        ttk.Label(card, text="USERNAME", style="LoginLabel.TLabel").pack(anchor="w", pady=(0, 6))
        self.username_var = tk.StringVar(value="admin")
        self.username_entry = ttk.Entry(card, textvariable=self.username_var, font=("Segoe UI", 11))
        self.username_entry.pack(fill="x", ipady=7, pady=(0, 15))
        ttk.Label(card, text="PASSWORD", style="LoginLabel.TLabel").pack(anchor="w", pady=(0, 6))
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(card, textvariable=self.password_var, show="●", font=("Segoe UI", 11))
        self.password_entry.pack(fill="x", ipady=7, pady=(0, 20))
        self.password_entry.bind("<Return>", lambda _event: self.login())
        ttk.Button(card, text="SIGN IN", style="Login.TButton", command=self.login).pack(fill="x", ipady=3)
        self.message_var = tk.StringVar(value="")
        tk.Label(card, textvariable=self.message_var, bg="#FFFFFF", fg="#B42318", font=("Segoe UI", 9), wraplength=350).pack(pady=(12, 0))
        tk.Label(card, text="Authorized company personnel only", bg="#FFFFFF", fg="#94A3B8", font=("Segoe UI", 8)).pack(side="bottom", pady=(22, 0))
        self.username_entry.focus_set()

    @staticmethod
    def hash_password(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
        return salt, digest

    def login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            self.message_var.set("Enter both username and password.")
            return
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(**DB_CONFIG)
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_users (
                    user_id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(60) NOT NULL UNIQUE,
                    password_salt VARCHAR(64) NOT NULL,
                    password_hash VARCHAR(128) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.commit()
            cursor.execute("SELECT COUNT(*) AS user_count FROM app_users")
            count = cursor.fetchone()["user_count"]
            if count == 0:
                # Demo account created only when this login table is empty.
                salt, digest = self.hash_password("Production@123")
                cursor.execute("INSERT INTO app_users (username, password_salt, password_hash) VALUES (%s, %s, %s)", ("admin", salt, digest))
                connection.commit()
            cursor.execute("SELECT username, password_salt, password_hash FROM app_users WHERE username=%s", (username,))
            row = cursor.fetchone()
            if not row:
                self.message_var.set("Invalid username or password.")
                return
            _, digest = self.hash_password(password, row["password_salt"])
            if secrets.compare_digest(digest, row["password_hash"]):
                self.authenticated = True
                self.username = row["username"]
                self.root.destroy()
            else:
                self.message_var.set("Invalid username or password.")
        except Error as exc:
            self.message_var.set("Could not connect to MySQL. Check DB_CONFIG and ensure MySQL Server is running.")
            messagebox.showerror("Database connection", f"Could not verify login.\n\n{exc}")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

def main():
    login_root = tk.Tk()
    login = LoginWindow(login_root)
    login_root.mainloop()
    if not login.authenticated:
        return

    root = tk.Tk()
    app = ProductionApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
