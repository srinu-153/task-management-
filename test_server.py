import unittest

from server import create_app, db


class TaskApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-session-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SESSION_COOKIE_SECURE": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        with self.app.app_context():
            db.drop_all()

    def register(self, client=None, email="alex@example.com"):
        active_client = client or self.client
        response = active_client.post(
            "/api/auth/register",
            json={"name": "Alex Morgan", "email": email, "password": "correct-horse"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(response.status_code, 201)
        return response.json["csrfToken"]

    def test_tasks_require_authentication(self) -> None:
        response = self.client.get("/api/tasks")
        self.assertEqual(response.status_code, 401)

    def test_register_and_task_crud(self) -> None:
        csrf = self.register()
        headers = {"Origin": "http://localhost", "X-CSRF-Token": csrf}
        created = self.client.post(
            "/api/tasks",
            json={"title": "Write the project brief", "priority": "high", "space": "Work"},
            headers=headers,
        )
        self.assertEqual(created.status_code, 201)
        task_id = created.json["id"]
        self.assertEqual(created.json["title"], "Write the project brief")

        updated = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"title": "Review the project brief", "completed": True},
            headers=headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json["completed"])
        self.assertEqual(updated.json["priority"], "high")

        listed = self.client.get("/api/tasks")
        self.assertEqual(len(listed.json), 1)
        self.assertEqual(listed.json[0]["title"], "Review the project brief")

        deleted = self.client.delete(f"/api/tasks/{task_id}", headers=headers)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/tasks").json, [])

    def test_task_ownership_and_csrf_are_enforced(self) -> None:
        csrf = self.register()
        created = self.client.post(
            "/api/tasks",
            json={"title": "Private task"},
            headers={"Origin": "http://localhost", "X-CSRF-Token": csrf},
        )
        task_id = created.json["id"]

        missing_csrf = self.client.post("/api/tasks", json={"title": "Blocked"})
        self.assertEqual(missing_csrf.status_code, 403)

        another_client = self.app.test_client()
        other_csrf = self.register(another_client, "sam@example.com")
        other_headers = {"Origin": "http://localhost", "X-CSRF-Token": other_csrf}
        self.assertEqual(another_client.get("/api/tasks").json, [])
        forbidden_task = another_client.patch(
            f"/api/tasks/{task_id}", json={"title": "Not yours"}, headers=other_headers
        )
        self.assertEqual(forbidden_task.status_code, 404)

    def test_password_login_and_duplicate_registration(self) -> None:
        self.register()
        duplicate = self.client.post(
            "/api/auth/register",
            json={"name": "Alex", "email": "alex@example.com", "password": "correct-horse"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(duplicate.status_code, 409)

        self.client.post("/api/auth/logout", headers={"Origin": "http://localhost", "X-CSRF-Token": self.client.get("/api/auth/session").json["csrfToken"]})
        login = self.client.post(
            "/api/auth/login",
            json={"email": "alex@example.com", "password": "correct-horse"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json["user"]["email"], "alex@example.com")


if __name__ == "__main__":
    unittest.main()