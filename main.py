import requests
import schedule
import time
import json
import os
from datetime import datetime


# -----------------------------------------
# GLOBAL VARIABLES
# -----------------------------------------

FILE_NAME = "github_monitor_data.json"

repositories = {}

CHECK_INTERVAL = 30


# -----------------------------------------
# SAVING INFORMATION TO FILE
# -----------------------------------------

def save_data():

    with open(FILE_NAME, "w", encoding="utf-8") as file:
        json.dump(repositories, file, indent=4, ensure_ascii=False)

    print("[Info] Data successfully saved.")


# -----------------------------------------
# LOADING INFORMATION FROM FILE
# -----------------------------------------

def load_data():

    global repositories

    if not os.path.exists(FILE_NAME):
        repositories = {}
        return

    try:
        with open(FILE_NAME, "r", encoding="utf-8") as file:
            repositories = json.load(file)

    except (json.JSONDecodeError, OSError):
        print("[Warning] Could not load saved data.")
        repositories = {}


# -----------------------------------------
# GETTING REPOSITORY INFORMATION FROM GITHUB
# -----------------------------------------

def get_latest_commits(owner, repository):

    url = f"https://api.github.com/repos/{owner}/{repository}/commits"

    try:
        response = requests.get(
            url,
            params={"per_page": 100},
            headers={"Accept": "application/vnd.github+json"},
            timeout=15
        )

        if response.status_code == 200:
            return response.json()

        elif response.status_code == 404:
            print("[Error] Repository not found or inaccessible.")

        elif response.status_code == 403:
            print("[Error] GitHub API rate limit or access restriction.")

        else:
            print("[Error] GitHub API error:", response.status_code)

    except requests.exceptions.RequestException as error:
        print("[Error] Connection problem:", error)

    return None


# -----------------------------------------
# ADDING A NEW REPOSITORY
# -----------------------------------------

def add_repository():

    print("\nAdd New Repository")

    repository_input = input(
        "Enter repository (owner/name or GitHub URL): "
    ).strip().rstrip("/")

    # Accepting both repository names and GitHub URLs.

    if repository_input.startswith("https://github.com/"):
        repository_input = repository_input.replace(
            "https://github.com/", "", 1
        )

    parts = repository_input.split("/")

    if len(parts) != 2 or not all(parts):
        print("[Error] Invalid repository format.")
        print("Example: torvalds/linux")
        return

    owner, repository = parts

    repository_key = f"{owner}/{repository}"

    if repository_key.lower() in (
        key.lower() for key in repositories
    ):
        print("[Warning] This repository is already being monitored.")
        return

    print("\nConnecting to GitHub...")

    commits = get_latest_commits(owner, repository)

    if commits is None:
        return

    if len(commits) == 0:
        print("[Warning] No commits found.")
        return

    latest_commit = commits[0]

    repositories[repository_key] = {
        "last_commit": latest_commit["sha"],
        "last_check": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    }

    save_data()

    print("[Success] Repository added successfully!")
    print("Repository:", repository_key)
    print("Latest commit:", latest_commit["commit"]["message"])


# -----------------------------------------
# SHOWING MONITORED REPOSITORIES
# -----------------------------------------

def show_repositories():

    if not repositories:
        print("\nThere are no monitored repositories.")
        return

    print("\nMonitored Repositories")

    for number, (repository, information) in enumerate(
        repositories.items(), start=1
    ):

        print("\n", number, ".", repository)
        print("Last commit:", information["last_commit"][:10])
        print("Last check:", information["last_check"])


# -----------------------------------------
# CHECKING FOR NEW COMMITS
# -----------------------------------------

def check_repository(repository_key):

    if repository_key not in repositories:
        return

    owner, repository = repository_key.split("/", 1)

    commits = get_latest_commits(owner, repository)

    if commits is None:
        return

    if len(commits) == 0:
        print("[Info] No commits found.")
        return

    old_commit = repositories[repository_key]["last_commit"]
    new_commit = commits[0]["sha"]

    if new_commit == old_commit:

        print(f"[Info] {repository_key}: No new updates.")

    else:

        print("\n" + "=" * 50)
        print("[ALERT] NEW COMMIT(S) DETECTED!")
        print("Repository:", repository_key)
        print("=" * 50)

        # Finding commits added after the previous check.

        new_commits = []

        for commit in commits:

            if commit["sha"] == old_commit:
                break

            new_commits.append(commit)

        if not new_commits:
            print("The previous commit is not in the latest 100 commits.")
            print("Showing the latest commit only.")

            new_commits = [commits[0]]

        for commit in reversed(new_commits):

            print("\nCommit message:",
                  commit["commit"]["message"])

            print("Commit date:",
                  commit["commit"]["author"]["date"])

            print("Commit SHA:",
                  commit["sha"][:10])

            print("Commit URL:",
                  commit["html_url"])

        print("\n" + "=" * 50)

        repositories[repository_key]["last_commit"] = new_commit

    repositories[repository_key]["last_check"] = (
        datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    )

    save_data()


