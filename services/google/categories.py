"""
All Google My Activity service definitions.
Each entry: name, url, category, delete_type, extra params.
"""

BASE = "https://myactivity.google.com"

# Delete types:
#   per_item        - X buttons, infinite scroll
#   per_item_lm     - X buttons + Load More
#   delete_all_btn  - single "Delete All" button on page
#   service_delete  - service-level Delete button (bulk)
#   yt_history      - YouTube History tab + DELETE
#   inline          - Delete button on more-activity page
#   play_toggles    - toggle switches + Load More
#   external        - link out, user handles manually
#   nuclear         - Delete → Always on main page

SERVICES = [
    # ── Nuclear ────────────────────────────────────────────────────────────
    {
        "name": "Nuclear Delete (All Activity)",
        "url": f"{BASE}/myactivity",
        "category": "Nuclear",
        "delete_type": "nuclear",
    },

    # ── YouTube Watch/Search History ───────────────────────────────────────
    {
        # /product/youtube has per-item X buttons too, but the efficient path is
        # DELETE → "Delete all time" which wipes ALL history in one operation
        # (vs 100s of per-item clicks). Scan still counts visible X buttons.
        "name": "YouTube Watch & Search History",
        "url": f"{BASE}/product/youtube",
        "category": "YouTube",
        "delete_type": "yt_history",
    },

    # ── YouTube per-item (infinite scroll) ────────────────────────────────
    {
        "name": "YouTube Comments",
        "url": f"{BASE}/page?page=youtube_comments",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Live Chat Messages",
        "url": f"{BASE}/page?page=youtube_live_chat",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Liked Videos",
        "url": f"{BASE}/page?page=youtube_likes",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        # Subscriptions are managed on YouTube (/feed/channels), not My Activity —
        # there are no "Delete activity item" X buttons. Handled via per-channel pick.
        "name": "YouTube Subscriptions",
        "url": "https://www.youtube.com/feed/channels",
        "category": "YouTube",
        "delete_type": "subscriptions",
    },
    {
        "name": "YouTube User Feedback",
        "url": f"{BASE}/page?page=youtube_user_feedback",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Sharing Activity",
        "url": f"{BASE}/page?page=youtube_sharing_activity",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Other Video Interactions",
        "url": f"{BASE}/page?page=youtube_video_other_activity",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube AI Creation",
        "url": f"{BASE}/page?page=youtube_gen_ai_creation",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube AI Feedback",
        "url": f"{BASE}/page?page=youtube_gen_ai_user_feedback",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Hype Activity",
        "url": f"{BASE}/page?page=youtube_video_hype",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Purchases",
        "url": f"{BASE}/page?page=youtube_commerce_acquisitions",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Gift Settings",
        "url": f"{BASE}/page?page=youtube_gift_settings",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Playables Progress",
        "url": f"{BASE}/page?page=youtube_miniapp_cloud_saves",
        "category": "YouTube",
        "delete_type": "per_item",
    },
    {
        "name": "YouTube Playables Scores",
        "url": f"{BASE}/page?page=youtube_miniapp_stats",
        "category": "YouTube",
        "delete_type": "per_item",
    },

    # ── YouTube Load More ──────────────────────────────────────────────────
    {
        "name": "YouTube Comment Likes/Dislikes",
        "url": f"{BASE}/page?page=youtube_comment_likes",
        "category": "YouTube",
        "delete_type": "per_item_lm",
    },

    # ── YouTube Delete All button ──────────────────────────────────────────
    {
        # Verified live: this page has per-item "Delete activity item" X buttons +
        # date-header buttons, NO "Delete All" button. It is a per_item page.
        "name": "YouTube Community Posts",
        "url": f"{BASE}/page?page=youtube_posts_activity",
        "category": "YouTube",
        "delete_type": "per_item",
    },

    # ── Search & Discover ──────────────────────────────────────────────────
    {
        "name": "Search Comments",
        "url": f"{BASE}/page?page=search_comments",
        "category": "Search",
        "delete_type": "per_item_lm",
    },
    {
        "name": "Media Likes on Search",
        "url": f"{BASE}/page?page=media_reaction_thumbs_on_search",
        "category": "Search",
        "delete_type": "per_item",
    },
    {
        "name": "Media Likes on Google TV",
        "url": f"{BASE}/page?page=media_reaction_thumbs_on_gtv",
        "category": "Search",
        "delete_type": "per_item",
    },
    {
        "name": "Search Text Reviews",
        "url": f"{BASE}/page?page=search_media_text_reviews",
        "category": "Search",
        "delete_type": "per_item",
    },
    {
        "name": "Discover Feed Topics",
        "url": f"{BASE}/page?page=customize_your_feed_activity_on_discover",
        "category": "Search",
        "delete_type": "per_item",
    },

    # ── Chrome ─────────────────────────────────────────────────────────────
    {
        "name": "Chrome History",
        "url": f"{BASE}/page?page=chrome",
        "category": "Chrome",
        "delete_type": "per_item",
    },
    {
        "name": "Chrome Shared Tab Groups",
        "url": f"{BASE}/page?page=chrome_shared_tab_group_activity",
        "category": "Chrome",
        "delete_type": "per_item",
    },
    {
        "name": "Chrome Recall Sharing",
        "url": f"{BASE}/page?page=recall_sharing",
        "category": "Chrome",
        "delete_type": "per_item",
    },

    # ── Google Play ────────────────────────────────────────────────────────
    {
        "name": "Play App Metadata Toggles",
        "url": f"{BASE}/product/google_play/playlibrary",
        "category": "Google Play",
        "delete_type": "play_toggles",
    },
    {
        "name": "Play Books Feedback",
        "url": f"{BASE}/page?page=play_books",
        "category": "Google Play",
        "delete_type": "per_item",
    },
    {
        "name": "Play Data Projection",
        "url": f"{BASE}/page?page=play_data_projection",
        "category": "Google Play",
        "delete_type": "per_item",
    },
    {
        "name": "Play Games Activity",
        "url": f"{BASE}/product/google_play?product=45",
        "category": "Google Play",
        "delete_type": "service_delete",
        "button_text": "Delete these results",
    },

    # ── Assistant / Home ───────────────────────────────────────────────────
    {
        "name": "Assistant Memory",
        "url": f"{BASE}/page?page=assistant_memory",
        "category": "Assistant",
        "delete_type": "per_item",
    },
    {
        "name": "Ask Advisor Chat History",
        "url": f"{BASE}/page?page=ask_advisor_chat",
        "category": "Assistant",
        "delete_type": "per_item",
    },
    {
        "name": "Help Guide Chat History",
        "url": f"{BASE}/page?page=gse_help_guide_chat",
        "category": "Assistant",
        "delete_type": "per_item",
    },
    {
        "name": "Google Home History",
        "url": f"{BASE}/product/home",
        "category": "Assistant",
        "delete_type": "service_delete",
        "button_text": "Delete",
    },

    # ── Gemini ─────────────────────────────────────────────────────────────
    {
        "name": "Gemini Activity",
        "url": f"{BASE}/product/gemini",
        "category": "Gemini",
        "delete_type": "service_delete",
        "button_text": "Delete",
    },

    # ── Photos / Workspace ─────────────────────────────────────────────────
    {
        "name": "Google Photos Activity",
        "url": f"{BASE}/product/photos",
        "category": "Google",
        "delete_type": "service_delete",
        "button_text": "Delete",
    },
    {
        "name": "Google Workspace History",
        "url": f"{BASE}/product/workspace",
        "category": "Google",
        "delete_type": "service_delete",
        "button_text": "Delete",
    },

    # ── Shopping ───────────────────────────────────────────────────────────
    {
        "name": "Shopping & Price Tracking",
        "url": f"{BASE}/search-services/history/shopping",
        "category": "Search",
        "delete_type": "service_delete",
        "button_text": "Delete",
    },

    # ── Voice/Face Match ───────────────────────────────────────────────────
    {
        "name": "Voice & Face Match Enrolment",
        "url": f"{BASE}/page?page=match_enrollment",
        "category": "Google",
        "delete_type": "delete_all_btn",
        # Prefix only: Google localises this as "enrolments" (UK) / "enrollments"
        # (US). click_delete_all matches by startsWith, so this catches both.
        "button_text": "Delete all enrol",
    },

    # ── Various per-item ───────────────────────────────────────────────────
    {
        "name": "News Preferences",
        "url": f"{BASE}/page?page=news_preferences",
        "category": "Google",
        "delete_type": "per_item",
    },
    {
        "name": "Crowdsource Activity",
        "url": f"{BASE}/page?page=crowdsource",
        "category": "Google",
        "delete_type": "per_item",
    },
    {
        "name": "Portrait Activity",
        "url": f"{BASE}/page?page=portrait",
        "category": "Google",
        "delete_type": "per_item",
    },
    {
        "name": "Google Survey Answers",
        "url": f"{BASE}/page?page=product_surveys",
        "category": "Google",
        "delete_type": "per_item",
    },
    {
        "name": "My Ad Centre Preferences",
        "url": f"{BASE}/page?page=my_ad_center_preferences",
        "category": "Google",
        "delete_type": "per_item",
    },
    {
        "name": "Data Archive History",
        "url": f"{BASE}/page?page=takeout",
        "category": "Google",
        "delete_type": "per_item",
    },

    # ── Inline (more-activity page Delete buttons) ─────────────────────────
    {
        "name": "YouTube Survey Answers",
        "url": f"{BASE}/more-activity",
        "category": "YouTube",
        "delete_type": "inline",
        "inline_label": "YouTube survey answers",
    },
    {
        "name": "YouTube Feed Feedback",
        "url": f"{BASE}/more-activity",
        "category": "YouTube",
        "delete_type": "inline",
        "inline_label": "YouTube customise your feed feedback",
    },
    {
        "name": "Google Word Coach",
        "url": f"{BASE}/more-activity",
        "category": "Search",
        "delete_type": "inline",
        "inline_label": "Google Word Coach",
    },
    {
        "name": "Interests & Notifications",
        "url": f"{BASE}/more-activity",
        "category": "Google",
        "delete_type": "inline",
        "inline_label": "Your interests and notifications",
    },
    {
        "name": "Exam Quiz Activity",
        "url": f"{BASE}/more-activity",
        "category": "Google",
        "delete_type": "inline",
        "inline_label": "Government exam quiz activity",
    },
    {
        "name": "Translate Language Selections",
        "url": f"{BASE}/more-activity",
        "category": "Google",
        "delete_type": "inline",
        "inline_label": "Translate language selections",
    },
    {
        "name": "Dictionary & Pronunciation Info",
        "url": f"{BASE}/more-activity",
        "category": "Google",
        "delete_type": "inline",
        "inline_label": "Dictionary and pronunciation search info",
    },
    {
        "name": "Promo Activity",
        "url": f"{BASE}/more-activity",
        "category": "Google",
        "delete_type": "inline",
        "inline_label": "Promo activity",
    },
    {
        "name": "Product Price Tracking",
        "url": f"{BASE}/more-activity",
        "category": "Google",
        "delete_type": "inline",
        "inline_label": "Product price tracking",
    },
    {
        "name": "Place Suggested Answers",
        "url": f"{BASE}/more-activity",
        "category": "Google",
        "delete_type": "inline",
        "inline_label": "Place suggested answers feedback",
    },

    # ── External (user handles, tool notifies) ────────────────────────────
    {
        "name": "Google Pay (2FA required)",
        "url": f"{BASE}/product/gpay",
        "category": "External",
        "delete_type": "external",
        "note": "Requires 2FA — handle manually in browser",
    },
    {
        "name": "Results About You",
        "url": f"{BASE}/results-about-you",
        "category": "External",
        "delete_type": "external",
        "note": "Separate removal flow",
    },
    {
        "name": "Purchases & Reservations",
        "url": "https://myaccount.google.com/purchases",
        "category": "External",
        "delete_type": "external",
        "note": "External — manage at myaccount.google.com",
    },
]


def get_by_category() -> dict:
    """Return services grouped by category."""
    result = {}
    for s in SERVICES:
        cat = s["category"]
        result.setdefault(cat, []).append(s)
    return result


def get_by_name(name: str) -> dict | None:
    return next((s for s in SERVICES if s["name"] == name), None)


def all_names() -> list:
    return [s["name"] for s in SERVICES]
