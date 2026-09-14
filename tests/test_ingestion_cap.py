"""
Unit tests for compute_batch_size() -- the one piece of the scheduled
ingestion pipeline that actually matters to get right without a database:
it's the thing standing between "passive ingestion" and "silently blew past
the 3,000-patient cap on Supabase's free tier."

No DB, no network -- this is exactly why the function was pulled out of
check_ingestion_cap.py's main() in the first place.
"""
from scripts.check_ingestion_cap import compute_batch_size, MIN_BATCH, MAX_BATCH


def test_cap_already_reached_returns_zero():
    assert compute_batch_size(current_count=3000, cap=3000) == 0


def test_cap_already_exceeded_returns_zero():
    # Shouldn't happen in practice (the cap can't be overshot if this
    # function is doing its job), but a stray manual insert could put the
    # count above cap -- this must still resolve to "do nothing," not a
    # negative batch size.
    assert compute_batch_size(current_count=3050, cap=3000) == 0


def test_small_headroom_clamps_below_min_batch():
    # Only 40 patients of headroom left, well under MIN_BATCH (100) --
    # the run must take exactly what's left, never overshoot the cap.
    assert compute_batch_size(current_count=2960, cap=3000) == 40


def test_headroom_of_zero_is_zero_not_negative():
    assert compute_batch_size(current_count=3000, cap=3000) == 0


def test_plenty_of_headroom_stays_within_normal_batch_range():
    # Comfortably more headroom than MAX_BATCH -- result should be an
    # ordinary random draw, never clamped.
    for _ in range(50):
        batch = compute_batch_size(current_count=0, cap=3000)
        assert MIN_BATCH <= batch <= MAX_BATCH


def test_never_exceeds_remaining_headroom_regardless_of_random_draw(monkeypatch):
    # Force the random draw to its maximum and confirm clamping still wins
    # when headroom is smaller than that draw.
    monkeypatch.setattr(
        "scripts.check_ingestion_cap.random.randint", lambda a, b: MAX_BATCH
    )
    assert compute_batch_size(current_count=2950, cap=3000) == 50
