import requests  # pyright: ignore[reportMissingModuleSource]
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

can_save = True

# Retry rules for temporary problems (timeout, dropped connection, 5xx).
# 3 attempts in total, waiting 1 second and then 2 seconds between them.

MAX_ATTEMPTS = 3

RETRY_WAITS = [1, 2]

# If GitHub asks us to wait longer than this (seconds), we do not wait.
# We stop and tell the user when to try again.

MAX_RETRY_AFTER = 60

# Becomes True after 401/403/429. Then the current round stops,
# because every other request would be refused in the same way.

stop_requests = False

# -----------------------------------------
# SAVING INFORMATION TO FILE
# -----------------------------------------

def save_data():

    # If the saved file could not be loaded and could not be backed up,
    # we must not write over it. Otherwise the old data would be lost.

    if not can_save:
        print("[Warning] Saving is disabled. Fix", FILE_NAME, "first.")
        return

    # First we write to a temporary file. If the program stops while
    # writing (for example with CTRL+C), only the temporary file is broken.
    # The real file still contains the last valid data.

    temporary_file = FILE_NAME + ".tmp"

    try:
        with open(temporary_file, "w", encoding="utf-8") as file:
            json.dump(repositories, file, indent=4, ensure_ascii=False)

        # Replacing the real file in one step.

        os.replace(temporary_file, FILE_NAME)

    except OSError as error:
        print("[Error] Could not save data:", error)
        return

    print("Data successfully saved.")


# -----------------------------------------
# BACKING UP A BROKEN FILE
# -----------------------------------------

def backup_broken_file():

    global can_save

    # Example name: github_monitor_data_20261103_163000.bak
    # The time in the name keeps older backups from being overwritten.

    time_text = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = FILE_NAME.replace(".json", "") + "_" + time_text + ".bak"

    try:
        os.replace(FILE_NAME, backup_name)
        print("[Warning] The old file was saved as:", backup_name)

    except OSError as error:
        print("[Error] Could not back up the broken file:", error)
        print("[Warning] Saving is disabled to protect the old file.")
        can_save = False

# -----------------------------------------
# FINDING A SAVED REPOSITORY (IGNORING CASE)
# -----------------------------------------

def find_repository_key(name):

    # GitHub names are not case-sensitive:
    # "torvalds/Linux" and "torvalds/linux" are the same repository.
    # We keep the original saved text, but compare with a separate key.
    # Names contain only ASCII letters (repository_name_controller),
    # so casefold() has no Turkish I/i problem here.

    search_key = name.strip().casefold()

    for saved_key in repositories:

        if saved_key.casefold() == search_key:
            return saved_key

    return None

# -----------------------------------------
# CHECKING ONE SAVED RECORD
# -----------------------------------------

def is_valid_record(repository_key, information):

    # Required fields: "owner/name" key, last_commit and last_check texts.

    if not isinstance(repository_key, str):
        return False

    if repository_key.count("/") != 1:
        return False
    
    # The saved name is also used in the request URL, so it must be safe.

    owner, repository = repository_key.split("/")

    if not repository_name_controller(owner, repository, show_errors=False):
        return False
    
    if not isinstance(information, dict):
        return False

    if not isinstance(information.get("last_commit"), str):
        return False

    if not information["last_commit"].strip():
        return False

    if not isinstance(information.get("last_check"), str):
        return False

    return True


# -----------------------------------------
# LOADING INFORMATION FROM FILE
# -----------------------------------------

def load_data():

    global repositories

    repositories = {}

    if not os.path.exists(FILE_NAME):
        return

    try:
        with open(FILE_NAME, "r", encoding="utf-8") as file:
            data = json.load(file)

    except (ValueError, OSError):

        # ValueError covers broken JSON and broken text encoding.

        print("[Warning] Could not read", FILE_NAME)
        backup_broken_file()
        return

    # The file is valid JSON, but it must also be a dictionary.

    if not isinstance(data, dict):
        print("[Warning]", FILE_NAME, "has an unexpected format.")
        backup_broken_file()
        return

    # Keeping valid records, counting the invalid ones.

    invalid_count = 0

    for repository_key, information in data.items():

        # One record per repository: "a/B" and "a/b" are the same one.

        if find_repository_key(repository_key) is not None:
            invalid_count += 1

        elif is_valid_record(repository_key, information):
            repositories[repository_key] = information

        else:
            invalid_count += 1

    if invalid_count > 0:
        print("[Warning]", invalid_count, "invalid record(s) were skipped.")
        backup_broken_file()

        # Saving the valid records right away, so they are not only in memory.

        save_data()


