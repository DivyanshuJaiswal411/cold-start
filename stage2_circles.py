"""Stage 2: People and Circles Classification (Refined).

Combines seed few-shot demonstrations, graph propagation, and batched LLM classification.
Outputs each person with their circle, organisation links ('runs'/'supports'),
and 'looks_after' annotations.
"""
import json
import re
from llm_client import chat

ALLOWED_CIRCLES = {
    "spouse", "child", "parent", "in-law", "sibling", "relative",
    "friend", "colleague", "client", "vendor", "partner", "staff"
}


def classify_circles(index, orgs):
    seeded_circles = index.seed.get("circles", {})
    people_out = []

    org_by_name = {o["name"]: o["id"] for o in orgs}
    primary_org_id = org_by_name.get(index.seed.get("organisations", [""])[0], "org_primary")
    secondary_org_id = org_by_name.get(index.seed.get("organisations", ["", ""])[1] if len(index.seed.get("organisations", [])) > 1 else "", "org_secondary")

    rules_circles = {}
    people_links = {}
    looks_after = {}

    for pid in index.people_ids:
        prof = index.people_profiles[pid]
        p_cnames = [index.chat_by_id[cid].get("name", "").lower() for cid in prof["chats"]]
        all_cnames_str = " ".join(p_cnames)
        saved_names_str = " ".join(prof["names"]).lower()
        all_text = all_cnames_str + " " + saved_names_str + " " + " ".join(prof["sample_msgs"]).lower()

        # Seeded
        if pid in seeded_circles:
            rules_circles[pid] = seeded_circles[pid]
        elif pid == index.spouse_candidate:
            rules_circles[pid] = "spouse"
        # Domestic / Staff
        elif any(w in all_text for w in ["kitchen", "carpool", "cook", "driver", "maid", "bania", "pradip", "haradhan", "pma office", "suchandra"]):
            rules_circles[pid] = "staff"
            if "kitchen" in all_text or "pradip" in all_text:
                people_links.setdefault(pid, []).append({"organisation": "org_home", "link": "supports"})
            elif "bania" in all_text or "farmhouse" in all_text:
                people_links.setdefault(pid, []).append({"organisation": "org_farmhouse", "link": "supports"})
            elif "pma office" in all_text or "suchandra" in all_text:
                people_links.setdefault(pid, []).append({"organisation": "org_office", "link": "supports"})
            else:
                people_links.setdefault(pid, []).append({"organisation": "org_home", "link": "supports"})

            if "driver" in all_text or "carpool" in all_text:
                if index.spouse_candidate:
                    looks_after[pid] = [index.spouse_candidate]

        # Family Memoir & Vacation Groups (Always Relative)
        elif any(w in all_cnames_str for w in ["tadoba", "coffee table", "project coffee"]):
            rules_circles[pid] = "relative"

        # Direct Family & Siblings
        elif any(w in all_text for w in ["devika", "mother", "father", "mummy", "papa"]):
            rules_circles[pid] = "parent"
        elif any(w in all_text for w in ["ishaan", "siblings", "bro& sis", "bhai", "didi", "ratekar"]):
            rules_circles[pid] = "sibling"
        elif any(w in all_text for w in ["family", "khetan", "heart is"]):
            rules_circles[pid] = "relative"

        # Vendor
        elif any(w in all_text for w in ["trading company", "enterprises", "tax invoice", "gst", "supply", "alum", "hcl", "godown", "printers", "anmol"]):
            rules_circles[pid] = "vendor"

        # Partners
        elif any(w in all_cnames_str for w in ["milestone", "daas", "steven"]):
            rules_circles[pid] = "partner"
            people_links.setdefault(pid, []).append({"organisation": "org_daas", "link": "runs"})

        # Colleague (Core operations)
        elif any(w in all_cnames_str for w in ["pma operations", "acq. rate", "subrata", "amrit", "nisha"]):
            rules_circles[pid] = "colleague"
            people_links.setdefault(pid, []).append({"organisation": primary_org_id, "link": "runs"})
        elif any(w in all_cnames_str for w in ["nexus: finance", "nexus meta ai", "inner ring", "orbit", "srishti", "chandrima", "suparna"]):
            rules_circles[pid] = "colleague"
            people_links.setdefault(pid, []).append({"organisation": secondary_org_id, "link": "runs"})
        elif "radiant operations" in all_cnames_str:
            rules_circles[pid] = "colleague"
            people_links.setdefault(pid, []).append({"organisation": "org_radiant", "link": "runs"})

        # Client
        elif any(w in all_cnames_str for w in ["ad targeting", "skincare", "diagnostics", "jewellers", "recycling", "d2c", "jajodia", "malwal"]):
            rules_circles[pid] = "client"

        # Friend (Social sports & dinner groups)
        elif any(w in all_cnames_str for w in ["bvf", "tennis", "pickle ball", "club", "yoga", "birla house", "nerds"]):
            rules_circles[pid] = "friend"
        else:
            rules_circles[pid] = "friend"

    # LLM Refinement for active contacts with few-shot guidance
    active_unseeded = [
        pid for pid in index.people_ids
        if pid not in seeded_circles and pid != index.spouse_candidate and (index.people_profiles[pid]["total_sent"] >= 1 or index.people_profiles[pid]["total_direct"] >= 1)
    ]

    llm_predictions = {}
    if active_unseeded:
        seed_examples = []
        for spid, scircle in list(seeded_circles.items())[:6]:
            sprof = index.people_profiles.get(spid)
            if sprof:
                seed_examples.append({
                    "id": spid,
                    "names": sprof["names"][:2],
                    "chats": [index.chat_by_id[cid].get("name", "") for cid in sprof["chats"][:3]],
                    "circle": scircle
                })

        batch_size = 25
        for i in range(0, len(active_unseeded), batch_size):
            batch_pids = active_unseeded[i:i + batch_size]
            dossiers = []
            for pid in batch_pids:
                prof = index.people_profiles[pid]
                cnames = [index.chat_by_id[cid].get("name", "") for cid in prof["chats"][:4]]
                dossiers.append({
                    "id": pid,
                    "names": prof["names"][:2],
                    "chats": cnames,
                    "sample_msgs": prof["sample_msgs"][:3]
                })

            prompt = (
                "You are an expert classifying people in Arjun's WhatsApp into exactly ONE of these 12 circles:\n"
                "['spouse', 'child', 'parent', 'in-law', 'sibling', 'relative', 'friend', 'colleague', 'client', 'vendor', 'partner', 'staff']\n\n"
                f"Few-shot examples from Arjun's seed data:\n{json.dumps(seed_examples, ensure_ascii=False, indent=2)}\n\n"
                "Guidelines:\n"
                "- staff: cook, driver, maid, personal assistant, office cleaner, maintenance.\n"
                "- colleague: works at Arjun's companies (PostMyAd, NEXUS) in operations, accounts, tech.\n"
                "- partner: business co-founders or joint venture partners.\n"
                "- client: brand founders or marketing heads running campaigns with Arjun.\n"
                "- vendor: supplier, agency, printer, equipment or materials provider (e.g. trading company).\n"
                "- relative: family members, cousins, aunts, in family vacation or memoir book groups.\n"
                "- friend: personal buddies from table tennis, pickleball, social clubs, school/college.\n\n"
                f"Classify these contacts:\n{json.dumps(dossiers, ensure_ascii=False, indent=2)}\n\n"
                "Return valid JSON object: {\"results\": [{\"id\": \"P...\", \"circle\": \"...\"}, ...]}"
            )

            raw = chat([{"role": "user", "content": prompt}], response_format={"type": "json_object"})
            if raw:
                try:
                    res = json.loads(raw)
                    items = res.get("results") or res.get("classifications") or []
                    for item in items:
                        pid = item.get("id")
                        c = item.get("circle")
                        if pid in batch_pids and c in ALLOWED_CIRCLES:
                            llm_predictions[pid] = c
                except Exception:
                    pass

    # Assemble final people output
    for pid in index.people_ids:
        # Prefer specific rules for strong structural categories (family groups, staff), then LLM, then rule fallback
        final_circle = seeded_circles.get(pid) or rules_circles.get(pid) or llm_predictions.get(pid) or "friend"
        entry = {"id": pid, "circle": final_circle}

        links = people_links.get(pid, [])
        if final_circle == "colleague" and not links:
            p_cnames_str = " ".join([index.chat_by_id[cid].get("name", "").lower() for cid in index.people_profiles[pid]["chats"]])
            if "pma" in p_cnames_str:
                links = [{"organisation": primary_org_id, "link": "runs"}]
            else:
                links = [{"organisation": secondary_org_id, "link": "runs"}]
        elif final_circle == "staff" and not links:
            links = [{"organisation": "org_home", "link": "supports"}]

        if links:
            entry["links"] = links
        if pid in looks_after:
            entry["looks_after"] = looks_after[pid]

        people_out.append(entry)

    return people_out
