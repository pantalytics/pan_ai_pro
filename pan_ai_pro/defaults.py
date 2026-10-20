"""The defaults Settings shows and the code falls back on, in one place."""

DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"
RUNS_PER_USER_PER_HOUR = 30
RETENTION_DAYS = 90
# Seconds per run, across slices (pan_ai.agent.time_limit).
TIME_LIMIT = 300
