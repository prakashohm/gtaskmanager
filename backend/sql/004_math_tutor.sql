-- Interactive math tutor rewrite: track hint usage, retire the Reading and
-- geometry topics, and seed foundational 9th-grade math skills.
ALTER TABLE worksheet_entries
    ADD COLUMN IF NOT EXISTS hint_count INT NOT NULL DEFAULT 0;

UPDATE tasks SET is_active = false
WHERE student_id = 'guhan' AND subject = 'Reading' AND topic = 'identifying theme';

UPDATE tasks SET is_active = false
WHERE student_id = 'guhan' AND subject = 'Math' AND topic = 'calculating area';

INSERT INTO tasks (student_id, subject, topic, description)
SELECT v.student_id, v.subject, v.topic, v.description
FROM (
    VALUES
        ('guhan', 'Math', 'arithmetic word problems', 'Whole-number and decimal +, -, x, / in real-world contexts'),
        ('guhan', 'Math', 'fractions', 'Add/subtract/multiply/divide and simplify fractions in word problems'),
        ('guhan', 'Math', 'percentages', 'Percent of a number, discounts, tips, percent increase/decrease'),
        ('guhan', 'Math', 'order of operations', 'Evaluate multi-step expressions (PEMDAS) framed as word problems'),
        ('guhan', 'Math', 'one-step equations', 'Solve for an unknown in a simple real-world equation')
) AS v(student_id, subject, topic, description)
WHERE NOT EXISTS (
    SELECT 1
    FROM tasks t
    WHERE t.student_id = v.student_id
      AND t.subject = v.subject
      AND t.topic = v.topic
);
