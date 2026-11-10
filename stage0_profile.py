"""Stage 0: Load and Profile.

Parses chats.jsonl, messages.jsonl, seed.json.
Standardizes voice transcripts (treats like text), sorts chronologically.
Builds per-person and per-chat statistics and graph adjacency without LLM calls.
"""
import json
from collections import Counter
from pathlib import Path


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_dataset(folder):
    folder = Path(folder)
    chats = read_jsonl(folder / "chats.jsonl")
    messages = read_jsonl(folder / "messages.jsonl")
    seed_path = folder / "seed.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8")) if seed_path.exists() else {}

    # Sort chronologically
    messages.sort(key=lambda m: m.get("ts", 0))

    return chats, messages, seed


class ProfileIndex:
    def __init__(self, chats, messages, seed):
        self.chats = chats
        self.messages = messages
        self.seed = seed

        self.chat_by_id = {c["chat_id"]: c for c in chats}
        self.msg_by_id = {m["id"]: m for m in messages}

        self.msgs_by_chat = {}
        self.msgs_by_sender = {}
        for m in messages:
            cid = m.get("chat_id")
            sid = m.get("sender_id")
            if cid:
                self.msgs_by_chat.setdefault(cid, []).append(m)
            if sid:
                self.msgs_by_sender.setdefault(sid, []).append(m)

        # People IDs (excluding ME)
        self.people_ids = sorted({p for c in chats for p in c.get("participants", [])} - {"ME"})

        # People chats
        self.people_chats = {p: [] for p in self.people_ids}
        self.direct_chat_by_person = {}
        for c in chats:
            cid = c["chat_id"]
            for p in c.get("participants", []):
                if p != "ME" and p in self.people_chats:
                    self.people_chats[p].append(cid)
            if not c.get("is_group"):
                parts = [p for p in c.get("participants", []) if p != "ME"]
                if parts:
                    self.direct_chat_by_person[parts[0]] = cid

        # People profiles
        self.people_profiles = {}
        for pid in self.people_ids:
            sent_msgs = self.msgs_by_sender.get(pid, [])
            direct_cid = self.direct_chat_by_person.get(pid)
            direct_msgs = self.msgs_by_chat.get(direct_cid, []) if direct_cid else []

            # Extract saved names
            names = set()
            for m in sent_msgs:
                sname = m.get("sender_name")
                if sname and sname != "ME":
                    names.add(sname)
            if direct_cid:
                cname = self.chat_by_id[direct_cid].get("name")
                if cname:
                    names.add(cname)

            # Sample message bodies
            sample_bodies = []
            for m in sent_msgs[-5:]:
                b = (m.get("body") or "").strip()
                if b and len(b) > 2 and b not in sample_bodies:
                    sample_bodies.append(b[:120])

            self.people_profiles[pid] = {
                "id": pid,
                "names": sorted(names),
                "total_sent": len(sent_msgs),
                "total_direct": len(direct_msgs),
                "chats": self.people_chats.get(pid, []),
                "direct_chat_id": direct_cid,
                "sample_msgs": sample_bodies
            }

        # Identify spouse candidate: highest 1:1 message volume with domestic/family context
        direct_counts = Counter()
        for pid, prof in self.people_profiles.items():
            if prof["total_direct"] > 0:
                direct_counts[pid] = prof["total_direct"]

        self.spouse_candidate = direct_counts.most_common(1)[0][0] if direct_counts else None
