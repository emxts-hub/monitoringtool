import os
from flask import Flask, jsonify, request
from firebase_admin import firestore, initialize_app
from google.cloud.firestore_v1.base_query import FieldFilter


app = Flask(__name__)
initialize_app()
db = firestore.client()


def _require_json():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "JSON object required"}), 400)
    return payload, None


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/logs")
def write_log():
    payload, error = _require_json()
    if error:
        return error
    if not isinstance(payload.get("timestamp"), str) or not isinstance(
        payload.get("records"), list
    ):
        return jsonify({"error": "timestamp and records are required"}), 400
    db.collection("logs").add(payload)
    return jsonify({"status": "ok"}), 201


@app.get("/logs")
def read_logs():
    try:
        limit = min(max(int(request.args.get("limit", "200")), 1), 200)
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    query = (
        db.collection("logs")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return jsonify([snapshot.to_dict() for snapshot in query.stream()])


@app.delete("/logs")
def delete_logs():
    cutoff = request.args.get("before")
    if not cutoff:
        return jsonify({"error": "before is required"}), 400
    snapshots = db.collection("logs").where(
        filter=FieldFilter("timestamp", "<", cutoff)
    ).stream()
    batch = db.batch()
    count = 0
    for snapshot in snapshots:
        batch.delete(snapshot.reference)
        count += 1
        if count == 400:
            batch.commit()
            batch = db.batch()
            count = 0
    if count:
        batch.commit()
    return jsonify({"deleted": count})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
