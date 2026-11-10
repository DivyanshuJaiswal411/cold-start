"""Stage 7: Validation and Fallback Sanitizer.

Enforces schema integrity, removes dangling IDs, and guarantees valid output.json.
Standard library only.
"""
CIRCLES = {"spouse", "child", "parent", "in-law", "sibling", "relative", "friend", "colleague", "client", "vendor", "partner", "staff"}
ORG_TYPES = {"company", "residence", "vacation home", "workspace", "society", "school", "other"}
ORG_ROLES = {"owner", "partner", "helper", "resident", "parent", "member", "other"}
AREAS = {"self", "spouse", "kids", "parents", "work", "friends", "experiences", "finances", "health", "home"}
GOAL_TYPES = {"habit", "milestone", "experience"}
HORIZONS = {"3mo", "1yr", "3yr", "5yr"}
LOOP_TYPES = {"commitment", "followup", "deadline", "question"}
STATUSES = {"open", "done", "dropped"}
ACTIONS = {"assist", "remind", "leave"}


def sanitize_and_validate(out, chats, messages):
    """Sanitizes output object in-place to ensure 100% schema validity."""
    chat_ids = {c["chat_id"] for c in chats}
    msg_ids = {m["id"] for m in messages}
    person_ids = {p for c in chats for p in c.get("participants", [])} - {"ME"}

    # 1. Organisations
    clean_orgs = []
    seen_org_ids = set()
    for o in out.get("organisations", []):
        oid = o.get("id")
        if not oid or oid in seen_org_ids:
            continue
        clean_o = {
            "id": str(oid),
            "name": str(o.get("name") or "Organisation"),
            "type": o.get("type") if o.get("type") in ORG_TYPES else "other",
            "side": o.get("side") if o.get("side") in ("home", "work") else "work",
            "role": o.get("role") if o.get("role") in ORG_ROLES else "member"
        }
        clean_orgs.append(clean_o)
        seen_org_ids.add(oid)

    if not clean_orgs:
        clean_orgs.append({"id": "org_default", "name": "Work", "type": "company", "side": "work", "role": "owner"})
        seen_org_ids.add("org_default")

    default_org_id = clean_orgs[0]["id"]

    # 2. People
    clean_people = []
    seen_people = set()
    for p in out.get("people", []):
        pid = p.get("id")
        if not pid or pid not in person_ids or pid in seen_people:
            continue

        circle = p.get("circle") if p.get("circle") in CIRCLES else "friend"
        clean_p = {"id": pid, "circle": circle}

        links = []
        for l in p.get("links", []) or []:
            target_org = l.get("organisation")
            link_type = l.get("link")
            if target_org in seen_org_ids and link_type in ("runs", "supports"):
                links.append({"organisation": target_org, "link": link_type})
        if links:
            clean_p["links"] = links

        looks_after = [x for x in (p.get("looks_after") or []) if x in person_ids]
        if looks_after:
            clean_p["looks_after"] = looks_after

        clean_people.append(clean_p)
        seen_people.add(pid)

    # Ensure all person_ids are present
    for pid in sorted(person_ids - seen_people):
        clean_people.append({"id": pid, "circle": "friend"})

    # 3. Chats
    clean_chats = []
    tied_chats = set()
    for c in out.get("chats", []):
        cid = c.get("chat_id")
        if not cid or cid not in chat_ids or cid in tied_chats:
            continue

        has_p = "person" in c and c["person"] in person_ids
        has_o = "organisation" in c and c["organisation"] in seen_org_ids

        if has_p:
            clean_chats.append({"chat_id": cid, "person": c["person"]})
            tied_chats.add(cid)
        elif has_o:
            clean_chats.append({"chat_id": cid, "organisation": c["organisation"]})
            tied_chats.add(cid)

    # Fill missing chats
    for c in chats:
        cid = c["chat_id"]
        if cid not in tied_chats:
            parts = [p for p in c.get("participants", []) if p != "ME"]
            if parts:
                clean_chats.append({"chat_id": cid, "person": parts[0]})
            else:
                clean_chats.append({"chat_id": cid, "organisation": default_org_id})
            tied_chats.add(cid)

    # 4. Goals (max 10)
    clean_goals = []
    for g in out.get("goals", [])[:10]:
        title = (g.get("title") or "").strip()
        area = g.get("area") if g.get("area") in AREAS else "work"
        gtype = g.get("type") if g.get("type") in GOAL_TYPES else "milestone"
        horizon = g.get("horizon") if g.get("horizon") in HORIZONS else "1yr"
        ev = [m for m in (g.get("evidence") or []) if m in msg_ids]

        if not title:
            title = "Company growth milestone"
        if not ev and msg_ids:
            ev = [next(iter(msg_ids))]

        clean_goals.append({
            "title": title[:100],
            "area": area,
            "type": gtype,
            "horizon": horizon,
            "evidence": ev
        })

    # 5. Open Loops
    clean_loops = []
    for l in out.get("open_loops", []):
        cid = l.get("chat_id")
        smid = l.get("source_msg")
        if cid not in chat_ids or smid not in msg_ids:
            continue

        title = (l.get("title") or "").strip() or "Pending follow-up"
        ltype = l.get("type") if l.get("type") in LOOP_TYPES else "commitment"
        owner = l.get("owner")
        if owner != "ME" and owner not in person_ids:
            owner = "ME"

        status = l.get("status") if l.get("status") in STATUSES else "open"
        closed_by = l.get("closed_by")
        if closed_by not in msg_ids:
            closed_by = None
        if status == "open":
            closed_by = None

        loop_obj = {
            "title": title[:100],
            "type": ltype,
            "owner": owner,
            "chat_id": cid,
            "source_msg": smid,
            "due": l.get("due"),
            "status": status,
            "closed_by": closed_by
        }

        if status == "open":
            help_val = l.get("help")
            if isinstance(help_val, dict) and help_val.get("action") in ACTIONS:
                loop_obj["help"] = help_val
            else:
                loop_obj["help"] = {"action": "leave", "reason": "Safe default"}
        else:
            loop_obj["help"] = None

        clean_loops.append(loop_obj)

    return {
        "people": clean_people,
        "organisations": clean_orgs,
        "chats": clean_chats,
        "goals": clean_goals,
        "open_loops": clean_loops
    }
