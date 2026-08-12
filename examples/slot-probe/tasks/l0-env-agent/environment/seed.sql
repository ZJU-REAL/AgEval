-- minimal seed for env prepare path
CREATE TABLE IF NOT EXISTS probe_smoke (
  id INT PRIMARY KEY,
  label TEXT NOT NULL
);
INSERT INTO probe_smoke (id, label) VALUES (1, 'slot-probe-l0')
ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label;
