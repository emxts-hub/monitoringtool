import os
import sys
import json
import threading
import uuid

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from config import get_logs_dir


_FIRESTORE_LOCK = threading.Lock()
_FIRESTORE_CLIENT = None
_PENDING_LOGS_LOCK = threading.Lock()
_PENDING_LOGS_FILENAME = "pending_firestore_logs.json"


def _credential_path():
    configured_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if configured_path:
        return configured_path

    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "service-account.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "service-account.json")


def get_firestore_client():
    global _FIRESTORE_CLIENT
    with _FIRESTORE_LOCK:
        if _FIRESTORE_CLIENT is None:
            if not firebase_admin._apps:
                credential_path = _credential_path()
                if not os.path.isfile(credential_path):
                    raise RuntimeError(
                        f"Firestore credential file not found: {credential_path}"
                    )
                firebase_admin.initialize_app(
                    credentials.Certificate(credential_path)
                )
            _FIRESTORE_CLIENT = firestore.client()
        return _FIRESTORE_CLIENT


def _pending_logs_path():
    return os.path.join(get_logs_dir(), _PENDING_LOGS_FILENAME)


def _read_pending_logs():
    path = _pending_logs_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_pending_logs(entries):
    path = _pending_logs_path()
    if not entries:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as error:
            raise OSError(f"Could not remove pending Firestore queue: {error}") from error
        return

    temporary_path = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(entries, file, indent=2)
        os.replace(temporary_path, path)
    except OSError:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def _write_log_online(entry):
    client = get_firestore_client()
    records = entry.get("records") if isinstance(entry, dict) else None
    entry_id = None
    if isinstance(records, list) and records and isinstance(records[0], dict):
        entry_id = records[0].get("entry_id")

    if entry_id:
        client.collection("logs").document(str(entry_id)).set(entry)
    else:
        client.collection("logs").add(entry)


def _queue_pending_log(entry):
    with _PENDING_LOGS_LOCK:
        pending = _read_pending_logs()
        entry_signature = json.dumps(entry, sort_keys=True, default=str)
        if not any(
            json.dumps(item, sort_keys=True, default=str) == entry_signature
            for item in pending
        ):
            pending.append(entry)
            _write_pending_logs(pending)


def write_log(entry):
    """Write a log online, or persist it for the next automatic sync attempt."""
    try:
        _write_log_online(entry)
        return True
    except Exception as error:
        _queue_pending_log(entry)
        print(f"Firestore unavailable; queued log for retry: {error}")
        return False


def sync_pending_logs():
    """Upload queued offline logs and retain any item that still cannot be sent."""
    with _PENDING_LOGS_LOCK:
        pending = _read_pending_logs()
        if not pending:
            return 0

        remaining = []
        uploaded = 0
        for entry in pending:
            try:
                _write_log_online(entry)
                uploaded += 1
            except Exception:
                remaining.append(entry)

        _write_pending_logs(remaining)
        return uploaded


def read_recent_logs(limit=200):
    query = (
        get_firestore_client()
        .collection("logs")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [snapshot.to_dict() for snapshot in query.stream()]


def delete_logs_older_than(cutoff_timestamp):
    client = get_firestore_client()
    old_logs = (
        client.collection("logs")
        .where(filter=FieldFilter("timestamp", "<", cutoff_timestamp))
        .stream()
    )
    batch = client.batch()
    count = 0
    for snapshot in old_logs:
        batch.delete(snapshot.reference)
        count += 1
        if count == 400:
            batch.commit()
            batch = client.batch()
            count = 0
    if count:
        batch.commit()
