-- Add worksheet round tracking (1 = required chore, 2+ = optional bonus)
ALTER TABLE daily_generated_questions
    ADD COLUMN IF NOT EXISTS worksheet_set INT NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_daily_questions_student_date_set
    ON daily_generated_questions (student_id, question_date, subject, worksheet_set);
