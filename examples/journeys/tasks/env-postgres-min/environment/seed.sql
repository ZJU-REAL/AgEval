-- Package-local seed (not Core-owned). Minimal smoke table for this package.
CREATE TABLE IF NOT EXISTS smoke (id INT PRIMARY KEY, label TEXT);
INSERT INTO smoke(id, label) VALUES (1, 'ageval') ON CONFLICT DO NOTHING;