# -----------------------------------------
# CHECKING ALL REPOSITORIES
# -----------------------------------------

def check_all_repositories():

    if not repositories:
        print("[Info] No repositories to monitor.")
        return

    print("\nChecking all repositories...")

    for repository_key in list(repositories.keys()):

        print("\nChecking:", repository_key)

        check_repository(repository_key)


# -----------------------------------------
# REMOVING A REPOSITORY
# -----------------------------------------

def remove_repository():

    if not repositories:
        print("\nThere are no repositories to remove.")
        return

    show_repositories()

    repository_name = input(
        "\nEnter repository name (owner/name) to remove: "
    ).strip()

    if repository_name not in repositories:
        print("[Error] Repository not found.")
        return

    answer = input(
        f"Are you sure you want to remove '{repository_name}'? (y/n): "
    ).strip().lower()

    if answer == "y":

        del repositories[repository_name]

        save_data()

        print("[Success] Repository removed.")

    else:

        print("[Info] Removal cancelled.")


# -----------------------------------------
# CHANGING MONITORING INTERVAL
# -----------------------------------------

def change_interval():

    global CHECK_INTERVAL

    print("\nCurrent monitoring interval:", CHECK_INTERVAL, "minutes")

    try:
        new_interval = int(
            input("Enter new interval in minutes: ")
        )

        if new_interval < 1:
            print("[Error] Interval must be at least 1 minute.")
            return

        CHECK_INTERVAL = new_interval

        print("[Success] Monitoring interval changed.")

    except ValueError:

        print("[Error] Please enter a valid number.")


# -----------------------------------------
# STARTING AUTOMATIC MONITORING
# -----------------------------------------

def start_monitoring():

    if not repositories:
        print("\n[Warning] Add at least one repository first.")
        return

    print("\nAutomatic Monitoring Started!")
    print("Monitoring interval:", CHECK_INTERVAL, "minutes")
    print("Press CTRL+C to stop monitoring.\n")

    # Clearing previously scheduled jobs.

    schedule.clear()

    # Scheduling automatic checks.

    schedule.every(CHECK_INTERVAL).minutes.do(
        check_all_repositories
    )

    # Performing the first check immediately.

    check_all_repositories()

    try:

        while True:

            schedule.run_pending()

            time.sleep(1)

    except KeyboardInterrupt:

        schedule.clear()

        print("\n[Info] Automatic monitoring stopped.")


# -----------------------------------------
# INITIALIZATION
# -----------------------------------------

load_data()


# -----------------------------------------
# MAIN MENU
# -----------------------------------------

while True:

    print("\n")
    print("---------------------------------------------")
    print("       GITHUB REPOSITORY MONITORING SYSTEM")
    print("---------------------------------------------")

    print("1. Add Repository to Monitoring")
    print("2. Show Monitored Repositories")
    print("3. Check for Updates")
    print("4. Remove Repository")
    print("5. Start Automatic Monitoring")
    print("6. Change Monitoring Interval")
    print("0. Exit")

    selection = input("\nWhat would you like to do? (0-6): ").strip()

    os.system("cls" if os.name == "nt" else "clear")

    if selection == "1":

        add_repository()

    elif selection == "2":

        show_repositories()

    elif selection == "3":

        check_all_repositories()

    elif selection == "4":

        remove_repository()

    elif selection == "5":

        start_monitoring()

    elif selection == "6":

        change_interval()

    elif selection == "0":

        save_data()

        print("\nThank you for using GitHub Monitoring System!")

        break

    else:

        print("[Error] Invalid selection. Please try again.")

    if selection != "0" and selection != "5":
        input("\nPress Enter to return to the main menu...")
        os.system("cls" if os.name == "nt" else "clear")