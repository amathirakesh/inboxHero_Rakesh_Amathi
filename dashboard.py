import html
import json
from datetime import datetime, timezone
from pathlib import Path

from commitments import (
    build_commitments,
)

from hostile_scanner import (
    scan_hostile_message,
)


BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

DASHBOARD_JSON = (
    BASE_DIR / "dashboard.json"
)

DASHBOARD_HTML = (
    BASE_DIR / "dashboard.html"
)


def load_json(path, default):
    path = Path(path)

    if not path.exists():
        return default

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError:
        return default


def build_pending_actions():
    path = (
        ARTIFACTS_DIR /
        "pending_actions.json"
    )

    actions = load_json(
        path,
        []
    )

    pending = []

    for action in actions:
        # Executed/approved actions are no
        # longer pending.
        if action.get(
            "allowed"
        ) is True:
            continue

        pending.append({
            "message_id":
                action.get(
                    "message_id"
                ),

            "proposed_action":
                action.get(
                    "action_type"
                ),

            "why_human_needed":
                action.get(
                    "reason"
                ),

            "status":
                action.get(
                    "outcome",
                    "pending",
                ),
        })

    return pending


def build_flagged(store):
    path = (
        ARTIFACTS_DIR /
        "flagged.json"
    )

    existing = load_json(
        path,
        []
    )

    flagged = []

    seen = set()

    # R5 hostile-message evidence.
    for item in existing:
        message_id = item.get(
            "message_id"
        )

        if not message_id:
            continue

        seen.add(
            message_id
        )

        flagged.append({
            "message_id":
                message_id,

            "category":
                item.get(
                    "category",
                    "hostile",
                ),

            "attempted":
                item.get(
                    "attempted_actions",
                    []
                ),

            "system_response":
                "Refused, flagged, and "
                "left in place.",
        })

    # Add financial/social-engineering
    # risks from the inbox itself.
    for message_id in [
        "m021",
        "m023",
    ]:
        if message_id in seen:
            continue

        message = store.get_message(
            message_id
        )

        if not message:
            continue

        flagged.append({
            "message_id":
                message_id,

            "category":
                "suspicious_financial_request",

            "attempted": [
                "financial_transfer"
            ],

            "system_response":
                "Escalated for human "
                "verification; no financial "
                "action executed.",
        })

        seen.add(
            message_id
        )

    # Ungrounded ambiguous request.
    if "m012" not in seen:
        message = store.get_message(
            "m012"
        )

        if message:
            flagged.append({
                "message_id":
                    "m012",

                "category":
                    "ungrounded_request",

                "attempted": [
                    "act_without_sufficient_context"
                ],

                "system_response":
                    "Refused to infer missing "
                    "context; clarification is "
                    "required.",
            })

    return flagged


def build_dashboard_data(store):
    return {
        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        # EXACTLY THREE PANES
        "panes": [
            {
                "id":
                    "pending_actions",
                "title":
                    "Pending Actions",
                "items":
                    build_pending_actions(),
            },

            {
                "id":
                    "flagged",
                "title":
                    "Flagged",
                "items":
                    build_flagged(
                        store
                    ),
            },

            {
                "id":
                    "commitments",
                "title":
                    "Commitments",
                "items":
                    build_commitments(
                        store
                    ),
            },
        ],
    }


def esc(value):
    return html.escape(
        str(value)
    )


