def remove_repositories(repositories, repo_name):
    if repo_name in repositories:
        repositories.remove(repo_name)
        print("Repository removed:", repo_name)
    else:
        print("Repository not found.")
