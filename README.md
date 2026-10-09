# Fieldnote Task Manager

A responsive full-stack task management app for capturing, organizing, and completing everyday work. The browser UI uses a Flask JSON API and SQLite persistence.

## Run

Install the Python dependencies and start the server from this folder:

```powershell
python -m pip install -r requirements.txt
python server.py
```

Open `http://127.0.0.1:5000` and create an account with a name, email, and password of at least 8 characters. The database is created as `fieldnote.sqlite3` in the project folder.

Run the API tests with `python -m unittest -v`.

## Features

- Create, edit, complete, and delete tasks
- Set due dates, priorities, and Personal or Work spaces
- Search tasks and filter by status
- View all tasks, tasks due today, upcoming tasks, and completed tasks
- Responsive desktop and mobile layouts
- SQLite persistence across browser sessions
- Password-hashed accounts, signed HttpOnly session cookies, CSRF protection, and per-account task authorization

## Architecture and security

`index.html` contains the app shell and task dialog, `styles.css` contains responsive presentation, and `app.js` owns interaction and calls the same-origin API through `taskApi`. `server.py` serves the UI and JSON endpoints; SQLAlchemy stores accounts and tasks in SQLite.

Passwords are hashed with Werkzeug, session cookies are HttpOnly and SameSite=Strict, unsafe authenticated API requests require a CSRF token, and each task query is scoped to its owner. For deployment beyond localhost, set a persistent random `SESSION_SECRET`, use HTTPS with `COOKIE_SECURE=1`, and configure a production-grade database and operational protections such as rate limiting and backups. Real-time multi-user updates are not included.