# -----------------------------------------
# GETTING REPOSITORY INFORMATION FROM GITHUB
# -----------------------------------------

def is_valid_commit(commit):

    # Checking the fields this program uses.
    # Example of a valid commit:
    # {"sha": "a1b2...", "html_url": "https://github.com/...",
    #  "commit": {"message": "Fix bug", "author": {"date": "2026-..."}}}

    if not isinstance(commit, dict):
        return False

    if not isinstance(commit.get("sha"), str) or not commit["sha"].strip():
        return False

    if not isinstance(commit.get("html_url"), str):
        return False

    details = commit.get("commit")

    if not isinstance(details, dict):
        return False

    if not isinstance(details.get("message"), str):
        return False

    author = details.get("author")

    if not isinstance(author, dict):
        return False

    if not isinstance(author.get("date"), str):
        return False

    return True


def read_commits(response):

    # Checking a 200 answer before trusting it.
    # Receiving bytes does not prove that the right data arrived.
    # Step 1: the body must be JSON.

    try:
        data = response.json()

    except ValueError:
        print("[Error] GitHub did not send valid JSON.")
        return None

    # Step 2: the JSON must be a list of commits.

    if not isinstance(data, list):
        print("[Error] Unexpected data format from GitHub.")
        return None

    # Step 3: every commit must have the fields we use.
    # If one is wrong, we reject the whole answer and keep old data.

    for commit in data:

        if not is_valid_commit(commit):
            print("[Error] GitHub sent a commit with missing fields.")
            return None

    return data


def wait_before_retry(attempt, reason):

    # Returns True if we waited and may try again,
    # False if the attempt limit is reached.

    if attempt >= MAX_ATTEMPTS:
        print(f"[Error] {reason}. Gave up after {MAX_ATTEMPTS} attempts.")
        return False

    wait_seconds = RETRY_WAITS[attempt - 1]

    print(f"[Warning] {reason}. Retrying in {wait_seconds} s "
          f"(attempt {attempt + 1}/{MAX_ATTEMPTS})...")

    time.sleep(wait_seconds)

    return True


def show_rate_limit_reset(response):

    # GitHub sends the reset time as seconds since 1970 (UTC).

    reset_text = response.headers.get("X-RateLimit-Reset", "")

    if reset_text.isdigit():
        reset_time = datetime.fromtimestamp(int(reset_text))
        print("You can try again after:", reset_time.strftime("%H:%M:%S"))


def get_latest_commits(owner, repository):

    # Return values:
    # list of commits -> success
    # []              -> success, but the repository is empty
    # None            -> failure (do not change saved data)

    global stop_requests

    url = f"https://api.github.com/repos/{owner}/{repository}/commits"

    for attempt in range(1, MAX_ATTEMPTS + 1):

        # ---- Sending the request ----

        try:
            response = requests.get(
                url,
                params={"per_page": 1},
                headers={"Accept": "application/vnd.github+json"},
                timeout=15
            )

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError):

            # Temporary problem: no reply or dropped connection.

            if wait_before_retry(attempt, "No reply from GitHub"):
                continue

            return None

        except requests.exceptions.RequestException as error:

            # Other request problems will not fix themselves.

            print("[Error] Request problem:", error)
            return None

        status = response.status_code

        # ---- 200: success, but the data still needs checking ----

        if status == 200:
            return read_commits(response)

        # ---- 409: valid answer, the repository is empty ----

        if status == 409:
            print("[Info] This repository is empty (no commits yet).")
            return []

        # ---- 404: wrong name or private repository ----

        if status == 404:
            print("[Error] Repository not found or inaccessible.")
            return None

        # ---- 429 or 403 with rate limit headers: too many requests ----

        retry_after = response.headers.get("Retry-After", "")
        remaining = response.headers.get("X-RateLimit-Remaining", "")

        rate_limited = (
            status == 429 or
            (status == 403 and (retry_after != "" or remaining == "0"))
        )

        if rate_limited:

            # Short wait requested: wait as Retry-After says, then retry.

            if (retry_after.isdigit() and
                    int(retry_after) <= MAX_RETRY_AFTER and
                    attempt < MAX_ATTEMPTS):

                print(f"[Warning] Too many requests. "
                      f"GitHub asks to wait {retry_after} s...")
                time.sleep(int(retry_after))
                continue

            # Long wait or no information: stop this round.

            print("[Error] GitHub API rate limit reached.")
            show_rate_limit_reset(response)
            stop_requests = True
            return None

        # ---- 401 / 403: missing or denied access ----

        if status == 401 or status == 403:
            print(f"[Error] Access denied by GitHub ({status}).")
            print("Check the repository permissions.")
            stop_requests = True
            return None

        # ---- 5xx: server error, temporary ----

        if 500 <= status <= 599:

            if wait_before_retry(attempt, f"GitHub server error ({status})"):
                continue

            return None

        # ---- Anything else ----

        print("[Error] GitHub API error:", status)
        return None

    return None

