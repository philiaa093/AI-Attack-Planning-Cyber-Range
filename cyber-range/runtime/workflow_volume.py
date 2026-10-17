"""Fixed offline operations on the isolated workflow volume; never target source."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys


def digest(root):
    files, total = {}, 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("WORKFLOW_VOLUME_SYMLINK")
        if path.is_file():
            total += path.stat().st_size
            if total > 128 * 1024 * 1024 or len(files) >= 10000:
                raise ValueError("WORKFLOW_VOLUME_LIMIT")
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "shoplab.sqlite3" not in files:
        raise ValueError("WORKFLOW_DATABASE_MISSING")
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def main():
    operation = sys.argv[1]
    if operation in ("snapshot", "verify"):
        source = Path("/source")
        value = digest(source)
        if operation == "snapshot":
            destination = Path("/clone")
            if any(destination.iterdir()):
                raise ValueError("WORKFLOW_CLONE_NOT_EMPTY")
            shutil.copytree(source, destination, dirs_exist_ok=True)
            if digest(destination) != value:
                raise ValueError("WORKFLOW_SNAPSHOT_MISMATCH")
        print(json.dumps({"sha256": value}))
    elif operation == "promote":
        username = sys.argv[2]
        if not re.fullmatch(r"rt_[a-f0-9]{12}_c", username):
            raise ValueError("WORKFLOW_ACCOUNT_INVALID")
        with sqlite3.connect("/app/data/shoplab.sqlite3", timeout=5) as db:
            cursor = db.execute("UPDATE users SET role='admin' WHERE username=? AND role='user'", (username,))
            if cursor.rowcount != 1:
                raise ValueError("WORKFLOW_ADMIN_PROVISION_FAILED")
        print('{"status":"PROVISIONED"}')
    else:
        raise ValueError("WORKFLOW_OPERATION_INVALID")


if __name__ == "__main__":
    main()
