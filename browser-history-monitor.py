import os
import time
import sqlite3
import shutil
import platform
import json
import logging
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# =========================
# CONFIGURATION
# =========================
SCAN_INTERVAL = 60

# =========================
# CONSTANTS
# =========================
CHROME_EPOCH_DIFF = 11644473600
MAC_EPOCH_DIFF = 978307200

# =========================
# USER-SCOPED PATHS
# =========================
USER_NAME = os.getlogin()
HOSTNAME = socket.gethostname()

LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home()))
USER_DATA_DIR = LOCAL_APPDATA / "BrowserMonitor"
LOG_FILE = USER_DATA_DIR / "browser_history.log"
STATE_FILE = USER_DATA_DIR / "browser_monitor_state.json"


class BrowserMonitor:
    def __init__(self):
        self.os_type = platform.system()
        self.user_home = Path.home()
        self.state = self.load_state()
        self.setup_logging()

    # -------------------------
    # LOGGING (PER USER)
    # -------------------------
    def setup_logging(self):
        try:
            USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

            self.logger = logging.getLogger(f"BrowserMonitor-{USER_NAME}")
            self.logger.setLevel(logging.INFO)
            self.logger.handlers.clear()
            self.logger.propagate = False

            fmt = f'%(asctime)s {HOSTNAME} browser-monitor[{USER_NAME}]: %(message)s'
            date_fmt = '%b %d %H:%M:%S'
            formatter = logging.Formatter(fmt, datefmt=date_fmt)

            fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

            self.logger.info("Starting Browser Monitor")

        except Exception:
            pass

    # -------------------------
    # STATE MANAGEMENT
    # -------------------------
    def load_state(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_state(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f)
        except Exception as e:
            self.logger.error(f"State save error: {e}")

    # -------------------------
    # BROWSER PATH DISCOVERY
    # -------------------------
    def get_browser_paths(self):
        paths = []

        if self.os_type == "Windows":
            local_app = os.environ.get("LOCALAPPDATA")
            roaming = os.environ.get("APPDATA")

            if local_app:
                paths += [
                    ("Chrome", Path(local_app) / r"Google\Chrome\User Data"),
                    ("Edge", Path(local_app) / r"Microsoft\Edge\User Data"),
                    ("Brave", Path(local_app) / r"BraveSoftware\Brave-Browser\User Data"),
                ]

            if roaming:
                paths += [
                    ("Opera", Path(roaming) / r"Opera Software\Opera Stable"),
                    ("OperaGX", Path(roaming) / r"Opera Software\Opera GX Stable"),
                    ("Firefox", Path(roaming) / r"Mozilla\Firefox\Profiles"),
                ]

        return paths

    def find_profiles(self):
        profiles = []

        for browser, root in self.get_browser_paths():
            if not root.exists():
                continue

            if browser == "Firefox":
                for d in root.iterdir():
                    if d.is_dir() and (d / "places.sqlite").exists():
                        profiles.append({
                            "browser": browser,
                            "profile": d.name,
                            "path": d,
                            "db": "places.sqlite",
                            "type": "firefox"
                        })
                continue

            if (root / "Default" / "History").exists():
                profiles.append({
                    "browser": browser,
                    "profile": "Default",
                    "path": root / "Default",
                    "db": "History",
                    "type": "chrome"
                })

            for p in root.glob("Profile *"):
                if (p / "History").exists():
                    profiles.append({
                        "browser": browser,
                        "profile": p.name,
                        "path": p,
                        "db": "History",
                        "type": "chrome"
                    })

        return profiles

    # -------------------------
    # TIME CONVERSION
    # -------------------------
    def chrome_time(self, ts):
        try:
            return datetime.fromtimestamp(
                (ts / 1_000_000) - CHROME_EPOCH_DIFF,
                timezone.utc
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "N/A"

    def firefox_time(self, ts):
        try:
            return datetime.fromtimestamp(
                ts / 1_000_000,
                timezone.utc
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "N/A"

    # -------------------------
    # HISTORY PROCESSING
    # -------------------------
    def process_history(self, profile):
        db_path = profile["path"] / profile["db"]
        state_key = f"{profile['browser']}_{profile['profile']}"
        last_ts = self.state.get(state_key, 0)

        temp_db = Path(tempfile.gettempdir()) / f"bm_{USER_NAME}_{state_key}.sqlite"

        try:
            shutil.copy2(db_path, temp_db)
        except:
            return

        new_max = last_ts

        try:
            conn = sqlite3.connect(temp_db)
            cur = conn.cursor()

            if profile["type"] == "chrome":
                cur.execute(
                    "SELECT last_visit_time, url, title FROM urls WHERE last_visit_time > ?",
                    (last_ts,)
                )
                rows = cur.fetchall()
                for ts, url, title in rows:
                    new_max = max(new_max, ts)
                    self.logger.info(
                        f"user={USER_NAME} {self.chrome_time(ts)} "
                        f"{profile['browser']} {profile['profile']} {url} {(title or '').replace(chr(10),' ')}"
                    )

            elif profile["type"] == "firefox":
                cur.execute(
                    """SELECT h.visit_date, p.url, p.title
                       FROM moz_historyvisits h
                       JOIN moz_places p ON h.place_id = p.id
                       WHERE h.visit_date > ?""",
                    (last_ts,)
                )
                rows = cur.fetchall()
                for ts, url, title in rows:
                    new_max = max(new_max, ts)
                    self.logger.info(
                        f"user={USER_NAME} {self.firefox_time(ts)} "
                        f"{profile['browser']} {profile['profile']} {url} {(title or '').replace(chr(10),' ')}"
                    )

        except Exception as e:
            self.logger.error(f"DB error {profile['browser']} {profile['profile']}: {e}")
        finally:
            try:
                conn.close()
            except:
                pass
            try:
                temp_db.unlink()
            except:
                pass

        self.state[state_key] = new_max

    # -------------------------
    # MAIN LOOP
    # -------------------------
    def run(self):
        while True:
            for profile in self.find_profiles():
                self.process_history(profile)
            self.save_state()
            time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    BrowserMonitor().run()
