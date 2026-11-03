def show_repositories(repositories):
    if len(repositories) == 0:
        print("No repositories found.")
    else:
        print("Repositories:")
        for repo in repositories:
            print("-", repo)


if __name__ == "__main__":
    repositories = [
        "emregazisamur/Pythonic-Project-2",
        "example-user/task-tracker"
    ]
    show_repositories(repositories)
