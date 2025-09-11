import asyncio
import pytest

from app.activities import GitHubMetadataActivities


class DummyCommit:
    def __init__(self, sha, message, author_name, date, html_url):
        class _A:
            def __init__(self, name, date):
                self.name = name
                self.date = date
        class _C:
            def __init__(self, author, message):
                self.author = author
                self.message = message
        self.sha = sha
        self.commit = _C(_A(author_name, date), message)
        self.html_url = html_url


class DummyRepo:
    def __init__(self, commits):
        self._commits = commits
    def get_commits(self):
        return self._commits


@pytest.mark.asyncio
async def test_extract_commit_metadata_shape_and_cache(monkeypatch):
    acts = GitHubMetadataActivities()

    # stub _get_repo to return a dummy repo with commits
    dummy_commits = [
        DummyCommit("abc", "init", "alice", None, "http://c1"),
        DummyCommit("def", "feat", "bob", None, "http://c2"),
    ]

    def fake_get_repo(full_name):
        return DummyRepo(dummy_commits)

    async def fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr(acts, "_get_repo", fake_get_repo)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    repo_url = "https://github.com/x/y"
    extraction_id = "test123"

    # first call populates cache
    out1 = await acts.extract_commit_metadata([repo_url, 10, extraction_id])
    assert isinstance(out1, list)
    assert len(out1) == 2
    assert {"sha", "message", "author", "date", "url"}.issubset(out1[0].keys())

    # second call should hit cache and return the same content quickly
    out2 = await acts.extract_commit_metadata([repo_url, 10, extraction_id])
    assert out2 == out1 