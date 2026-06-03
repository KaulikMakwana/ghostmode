"""Instagram data categories and their deletion mechanism.

The "Your Activity" hub (instagram.com/your_activity/...) is IG's closest analog to
Google's My Activity: a bulk Select -> tick -> Delete/Unlike flow. URLs verified
current as of 2026-05; if IG moves them, fix here only.
"""
BASE = "https://www.instagram.com"

SERVICES = [
    {
        "name": "Comments",
        "category": "Interactions",
        "url": f"{BASE}/your_activity/interactions/comments/",
        "delete_type": "ig_bulk",
        "action": "Delete",
    },
    {
        "name": "Likes",
        "category": "Interactions",
        "url": f"{BASE}/your_activity/interactions/likes/",
        "delete_type": "ig_bulk",
        "action": "Unlike",  # the action button on the likes page says "Unlike"
    },
    {
        "name": "Story Replies",
        "category": "Interactions",
        "url": f"{BASE}/your_activity/interactions/story_replies/",
        "delete_type": "ig_bulk",
        "action": "Delete",
    },
    {
        "name": "Posts & Media",
        "category": "Content",
        "url": f"{BASE}/your_activity/photos_and_videos/",
        "delete_type": "ig_bulk",
        "action": "Delete",
    },
    # Phase 2 / 3 (deferred — defined so the dashboard can show them):
    {
        "name": "Direct Messages",
        "category": "Messages",
        "url": f"{BASE}/direct/inbox/",
        "delete_type": "ig_dms",        # per-thread, best-effort (Phase 2)
    },
    {
        "name": "Delete Account",
        "category": "Account",
        "url": f"{BASE}/accounts/remove/request/permanent/",
        "delete_type": "ig_account",    # gated one-shot (Phase 3)
    },
]


def get_by_category() -> dict:
    out = {}
    for s in SERVICES:
        out.setdefault(s["category"], []).append(s)
    return out
