"""Reject repository activity and new human commits from the wrong GitHub account."""

import json
import os
import urllib.request
from pathlib import Path

OWNER = "roygrssmn"
BOTS = {"dependabot[bot]", "github-actions[bot]"}
PERSONAL_EMAILS = {"roy@grossman.im", "9532311+roygrssmn@users.noreply.github.com"}


def check_login(login, label):
    if login not in {OWNER, *BOTS}:
        raise ValueError(f"{label} must use {OWNER}; got {login!r}")


def check_commit(commit):
    data = commit["commit"]
    for label in ("author", "committer"):
        email = data[label]["email"]
        bot = (commit.get(label) or {}).get("login") in BOTS
        github_merge = label == "committer" and email == "noreply@github.com"
        if email not in PERSONAL_EMAILS and not bot and not github_merge:
            raise ValueError(f"Commit {commit['sha']}: {label} has an unapproved identity")


def api(path):
    request = urllib.request.Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    check_login(os.environ["GITHUB_ACTOR"], "Authenticated actor")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    repo = os.environ["GITHUB_REPOSITORY"]
    if "pull_request" in event:
        check_login(event["pull_request"]["user"]["login"], "Pull request author")
        page = 1
        while True:
            commits = api(f"/repos/{repo}/pulls/{event['number']}/commits?per_page=100&page={page}")
            for commit in commits:
                check_commit(commit)
            if len(commits) < 100:
                break
            page += 1
    elif os.environ.get("GITHUB_SHA"):
        check_commit(api(f"/repos/{repo}/commits/{os.environ['GITHUB_SHA']}"))
    print("Repository identity verified: personal account or approved automation.")


if __name__ == "__main__":
    main()