# -----------------------------------------
# CHECKING A REPOSITORY NAME
# -----------------------------------------

def repository_name_controller(owner, repository, show_errors=True):

    # The names go directly into the request URL:
    # https://api.github.com/repos/{owner}/{repository}/commits
    # Characters like ? # % or names like ".." could change that address.
    # So we allow only the characters GitHub allows in names.

    def error(message):
        if show_errors:
            print("[Error]", message)
            print("Example: torvalds/linux")
        return False

    # Owner (user or organization) rules:
    # 1-39 characters, letters, digits and "-", no "-" at the start or end.

    if len(owner) < 1 or len(owner) > 39:
        return error("Owner name must be 1-39 characters.")

    for character in owner:
        if not (character.isascii() and
                (character.isalnum() or character == "-")):
            return error(f"Owner name has an invalid character: {character}")

    if owner.startswith("-") or owner.endswith("-"):
        return error("Owner name cannot start or end with '-'.")

    # Repository name rules:
    # 1-100 characters, letters, digits, "-", "_" and ".".
    # "." and ".." are not real names; they mean "this/upper folder".

    if len(repository) < 1 or len(repository) > 100:
        return error("Repository name must be 1-100 characters.")

    for character in repository:
        if not (character.isascii() and
                (character.isalnum() or character in "-_.")):
            return error(
                f"Repository name has an invalid character: {character}"
            )

    if repository == "." or repository == "..":
        return error("Repository name cannot be '.' or '..'.")

    return True

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
    
    if not repository_name_controller(owner, repository):
        return

    repository_key = f"{owner}/{repository}"

    if find_repository_key(repository_key) is not None:
        print("[Warning] This repository is already being monitored.")
        return

    print("\nConnecting to GitHub...")

    commits = get_latest_commits(owner, repository)

    if commits is None:
        return

    if len(commits) == 0:

        # We need a first commit to compare with later.

        print("[Warning] An empty repository cannot be added yet.")
        print("Try again after the first commit.")
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
        save_data()
        return

    if len(commits) == 0:

        # The check worked, but GitHub now reports no commits.
        # We keep the saved commit and do not report "new commit".

        print(f"[Info] {repository_key}: Repository has no commits now.")
        print("The saved commit is kept.")
        save_data()
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

        # found becomes True only if the saved commit is in the list.

        found = False

        for commit in commits:

            if commit["sha"] == old_commit:
                found = True
                break

            new_commits.append(commit)

        if not found:

            # The saved commit is not in the latest commits.
            # Reason: more new commits than we downloaded,
            # or the history was rewritten (force-push).
            # We cannot know which commits are new, so we show only the latest.

            print("The previous commit is not in the latest",
                  len(commits), "commits.")
            print("Possible reason: too many new commits or a force-push.")
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

    global stop_requests

    if not repositories:
        print("[Info] No repositories to monitor.")
        return

    print("\nChecking all repositories...")

    # Every round starts with permission to send requests.

    stop_requests = False

    for repository_key in list(repositories.keys()):

        # After 401/403/429 the other requests would fail too.

        if stop_requests:
            print("\n[Info] Stopping this round. Saved data is unchanged.")
            break

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

    # Finding the saved name, even if the letter case is different.

    saved_key = find_repository_key(repository_name)

    if saved_key is None:
        print("[Error] Repository not found.")
        return

    repository_name = saved_key

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

    try:

        # Performing the first check immediately.
        # It is inside "try" so CTRL+C during the first check
        # does not crash the program.

        check_all_repositories()

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
try:
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

except (KeyboardInterrupt, EOFError):

    # CTRL+C (or closed input) in the main menu: save and exit cleanly.

    save_data()

    print("\n[Info] Program closed.")