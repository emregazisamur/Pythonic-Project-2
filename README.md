# Pythonic-Project-2
GitHub Repository Monitoring System

About the Project

GitHub Repository Monitoring System is a Python-based command-line application that allows users to monitor public GitHub repositories and check for new commits.

The application uses the GitHub REST API to retrieve repository commit information and compares the latest commit SHA with the previously stored SHA. If a new commit is detected, the application notifies the user through the terminal.

Features

Add public GitHub repositories to the monitoring list.

Display all monitored repositories.

Check repositories for new commits.

Get notified when new commits are detected.

Remove repositories from the monitoring list.

Start automatic repository monitoring.

Change the monitoring interval.

Save repository information in a JSON file.

Technologies Used

Python: Main programming language.

Requests: Sends HTTP requests to the GitHub REST API.

GitHub REST API: Retrieves repository commit information.

Schedule: Runs automatic monitoring at specified intervals.

JSON: Stores repository information.

Datetime: Records the last check date and time.

How It Works

The user enters a GitHub repository in the format owner/repository.

The application sends a request to the GitHub REST API.

The API returns the latest commits of the repository.

The application stores the latest commit SHA and the last check time.

When the user checks for updates, the application compares the current latest commit SHA with the previously saved SHA.

If the SHA values are different, a new commit is detected and the application displays a notification.

Repository information is saved in github_monitor_data.json so that it can be loaded again when the application restarts.






