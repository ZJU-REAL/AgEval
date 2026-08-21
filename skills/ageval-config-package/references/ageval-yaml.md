# Field catalog

Formats: `ageval.dataset/1`, `ageval.task/1`, `ageval.profiles/1`. Unknown format → `invalid_format` at `/format`.

Dataset root keys: `format`, `dataset_id`, `version`, `description`, `tasks`. No `database_id`.

Task: `format`, `task_id`, `parameters`, `agent_profiles` (role ids only), `limits`, `artifacts`, `evaluation`, `provenance`, `requires`. Files present (`run.py`, `evaluator.py`, Dockerfile, `setup.sh`) are recognized. No `harness:` block, no `provider.kind`, no `assurance`.

Profiles: `format`, `environment`, `environment_options`, `agent_profiles`. Role rows may have `executor`, `model`, `api_key` (locator), `options.entry`, `extensions`.

`api_key: ${ENV}` is a locator name. Value never enters lock.

`--set` allowlist lives in Config Core, not here.
