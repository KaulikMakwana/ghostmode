from pathlib import Path

CDP_PORT = 9222
CDP_HOST = "localhost"
CHROMIUM_BIN = "/usr/lib/chromium/chromium"
PROFILES_DIR = Path.home() / ".ghostmode" / "profiles"
STATE_FILE = Path.home() / ".ghostmode" / "active_browser.json"  # which profile owns CDP_PORT
PASSWORD_FILE = Path.home() / "Desktop" / "password"
WS_PING_INTERVAL = 20
WS_PING_TIMEOUT = 30
WS_MAX_SIZE = 20_000_000
AUTH_COOLDOWN = 30        # seconds between auto-auth attempts
AUTH_2FA_TIMEOUT = 300    # seconds to wait for user to complete 2FA
CLICK_DELAY = 0.15        # seconds between item clicks
BATCH_SETTLE = 0.5        # seconds after batch before re-checking
SCROLL_STEPS = 6          # increments per scroll cycle
SCROLL_STEP_PX = 1500
LOAD_MORE_WAIT = 3.0
RECONNECT_WAIT = 5

# Instagram — deliberately SLOW, ban-averse pacing (the account must survive).
# Speed is not the goal; avoiding action-blocks is.
IG_BATCH_SIZE = 50           # selects ALL rendered tiles up to this (IG paginates ~27)
IG_TICK_DELAY = 0.12         # seconds between checkbox ticks
IG_ACTION_DELAY = 1.0        # seconds between major actions (Select/Delete/confirm)
IG_POST_DELETE_WAIT = 2.0    # short settle after a delete; _wait_for_items/_settle_items
                             # already poll patiently for the next page, so this no longer
                             # needs the old 6s (that was dead time stacked on the poll)
IG_SELECT_RETRIES = 12       # attempts to find/enter the "Select" mode per round
IG_RELOAD_RETRIES = 3        # polls for the next batch before forcing a refresh. Comments
                             # NEVER render the next page in-place (always needs the refresh),
                             # so 6x5s=30s was dead time; 3x4s=12s refreshes sooner. SAFE: the
                             # post-refresh re-check is the authoritative empty test, unchanged.
IG_RELOAD_WAIT = 4.0         # seconds between those polls (Likes/Story Replies load <12s in-place)
IG_SETTLE_POLLS = 4          # polls to let the tile list finish lazy-streaming before ticking
IG_SETTLE_WAIT = 1.0         # seconds between settle polls; breaks early once the count
                             # plateaus, so a fast page costs ~1s, a slow one ~4s max
IG_RATELIMIT_BACKOFF = 45.0  # seconds to wait after a rate-limit modal
IG_RATELIMIT_MAX_HITS = 3    # HARD STOP after this many rate-limit modals in a run
IG_MAX_ACTIONS = 100000      # runaway backstop only; real stop = empty page / rate-limit
                             # (verified: 1026 unlikes/run with 0 throttle, so the old
                             #  1000 cap was the false "Done", not IG)