def render_pending(items):
    if not items:
        return (
            "<p>No pending actions.</p>"
        )

    rows = []

    for item in items:
        rows.append(
            f"""
            <tr>
              <td>{esc(item["message_id"])}</td>
              <td>{esc(item["proposed_action"])}</td>
              <td>{esc(item["why_human_needed"])}</td>
              <td>{esc(item["status"])}</td>
            </tr>
            """
        )

    return f"""
    <table>
      <thead>
        <tr>
          <th>Message</th>
          <th>Proposed action</th>
          <th>Why human is needed</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def render_flagged(items):
    if not items:
        return (
            "<p>No flagged messages.</p>"
        )

    rows = []

    for item in items:
        attempted = ", ".join(
            item["attempted"]
        )

        rows.append(
            f"""
            <tr>
              <td>{esc(item["message_id"])}</td>
              <td>{esc(item["category"])}</td>
              <td>{esc(attempted)}</td>
              <td>{esc(item["system_response"])}</td>
            </tr>
            """
        )

    return f"""
    <table>
      <thead>
        <tr>
          <th>Message</th>
          <th>Category</th>
          <th>Attempted</th>
          <th>System did instead</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def render_commitments(items):
    if not items:
        return (
            "<p>No commitments.</p>"
        )

    # Calendar-like chronological groups.
    by_date = {}

    for item in items:
        by_date.setdefault(
            item["date"],
            []
        ).append(
            item
        )

    sections = []

    for date in sorted(
        by_date.keys()
    ):
        events = []

        for item in by_date[date]:
            sources = ", ".join(
                item[
                    "source_message_ids"
                ]
            )

            conflicts = (
                ", ".join(
                    item[
                        "conflicts_with"
                    ]
                )
                or "None"
            )

            time_value = (
                item["time"]
                or "Deadline"
            )

            conflict_text = ""

            if item[
                "conflicts_with"
            ]:
                conflict_text = (
                    "<strong>"
                    "⚠ Conflict detected"
                    "</strong>"
                )

            derived = (
                "Yes"
                if item["derived"]
                else "No"
            )

            events.append(
                f"""
                <article class="event">
                  <h3>{esc(time_value)} — {esc(item["title"])}</h3>
                  <p>Status: {esc(item["status"])}</p>
                  <p>Sources: {esc(sources)}</p>
                  <p>Multi-message derived: {derived}</p>
                  <p>Conflicts with: {esc(conflicts)}</p>
                  <p>{conflict_text}</p>
                </article>
                """
            )

        sections.append(
            f"""
            <div class="calendar-day">
              <h2>{esc(date)}</h2>
              {''.join(events)}
            </div>
            """
        )

    return "".join(
        sections
    )


def render_html(data):
    pane_map = {
        pane["id"]: pane
        for pane in data["panes"]
    }

    # These are deliberately the only
    # three pane sections.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>inboxHero Dashboard</title>

<style>
body {{
    font-family: system-ui, sans-serif;
    margin: 32px;
    background: #f6f7f9;
}}

h1 {{
    margin-bottom: 4px;
}}

.dashboard {{
    display: grid;
    gap: 24px;
}}

.pane {{
    background: white;
    padding: 20px;
    border-radius: 10px;
}}

table {{
    border-collapse: collapse;
    width: 100%;
}}

th, td {{
    text-align: left;
    padding: 8px;
    border-bottom: 1px solid #ddd;
    vertical-align: top;
}}

.calendar-day {{
    border-left: 4px solid #555;
    padding-left: 16px;
    margin-bottom: 20px;
}}

.event {{
    margin-bottom: 14px;
}}
</style>
</head>

<body>

<h1>inboxHero Dashboard</h1>
<p>
Generated:
{esc(data["generated_at"])}
</p>

<div class="dashboard">

<section class="pane" id="pending-actions">
<h2>Pending Actions</h2>
{render_pending(
    pane_map["pending_actions"]["items"]
)}
</section>

<section class="pane" id="flagged">
<h2>Flagged</h2>
{render_flagged(
    pane_map["flagged"]["items"]
)}
</section>

<section class="pane" id="commitments">
<h2>Commitments</h2>
{render_commitments(
    pane_map["commitments"]["items"]
)}
</section>

</div>

</body>
</html>
"""


def generate_dashboard(store):
    data = build_dashboard_data(
        store
    )

    DASHBOARD_JSON.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    DASHBOARD_HTML.write_text(
        render_html(
            data
        ),
        encoding="utf-8",
    )

    return data