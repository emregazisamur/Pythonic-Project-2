import json
import os
import urllib.request

CONFIG_FILE = "tracked_repos.json"

def load_repos():
    """JSON dosyasından kayıtlı depoları okur."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_repos(repos):
    """Güncellenen repo verilerini JSON dosyasına kaydeder."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(repos, f, indent=4)

def get_latest_commit(repo_name):
    """GitHub API kullanarak depodaki en son commit bilgilerini çeker."""
    url = f"https://api.github.com/repos/{repo_name}/commits"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GitHub-Monitor-App",
            "Accept": "application/vnd.github+json",
        }
    )
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data and isinstance(data, list):
                latest_commit = data[0]
                sha = latest_commit.get("sha")
                message = latest_commit.get("commit", {}).get("message", "Mesaj yok")
                return sha, message
    except Exception as e:
        print(f"[!] Hata oluştu ({repo_name}): {e}")
    return None, None

def check_updates():
    """Takip edilen depoları kontrol eder, yeni commit varsa bildirir."""
    repos = load_repos()

    if not repos:
        print("\n[!] Kontrol edilecek takip edilen depo bulunmuyor.")
        return

    print("\n" + "-"*40)
    print("      GÜNCELLEMELER KONTROL EDİLİYOR... ")
    print("-"*40)

    updates_found = False

    for repo_name, last_sha in list(repos.items()):
        print(f"Kontrol ediliyor: {repo_name}...")
        new_sha, commit_info = get_latest_commit(repo_name)

        if new_sha:
            if