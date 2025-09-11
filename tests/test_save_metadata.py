import json
import os
import tempfile
import asyncio
import pytest

from app.activities import GitHubMetadataActivities


@pytest.mark.asyncio
async def test_save_metadata_to_file_local(tmp_path, monkeypatch):
    acts = GitHubMetadataActivities()

    # point METADATA_DIR to tmp for this test
    acts.data_dir = str(tmp_path)

    metadata = {"repository": "x/y", "commits": []}
    repo_url = "https://github.com/x/y"
    extraction_id = "abc123"

    path = await acts.save_metadata_to_file([metadata, repo_url, extraction_id])
    assert path.endswith(".json")
    assert os.path.exists(path)

    with open(path, "r") as f:
        data = json.load(f)

    assert data["repository"] == "x/y"
    prov = data.get("extraction_provenance", {})
    assert "saved_at" in prov
    assert "file_path" in prov 