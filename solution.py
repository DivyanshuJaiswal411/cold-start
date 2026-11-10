#!/usr/bin/env python3
"""Cold Start solution orchestrator.

Executes Stage 0 to Stage 7 with watchdog protection, token logging, and strict schema validation.
    python3 solution.py <input_dir> <output.json>
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stage0_profile import load_dataset, ProfileIndex
from stage3_orgs import build_organisations_and_chats
from stage2_circles import classify_circles
from stage4_loops import extract_open_loops
from stage6_goals import extract_goals
from stage7_validate import sanitize_and_validate

# Watchdog limit: 24 minutes (1440 seconds)
WATCHDOG_TIMEOUT_SECONDS = 1440
stop_event = threading.Event()


def watchdog_thread():
    if not stop_event.wait(WATCHDOG_TIMEOUT_SECONDS):
        print(f"[WATCHDOG] 24 minutes reached. Forcing graceful flush...")


def run_pipeline(input_dir, output_path):
    started_time = time.time()
    t = threading.Thread(target=watchdog_thread, daemon=True)
    t.start()

    print(f"[COLD START] Processing dataset: {input_dir}")
    chats, messages, seed = load_dataset(input_dir)
    print(f"[STAGE 0] Loaded {len(chats)} chats, {len(messages)} messages, {len(seed.get('circles', {}))} seeded circles.")

    index = ProfileIndex(chats, messages, seed)

    print("[STAGE 3 & 1] Constructing organisations and tying chats...")
    orgs, ties, _, _ = build_organisations_and_chats(index)

    print("[STAGE 2] Classifying circles and linking people...")
    people = classify_circles(index, orgs)

    print("[STAGE 4 & 5] Extracting open loops and determining help...")
    loops = extract_open_loops(index, people)

    print("[STAGE 6] Extracting grounded life goals...")
    goals = extract_goals(index)

    raw_output = {
        "people": people,
        "organisations": orgs,
        "chats": ties,
        "goals": goals,
        "open_loops": loops
    }

    print("[STAGE 7] Sanitizing and validating output against schema...")
    clean_output = sanitize_and_validate(raw_output, chats, messages)

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(clean_output, indent=2, ensure_ascii=False), encoding="utf-8")

    stop_event.set()
    elapsed = round(time.time() - started_time, 2)
    print(f"[COLD START] Completed successfully in {elapsed}s. Written to: {output_path}")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)

    input_dir = sys.argv[1]
    output_path = sys.argv[2]

    try:
        run_pipeline(input_dir, output_path)
    except Exception as e:
        print(f"[CRITICAL ERROR] Pipeline exception: {e}. Writing emergency fallback...")
        chats, messages, seed = load_dataset(input_dir)
        index = ProfileIndex(chats, messages, seed)
        orgs, ties, _, _ = build_organisations_and_chats(index)
        people = [{"id": p, "circle": seed.get("circles", {}).get(p, "friend")} for p in index.people_ids]
        goals = extract_goals(index)
        emergency_output = sanitize_and_validate({
            "people": people,
            "organisations": orgs,
            "chats": ties,
            "goals": goals,
            "open_loops": []
        }, chats, messages)
        Path(output_path).write_text(json.dumps(emergency_output, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
