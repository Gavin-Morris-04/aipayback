"""Thin clients for Buttondown (newsletter) and GitHub (preview issues and the hold label).

Buttondown API, checked against its OpenAPI spec on 2026-11-10:
- POST   /v1/emails                  create (status "draft"; metadata holds our issue key)
- POST   /v1/emails/{id}/send-draft  test copies to `recipients` (the founders)
- PATCH  /v1/emails/{id}             status "about_to_send" sends it
- GET    /v1/emails/{id}             read back (body hash check before sending)
Auth: "Authorization: Token <key>". A body that starts with YAML front matter is rejected.
"""

from __future__ import annotations

import httpx2

BUTTONDOWN = "https://api.buttondown.com/v1"
GITHUB = "https://api.github.com"


class ServiceError(RuntimeError):
    pass


def _check(resp: httpx2.Response, what: str) -> dict:
    if resp.status_code >= 400:
        raise ServiceError(f"{what}: HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.content else {}


class Buttondown:
    def __init__(self, api_key: str | None, *, transport: httpx2.BaseTransport | None = None):
        if not api_key:
            raise ServiceError("BUTTONDOWN_API_KEY is not set (GitHub secret or .env).")
        self.http = httpx2.Client(
            base_url=BUTTONDOWN,
            timeout=30,
            transport=transport,
            headers={"Authorization": f"Token {api_key}"},
        )

    def create_draft(self, subject: str, body: str, metadata: dict) -> dict:
        if body.lstrip().startswith("---"):
            raise ServiceError("Body starts with '---' (Buttondown rejects front matter).")
        payload = {"subject": subject, "body": body, "status": "draft", "metadata": metadata}
        return _check(self.http.post("/emails", json=payload), "create draft")

    def send_test(self, email_id: str, recipients: list[str]) -> None:
        if not recipients:
            raise ServiceError("FOUNDER_EMAILS is empty: nobody to send the test copy to.")
        _check(
            self.http.post(f"/emails/{email_id}/send-draft", json={"recipients": recipients}),
            "send test copy",
        )

    def get(self, email_id: str) -> dict:
        return _check(self.http.get(f"/emails/{email_id}"), "read email")

    def send(self, email_id: str) -> dict:
        return _check(
            self.http.patch(f"/emails/{email_id}", json={"status": "about_to_send"}), "send"
        )


class GitHub:
    def __init__(
        self, token: str | None, repo: str | None, *, transport: httpx2.BaseTransport | None = None
    ) -> None:
        if not token or not repo:
            raise ServiceError("GITHUB_TOKEN and GITHUB_REPOSITORY are needed (set in Actions).")
        self.repo = repo
        self.http = httpx2.Client(
            base_url=GITHUB,
            timeout=30,
            transport=transport,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )

    def open_issue(self, title: str, body: str, labels: list[str] | None = None) -> int:
        data = _check(
            self.http.post(
                f"/repos/{self.repo}/issues",
                json={"title": title, "body": body, "labels": labels or []},
            ),
            "open issue",
        )
        return int(data["number"])

    def labels(self, number: int) -> set[str]:
        data = _check(self.http.get(f"/repos/{self.repo}/issues/{number}"), "read issue")
        return {lbl["name"] for lbl in data.get("labels", [])}

    def comment(self, number: int, body: str) -> None:
        _check(
            self.http.post(f"/repos/{self.repo}/issues/{number}/comments", json={"body": body}),
            "comment",
        )

    def close(self, number: int) -> None:
        _check(
            self.http.patch(f"/repos/{self.repo}/issues/{number}", json={"state": "closed"}),
            "close issue",
        )
