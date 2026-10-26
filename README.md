# Production Status Tracking System (website)

Browser-based Flask website for the existing MySQL database `production_db`. The original Tkinter file `production_status_app_redesigned.py` is unchanged.

This website **reads and writes live tables**. It does not drop, truncate, or recreate production tables.

## What was found in MySQL

Inspected live schema on `localhost` / `production_db`:

| Object | Type | Rows at inspection |
| --- | --- | ---: |
| customers | table | 7 |
| employees | table | 11 |
| projects | table | 14 |
| project_manpower | table | 16 |
| production_updates | table | 13 |
| quality_inspections | table | 4 |
| status_history | table | 2 |
| vw_project_status | view | 14 |
| vw_manpower_by_project | view | 14 |
| vw_pending_inspections | view | 11 |
| sp_add_production_update | procedure | — |
| sp_update_project_status | procedure | — |

There was **no** `app_users` table at inspection time. The website creates that login table only if it is missing (same columns as the desktop app). If the table is empty, it creates the `admin` account once.

## Windows setup

1. Install Python 3 and MySQL Server. Confirm MySQL is running.
2. Open **Command Prompt** or **PowerShell** in this folder:

```bat
cd "C:\Users\shriy\OneDrive\Desktop\production managemanet"
```

3. Create a virtual environment (optional but recommended):

```bat
python -m venv .venv
.venv\Scripts\activate
```

4. Install packages:

```bat
python -m pip install -r requirements.txt
```

5. Copy the environment file and enter your real MySQL password. Do not put the password in `web_app.py`.

```bat
copy .env.example .env
notepad .env
```

Set at least:

```
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password_here
MYSQL_DATABASE=production_db
FLASK_SECRET_KEY=a-long-random-string
FLASK_DEBUG=1
```

6. Run the website:

```bat
python web_app.py
```

7. Open http://127.0.0.1:5000

## Sign in

Accounts live in `app_users`. Passwords are stored as salted hashes. The website no longer creates a default password.

The existing `admin` account is an Administrator. Employees can view data and save production updates, manpower, and inspections. Only an Administrator can create, edit, or delete projects. Deleting a project that already has related rows marks it Cancelled and keeps those rows, because MySQL would otherwise delete them automatically.

Change the password from Account after signing in. Administrators add users from Users.

If login shows a MySQL error, MySQL is not running or `.env` credentials are wrong. The site will not pretend it saved data.

## Pages

- `/` dashboard counts and `vw_project_status`
- `/projects` list, add project, `/projects/<id>` details
- `/updates` daily production form (stored procedures)
- `/manpower` allocation and `vw_manpower_by_project`
- `/employees`
- `/inspections` quality records
- `/reports` plus CSV export

## Safety

- Existing Python desktop file is not modified by this website.
- SQL uses parameterized queries / stored procedures.
- `.env` is gitignored. Use `.env.example` as the template.
