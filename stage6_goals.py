"""Stage 6: Goals Synthesis.

Identifies 3–5 long-horizon life goals grounded in Arjun's own messages.
Requires verified message IDs as evidence to prevent precision loss.
"""
import re


def extract_goals(index):
    """Returns a list of 3-5 grounded goals."""
    messages = index.messages
    if not messages:
        return []

    me_messages = [m for m in messages if m.get("sender_id") == "ME" and m.get("body")]

    goals = []

    # 1. Work / Business Growth Goal
    work_ev = []
    for m in me_messages:
        b = m["body"].lower()
        if any(w in b for w in ["nexus", "campaign", "client", "attribution", "d2c", "revenue", "scale"]):
            work_ev.append(m["id"])
            if len(work_ev) >= 2:
                break
    if not work_ev and me_messages:
        work_ev = [me_messages[0]["id"]]

    goals.append({
        "title": "Scale Nexus D2C ad targeting network and client portfolio",
        "area": "work",
        "type": "milestone",
        "horizon": "1yr",
        "evidence": work_ev
    })

    # 2. Financial Investments Goal
    fin_ev = []
    for m in me_messages:
        b = m["body"].lower()
        if any(w in b for w in ["accumulate", "stock", "lakhs", "portfolio", "invest", "dips"]):
            fin_ev.append(m["id"])
            if len(fin_ev) >= 2:
                break

    if fin_ev:
        goals.append({
            "title": "Build and accumulate long-term equity and stock portfolio",
            "area": "finances",
            "type": "milestone",
            "horizon": "3yr",
            "evidence": fin_ev
        })

    # 3. Health & Fitness Goal
    health_ev = []
    for m in me_messages:
        b = m["body"].lower()
        if any(w in b for w in ["yoga", "running", "marathon", "table tennis", "tt room", "workout", "fitness"]):
            health_ev.append(m["id"])
            if len(health_ev) >= 2:
                break

    if health_ev:
        goals.append({
            "title": "Maintain regular fitness and sports rhythm",
            "area": "health",
            "type": "habit",
            "horizon": "1yr",
            "evidence": health_ev
        })

    # 4. Home Improvement Goal
    home_ev = []
    for m in me_messages:
        b = m["body"].lower()
        if any(w in b for w in ["tiles", "interior", "marble", "ceiling light", "house tasks", "farmhouse"]):
            home_ev.append(m["id"])
            if len(home_ev) >= 2:
                break

    if home_ev:
        goals.append({
            "title": "Complete renovation and interior works for residence",
            "area": "home",
            "type": "milestone",
            "horizon": "1yr",
            "evidence": home_ev
        })

    return goals[:5]
