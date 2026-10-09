# Workspace Guidance

- Run the app with `python server.py`; it serves the frontend and Flask API from one origin.
- Preserve the `taskApi` boundary when changing persistence so UI event handlers do not depend on API details.
- Keep every task query scoped to the authenticated owner and protect unsafe session-authenticated requests with CSRF validation.
- Keep task rendering escaped and maintain keyboard-accessible labels and responsive layouts.
- Verify changes in a browser at desktop and mobile widths when the UI changes.