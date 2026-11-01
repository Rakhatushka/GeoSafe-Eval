# GeoSafe-Eval

Independent exploratory research on evidence-sensitive decisions by AI agents in geospatial tasks.

**Status: exploratory pilot. Independent validation and broader evaluation remain in progress.** This is a selected research snapshot, not a validated benchmark or a model leaderboard.

## Research question

Can an AI agent distinguish sufficient evidence (ANSWER), a recoverable information gap (INVESTIGATE), unavailable evidence (ABSTAIN), and a decision requiring human authority (ESCALATE)?

## Included materials

- `model_tasks.json`: ten synthetic Russian-language text tasks (v2); each contains only an ID and model-facing prompt.
- `run_eval.py`: independent OpenRouter requests, offline by default; live mode requires an environment-variable credential.
- `grade_run.py`: historical local scorer, with separate strict-format and content assessment. The author scoring key is excluded from this snapshot, so historical scores cannot be independently reproduced from this release alone.
- `geospatial_tool_environment/`: GIS tools, agent loop, API transport, synthetic raster generators, fixtures and existing local tests. Historical variants ending in `_v1` are retained as implementation history, not separate evidence of model performance.
- Public `reference_answers.json` files for the synthetic GIS software checks (author-defined, not independently validated). These contain expected outcomes, not API credentials.
- Synthetic GeoTIFF/GeoJSON fixtures for compatibility, region-specific NoData, coverage and recoverable-data experiments.

## Preliminary work and limitations

Local records contain preliminary text-only API experiments and model-driven GIS episodes. Text tasks describe available information and authority; they do not demonstrate execution of GIS operations. In the GIS prototype, host code executes permitted operations requested by the model. Tool safeguards contribute to system behavior; results do not isolate model ability.

The four original GIS fixtures use tiny 4-by-4 synthetic rasters: compatible inputs, mismatched grids, missing population inside the region, and missing population outside the region. Additional controlled pairs explore recovery and coverage. Scripted demonstrations and mocked API tests are software checks, not model results.

Small author-designed task sets, explicit task cues, ceiling effects, changes after pilot inspection, selective diagnostic reruns, and lack of independent scoring validation limit interpretation. The research does not establish general GIS competence, broad model rankings, prompt-injection robustness, or safety of real decisions. Human-authority scenarios in the text tasks do not constitute a deployed approval workflow.

Raw API logs and quantitative historical result tables are intentionally outside this initial snapshot pending release review. No new model experiment was run to prepare this release.

## Local use

Python 3.10+ is required. The text runner uses the standard library. GIS tools require the direct dependencies in `requirements.txt`; these are not a complete GDAL/PROJ platform lock.

```sh
python -m pip install -r requirements.txt
python run_eval.py --limit 1 --output runs/offline-preview
python -m unittest discover -s geospatial_tool_environment -p "test_*.py"
python geospatial_tool_environment/demo.py
```

The preview, local tests and demo require no model API requests. The demo creates local output. Choose a fresh preview output directory on each run. Existing fixtures are included; generators refuse to overwrite existing destinations.

Live API use is optional, incurs provider charges and is not necessary to inspect this project. Review `python run_eval.py --help`, provider configuration and output handling before using it. Never put credentials in source code, configuration files or commits. Historical provider/model settings are not a guarantee of current endpoint availability.

## Data and release scope

The supplied GIS fixtures are synthetic, not observations of real people or real programme locations. This snapshot excludes the original `private/` folders, API logs, experiment databases, local account notes, and the separate Somalia real-data feasibility experiment. It includes no IFAD/UNCCD source datasets or internal reports. GeoSafe-Eval is independent research; no institutional endorsement is claimed.

This release exposes synthetic tasks and fixture behavior. They should not be treated as a secret held-out evaluation set. An automated pattern scan complements file review but does not prove the absence of every possible sensitive detail.

## Next work

Independent task/key review; more discriminating controlled tasks; a documented attempt registry; explicit statistical analysis; broader model evaluation; and a separately reviewed release of reproducible pilot results.

Three historical registry integration tests are explicitly skipped: they require the excluded local experiment database. Other tests use local fixtures or mocked transports.
