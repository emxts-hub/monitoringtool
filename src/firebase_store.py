import os
import sys
import threading

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter


_FIRESTORE_LOCK = threading.Lock()
_FIRESTORE_CLIENT = None


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


def write_log(entry):
    get_firestore_client().collection("logs").add(entry)


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
