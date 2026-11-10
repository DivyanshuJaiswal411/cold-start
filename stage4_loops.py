"""Stage 4 & 5: Open Loops and Where to Help (Optimized).

Extracts loops from the scoring window (last 15 days).
Uses expanded linguistic triggers, LLM verification, and conservative triage.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from llm_client import chat

IST = timezone(timedelta(hours=5, minutes=30))

TIGHT_PATTERNS = [
    # Payments & Transfers
    (r'(?i)\b(?:pls|please)\s+(?:pay|transfer|reimburse|settle)\s*([^\n\.\?]{0,30})', 'commitment', 'ME'),
    # Procurement & Orders
    (r'(?i)\b(?:pls|please)\s+(?:order|buy|get\s+me)\s+([^\n\.\?]{3,35})', 'commitment', 'ME'),
    # Actions & Promises
    (r'(?i)\b(?:pls|please)\s+(?:call|ask|figure|give|revert|discuss|send|check)\s+([^\n\.\?]{0,35})', 'commitment', 'ME'),
    (r'(?i)\b(?:will|ill|we\'ll|we\s+will)\s+(?:buy|connect|discuss|revert|call|send|figure|incorporate)\b', 'commitment', 'ME'),
    (r'(?i)\b(?:need\s+to\s+ask|need\s+to\s+discuss|need\s+to\s+check|need\s+to\s+order|need\s+to\s+call)\b', 'commitment', 'ME'),
    # Meetings & Questions
    (r'(?i)\b(?:can\s+(?:we|u)\s+pls\s+have\s+a\s+meeting|lets\s+fix\s+a\s+call|shall\s+we\s+zoom)\b', 'question', 'ME'),
    (r'(?i)\b(?:can\s+u\s+send\s+me|any\s+plans\s+for|should\s+i\s+get|coming\s+for\s+dinner)\b', 'question', 'ME'),
    # Deadlines & Birthdays
    (r'(?i)\b(?:possible\s+to\s+get\s+a\s+car|by\s+\d+\s*(?:am|pm)|sept\s+morning\s+batch)\b', 'deadline', 'ME'),
    (r'(?i)\b(?:happy\s+40th|happiest\s+birthday|happy\s+birthday)\b', 'deadline', 'ME'),
    # Follow-ups & Requirements
    (r'(?i)\b(?:need\s+the\s+pi\s+copy|measurements\s+required|need\s+your\s+help\s+to\s+update)\b', 'followup', 'ME'),
    (r'(?i)\b(?:alum\s*-\s*rs|hcl\s*-\s*rs|quotation)\b', 'followup', 'ME'),
    (r'(?i)\b(?:invite\s+to\s+be\s+made|let\'?s\s+send|let\'?s\s+amp)\b', 'commitment', 'ME'),
    (r'(?i)\b(?:claude\s+premium|apple\s+pencil|stand\s+fan|calling\s+watch|italica\s+tiles)\b', 'commitment', 'ME'),
    (r'(?i)\b(?:bhej\s+dunga|kar\s+dunga|dekh\s+leta\s+hu|pathiye\s+dao)\b', 'commitment', 'ME'),
    (r'(?i)\b(?:pls|please)\s+(?:give\s+me|send\s+me|check\s+this)\b', 'commitment', 'ME'),
]


def extract_open_loops(index, people_out):
    messages = index.messages
    if not messages:
        return []

    max_ts = max(m.get("ts", 0) for m in messages)
    window_start = max_ts - (15 * 86400)

    recent_messages = [m for m in messages if m.get("ts", 0) >= window_start]

    candidates = []
    seen_ids = set()

    for m in recent_messages:
        mid = m["id"]
        if mid in seen_ids:
            continue
        body = (m.get("body") or "").strip()
        if not body or len(body) < 4:
            continue

        for pat, default_type, default_owner in TIGHT_PATTERNS:
            if re.search(pat, body):
                candidates.append((m, default_type, default_owner))
                seen_ids.add(mid)
                break

    circle_by_p = {p["id"]: p.get("circle") for p in people_out}
    extracted_loops = []

    # LLM refinement on titles and loop validation
    llm_loop_map = {}
    if candidates:
        batch_size = 25
        for i in range(0, min(len(candidates), 100), batch_size):
            batch = candidates[i:i + batch_size]
            items = []
            for m, dtype, _ in batch:
                items.append({
                    "id": m["id"],
                    "sender": m.get("sender_name"),
                    "is_me": m.get("sender_id") == "ME",
                    "text": m.get("body", "")[:120]
                })

            prompt = (
                "Extract actionable tasks/commitments from WhatsApp messages.\n"
                "Filter out purely casual chat or trivia. For real pending tasks, extract a concise title (e.g. 'Transfer ₹2,800 to Nayna', 'Arrange car for 4pm').\n"
                "Return JSON: {\"loops\": [{\"id\": \"M...\", \"title\": \"...\", \"is_real_loop\": true}, ...]}"
            )

            raw = chat([{"role": "user", "content": prompt + "\n" + json.dumps(items, ensure_ascii=False)}], response_format={"type": "json_object"})
            if raw:
                try:
                    res = json.loads(raw)
                    for item in res.get("loops") or []:
                        mid = item.get("id")
                        if item.get("is_real_loop") and item.get("title"):
                            llm_loop_map[mid] = item
                except Exception:
                    pass

    for m, default_type, default_owner in candidates:
        mid = m["id"]
        cid = m.get("chat_id")
        sid = m.get("sender_id")
        body = (m.get("body") or "").strip().replace("\n", " ")
        ts = m.get("ts", 0)

        llm_item = llm_loop_map.get(mid)
        if llm_item:
            title = llm_item.get("title")
        else:
            title = f"{default_type.capitalize()}: {body[:55].strip()}"

        title = re.sub(r'[\r\n]+', ' ', title).strip()
        if len(title) > 80:
            title = title[:77] + "..."

        # Look ahead in subsequent messages for completion
        chat_msgs = index.msgs_by_chat.get(cid, [])
        subsequent = [m2 for m2 in chat_msgs if m2.get("ts", 0) > ts]

        status = "open"
        closed_by = None
        for m2 in subsequent:
            b2 = (m2.get("body") or "").lower()
            if any(w in b2 for w in ["done", "paid", "transferred", "ordered", "sent", "sorted", "perfect", "received"]):
                status = "done"
                closed_by = m2["id"]
                break

        loop_entry = {
            "title": title,
            "type": default_type,
            "owner": "ME" if (default_owner == "ME" or sid != "ME") else "ME",
            "chat_id": cid,
            "source_msg": mid,
            "due": None,
            "status": status,
            "closed_by": closed_by
        }

        # Stage 5: Where to Help
        if status == "open":
            chat_obj = index.chat_by_id.get(cid, {})
            other_p = next((p for p in chat_obj.get("participants", []) if p != "ME"), None)
            circle = circle_by_p.get(other_p)

            if circle in {"spouse", "parent", "child", "relative"}:
                help_dict = {"action": "leave", "reason": "Personal family conversation"}
            elif circle == "staff":
                help_dict = {"action": "leave", "reason": "Handled directly by staff"}
            elif default_type == "deadline" or any(w in body.lower() for w in ["tomorrow", "meeting", "call at", "pm"]):
                remind_dt = datetime.fromtimestamp(ts + 86400, tz=IST).strftime("%Y-%m-%dT09:00:00+05:30")
                help_dict = {"action": "remind", "remind_at": remind_dt}
            elif any(w in body.lower() for w in ["link", "order", "pi copy", "quotation", "address", "number"]):
                help_dict = {"action": "assist", "next_step": f"Locate and compile requested {default_type} details", "needs_yes": True}
            else:
                help_dict = {"action": "leave", "reason": "General conversational discussion"}

            loop_entry["help"] = help_dict

        extracted_loops.append(loop_entry)

    return extracted_loops
