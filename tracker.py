from github import Github, Auth
import configs # Removed duplicate import

GITHUB_ACCESS_TOKEN = configs.get_property("GITHUB_ACCESS_TOKEN")


def get_repo(repo_owner: str, repo_name: str):
    # This function remains unchanged as it fetches the repository object,
    # branch is specified later when getting commits.
    auth = Auth.Token(GITHUB_ACCESS_TOKEN)
    g = Github(auth=auth)
    repo = g.get_repo(f'{repo_owner}/{repo_name}')
    return repo


def get_last_commit_sha(repo_owner: str, repo_name: str, branch_name: str = None) -> str: # Added branch_name
    """Gets the last commit sha from a repository, optionally from a specific branch."""
    repo = get_repo(repo_owner, repo_name)
    # Pass branch_name to the sha parameter. If branch_name is None,
    # PyGithub defaults to the repository's default branch.
    commits = repo.get_commits(sha=branch_name)
    return commits[0].sha if commits else None


def get_not_reported_commits(repo, last_commit_sha: str, branch_name: str = None) -> list: # repo is a Repository object, added branch_name
    """Gets the commits that haven't been reported yet, optionally from a specific branch."""
    # Pass branch_name to the sha parameter.
    commits = repo.get_commits(sha=branch_name)
    not_reported = []
    # The rest of the logic for finding new commits remains the same.
    # It iterates from the latest commit on the (potentially specified) branch.
    if last_commit_sha:
        for commit in commits:
            if commit.sha == last_commit_sha:
                break
            not_reported.append(commit)
    else:
        # If there's no last_commit_sha (e.g., new subscription),
        # we might want to report only the latest commit or a few recent ones.
        # Current behavior is to report none if last_commit_sha is None/empty.
        # Consider if you want to fetch all commits or just the latest one in this case.
        # For simplicity, if last_commit_sha is None, this will return an empty list.
        # To report the latest commit on a new subscription, bot.py would handle that
        # by sending the commit whose SHA was fetched by get_last_commit_sha.
        pass

    return not_reported
