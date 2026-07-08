-- RewardHub + IEP worksheet schema (idempotent)
-- Safe to run multiple times on the shared Supabase project.

CREATE TABLE IF NOT EXISTS chore_app_state (
    app_name TEXT PRIMARY KEY,
    app_data JSONB DEFAULT '{}'::jsonb
);

INSERT INTO chore_app_state (app_name, app_data)
SELECT 'GuhanApp', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM chore_app_state WHERE app_name = 'GuhanApp'
);

ALTER TABLE chore_app_state ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'chore_app_state' AND policyname = 'chore_app_state_anon_rw'
    ) THEN
        CREATE POLICY "chore_app_state_anon_rw"
        ON chore_app_state FOR ALL TO anon
        USING (true) WITH CHECK (true);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id TEXT NOT NULL DEFAULT 'guhan',
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- If tasks existed from a prior partial run without UNIQUE, add it now.
CREATE UNIQUE INDEX IF NOT EXISTS tasks_student_subject_topic_uidx
    ON tasks (student_id, subject, topic);

CREATE TABLE IF NOT EXISTS daily_generated_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id TEXT NOT NULL DEFAULT 'guhan',
    question_date DATE NOT NULL DEFAULT (CURRENT_DATE AT TIME ZONE 'America/New_York')::date,
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    difficulty_level TEXT NOT NULL CHECK (difficulty_level IN ('simplified', 'maintained', 'increased')),
    question_text TEXT NOT NULL,
    scaffolding_hints JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_answer TEXT NOT NULL,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    source_prompt_version TEXT,
    is_assigned_as_chore BOOLEAN NOT NULL DEFAULT false,
    chore_task_id BIGINT,
    worksheet_set INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS worksheet_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id TEXT NOT NULL DEFAULT 'guhan',
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    question_id UUID REFERENCES daily_generated_questions(id) ON DELETE SET NULL,
    question_text TEXT,
    student_answer TEXT,
    expected_answer TEXT,
    is_correct BOOLEAN,
    score NUMERIC(5, 2) CHECK (score >= 0 AND score <= 100),
    entry_date DATE NOT NULL DEFAULT (CURRENT_DATE AT TIME ZONE 'America/New_York')::date,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_worksheet_entries_student_date
    ON worksheet_entries (student_id, entry_date DESC);

CREATE INDEX IF NOT EXISTS idx_worksheet_entries_topic_date
    ON worksheet_entries (student_id, topic, entry_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_questions_student_date
    ON daily_generated_questions (student_id, question_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_questions_subject_date
    ON daily_generated_questions (student_id, subject, question_date DESC);

INSERT INTO tasks (student_id, subject, topic, description)
SELECT v.student_id, v.subject, v.topic, v.description
FROM (
    VALUES
        ('guhan', 'Math', 'calculating area', 'Area of rectangles and triangles with explicit formulas'),
        ('guhan', 'Math', 'unit price', 'Find cost per item using division; literal word problems'),
        ('guhan', 'Reading', 'identifying theme', 'State the main idea or theme in simple, literal language')
) AS v(student_id, subject, topic, description)
WHERE NOT EXISTS (
    SELECT 1
    FROM tasks t
    WHERE t.student_id = v.student_id
      AND t.subject = v.subject
      AND t.topic = v.topic
);

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE worksheet_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_generated_questions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'tasks' AND policyname = 'tasks_anon_rw') THEN
        CREATE POLICY "tasks_anon_rw" ON tasks FOR ALL TO anon USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'worksheet_entries' AND policyname = 'worksheet_entries_anon_rw') THEN
        CREATE POLICY "worksheet_entries_anon_rw" ON worksheet_entries FOR ALL TO anon USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'daily_generated_questions' AND policyname = 'daily_generated_questions_anon_rw') THEN
        CREATE POLICY "daily_generated_questions_anon_rw" ON daily_generated_questions FOR ALL TO anon USING (true) WITH CHECK (true);
    END IF;
END $$;
