-- Per-topic difficulty pin (parent override, persists across generations) and
-- hysteresis state (the difficulty band actually in effect, so day-to-day
-- success-rate noise near a threshold doesn't flip difficulty back and forth).
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS difficulty_pin TEXT
        CHECK (difficulty_pin IN ('simplified', 'maintained', 'increased')),
    ADD COLUMN IF NOT EXISTS current_adaptive_difficulty TEXT
        CHECK (current_adaptive_difficulty IN ('simplified', 'maintained', 'increased')),
    ADD COLUMN IF NOT EXISTS difficulty_changed_at DATE;
