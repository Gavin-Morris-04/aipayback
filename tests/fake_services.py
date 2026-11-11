"""In-memory Buttondown and GitHub for newsletter tests (httpx2 MockTransport)."""

from __future__ import annotations

import itertools
import json

import httpx2


class FakeButtondown:
    def __init__(self) -> None:
        self.emails: dict[str, dict] = {}
        self.test_sends: list[tuple[str, list[str]]] = []
        self.sent: list[str] = []
        self._ids = itertools.count(1)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path.removeprefix("/v1")
        body = json.loads(request.content) if request.content else {}
        if request.method == "POST" and path == "/emails":
            eid = f"em_{next(self._ids)}"
            self.emails[eid] = {"id": eid, **body}
            return httpx2.Response(201, json=self.emails[eid])
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "emails" and parts[1] in self.emails:
            email = self.emails[parts[1]]
            if request.method == "POST" and parts[-1] == "send-draft":
                self.test_sends.append((parts[1], body["recipients"]))
                return httpx2.Response(200, json={})
            if request.method == "GET":
                return httpx2.Response(200, json=email)
            if request.method == "PATCH":
                email.update(body)
                if body.get("status") == "about_to_send":
                    self.sent.append(parts[1])
                return httpx2.Response(200, json=email)
        return httpx2.Response(404, json={"detail": "not found"})


class FakeGitHub:
    def __init__(self) -> None:
        self.issues: dict[int, dict] = {}
        self._n = itertools.count(1)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        parts = request.url.path.strip("/").split("/")  # repos/<o>/<r>/issues[/<n>[/comments]]
        body = json.loads(request.content) if request.content else {}
        if parts[3:] == ["issues"] and request.method == "POST":
            n = next(self._n)
            self.issues[n] = {
                "number": n,
                "title": body["title"],
                "body": body["body"],
                "labels": [{"name": x} for x in body.get("labels", [])],
                "comments": [],
                "state": "open",
            }
            return httpx2.Response(201, json=self.issues[n])
        n = int(parts[4]) if len(parts) > 4 else None
        issue = self.issues.get(n)
        if issue is None:
            return httpx2.Response(404, json={})
        if len(parts) == 6 and parts[5] == "comments":
            issue["comments"].append(body["body"])
            return httpx2.Response(201, json={})
        if request.method == "PATCH":
            issue.update(body)
        return httpx2.Response(200, json=issue)

    def add_label(self, n: int, name: str) -> None:
        self.issues[n]["labels"].append({"name": name})
