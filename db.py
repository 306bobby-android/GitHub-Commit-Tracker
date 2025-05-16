import json
import os

def set_db():
    """Sets the database."""
    current_dir = os.path.dirname(os.path.realpath(__file__))
    db_path = os.path.join(current_dir, 'db.json')
    if not os.path.exists(db_path):
        with open(db_path, "w") as file:
            json.dump([], file)
    return db_path

DB_PATH = set_db()

def get_all_entries() -> list:
    # Robust loading, ensure file is not empty before loading
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        with open(DB_PATH, "r") as file:
            try:
                db = json.load(file)
                # Ensure it's a list, otherwise return empty or handle error
                return db if isinstance(db, list) else []
            except json.JSONDecodeError:
                return [] # Return empty list if JSON is invalid
    return []


def init_entry(new_entry: dict):
    """
    Initializes or updates an entry in the database.
    The new_entry dict from bot.py typically contains:
    - chat_id
    - repo_owner
    - message_thread_id (can be None)
    - repo_name (initially empty string)
    - last_commit_sha (initially empty string)
    """
    db = get_all_entries()

    entry_found_and_updated = False
    for i, entry in enumerate(db):
        if entry["chat_id"] == new_entry["chat_id"]:
            # Entry exists, user might be re-running /start.
            # Update repo_owner and message_thread_id.
            # Preserve existing repo_name and last_commit_sha,
            # as they are set/updated by update_propery later in bot flow.
            entry.setdefault("repo_name", "")
            entry.setdefault("last_commit_sha", "")
            entry.setdefault("message_thread_id", None)
            entry.setdefault("branch_name", None)

            entry_found_and_updated = True
            break

    if not entry_found_and_updated:
        # New entry, create a full record.
        db_item_to_append = {
            "chat_id": new_entry["chat_id"],
            "repo_owner": new_entry.get("repo_owner"),
            "repo_name": new_entry.get("repo_name", ""),
            "last_commit_sha": new_entry.get("last_commit_sha", ""),
            "message_thread_id": new_entry.get("message_thread_id"),
            "branch_name": new_entry.get("branch_name")
        }
        db.append(db_item_to_append)

    with open(DB_PATH, "w") as file:
        json.dump(db, file, indent=4) # Added indent=4 for better db.json readability


def remove_entry(chat_id: str):
    with open(DB_PATH, "r") as file:
        db = json.load(file)
        for entry in db:
            if entry["chat_id"] == chat_id:
                db.remove(entry)
                break
    with open(DB_PATH, "w") as file:
        json.dump(db, file)


def update_propery(chat_id: str, property: str, value: str):
    with open(DB_PATH, "r") as file:
        db = json.load(file)
        for entry in db:
            if entry["chat_id"] == chat_id:
                entry[property] = value
    with open(DB_PATH, "w") as file:
        json.dump(db, file)

def get_property(chat_id: str, property: str) -> str:
    with open(DB_PATH, "r") as file:
        db = json.load(file)
        for entry in db:
            if entry["chat_id"] == chat_id:
                return entry[property]
    return None


def save_commit_state(chat_id: str, last_commit_sha: str):
    with open(DB_PATH, "r") as file:
        db = json.load(file)
        for entry in db:
            if entry["chat_id"] == chat_id:
                entry["last_commit_sha"] = last_commit_sha
    with open(DB_PATH, "w") as file:
        json.dump(db, file)
