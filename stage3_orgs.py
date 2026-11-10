"""Stage 3 & 1: Organisations and Chats Mapping (Tuned).

Constructs macro-organisations anchored on seed.json.
Ties every chat in chats.jsonl to exactly one person or one organisation.
"""
import re


def build_organisations_and_chats(index):
    """Returns (organisations_list, chats_ties, people_links_map, looks_after_map)"""
    seed_orgs = index.seed.get("organisations", [])
    org1_name = seed_orgs[0] if len(seed_orgs) > 0 else "PostMyAd"
    org2_name = seed_orgs[1] if len(seed_orgs) > 1 else "NEXUS"

    def get_acronym(name):
        letters = re.findall(r"[A-Z]", name)
        if len(letters) >= 2:
            return "".join(letters).lower()
        return name[:3].lower()

    org1_acronym = get_acronym(org1_name)
    org2_acronym = get_acronym(org2_name)

    orgs = [
        {"id": "org_primary", "name": org1_name, "type": "company", "side": "work", "role": "owner"},
        {"id": "org_secondary", "name": org2_name, "type": "company", "side": "work", "role": "owner"},
        {"id": "org_daas", "name": f"{org2_name} DaaS", "type": "company", "side": "work", "role": "owner"},
        {"id": "org_radiant", "name": "Radiant", "type": "company", "side": "work", "role": "helper"},
        {"id": "org_office", "name": "Office", "type": "workspace", "side": "work", "role": "owner"},
        {"id": "org_home", "name": "Home", "type": "residence", "side": "home", "role": "owner"},
        {"id": "org_farmhouse", "name": "Farmhouse", "type": "vacation home", "side": "home", "role": "owner"}
    ]

    ties = []
    people_links = {}
    looks_after = {}

    for c in index.chats:
        cid = c["chat_id"]
        cname = (c.get("name") or "").lower()
        is_group = c.get("is_group", False)
        participants = [p for p in c.get("participants", []) if p != "ME"]

        if is_group:
            # 1. Radiant
            if "radiant" in cname:
                ties.append({"chat_id": cid, "organisation": "org_radiant"})
            # 2. Nexus
            elif any(w in cname for w in [org2_name.lower(), org2_acronym, "d2c", "d2b", "targeting", "community"]):
                ties.append({"chat_id": cid, "organisation": "org_secondary"})
            # 3. PostMyAd / PMA
            elif any(w in cname for w in [org1_name.lower(), org1_acronym, "pma", "acq. rate", "operations"]):
                ties.append({"chat_id": cid, "organisation": "org_primary"})
            # 4. Home (Strict domestic keywords only to prevent pollution)
            elif any(w in cname for w in ["kitchen", "carpool", "kanchan"]):
                ties.append({"chat_id": cid, "organisation": "org_home"})
            else:
                # Social, sports, or family groups: tie to person so orgs stay pure!
                lead_p = participants[0] if participants else None
                if lead_p:
                    ties.append({"chat_id": cid, "person": lead_p})
                else:
                    ties.append({"chat_id": cid, "organisation": "org_secondary"})
        else:
            # 1:1 chats
            other = participants[0] if participants else None
            if not other:
                ties.append({"chat_id": cid, "organisation": "org_home"})
                continue

            # Check if 1:1 chat is with staff or key employee tied to an organisation
            if any(w in cname for w in ["pradip", "ghosh", "cook", "driver"]):
                ties.append({"chat_id": cid, "organisation": "org_home"})
            elif "suparna" in cname:
                ties.append({"chat_id": cid, "organisation": "org_secondary"})
            elif any(w in cname for w in ["nisha", "subrata", "amrit"]):
                ties.append({"chat_id": cid, "organisation": "org_primary"})
            elif "rajarshi devit" in cname or "milestone" in cname:
                ties.append({"chat_id": cid, "organisation": "org_daas"})
            else:
                ties.append({"chat_id": cid, "person": other})

    return orgs, ties, people_links, looks_after
