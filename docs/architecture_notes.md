# Architecture notes

## Package boundaries

`bootstrap.py` creates the application context: configuration and the task
registry. `PlayerWindow` is a small Qt shell whose feature controllers own the
widgets, state and actions. It has no feature mixin inheritance or forwarded
state properties.

| Package | Responsibility |
| --- | --- |
| `configuration` | Ten immutable settings sections, environment defaults and persisted schema |
| `domain` | Scheduling, timeline values, deduplication and pure policy |
| `application` | Workflow engines, dependency contracts, jobs and atomic speech publication |
| `adapters` | Provider SDKs, media tools, storage, sources and Qt execution |
| `runtime` | Model definitions, runtime profiles, diagnostics, health and warmup |
| `ui/features` | Composed controllers and their explicit state ownership |
| `ui/views` | Builders for toolbars, panels, settings sections and final assembly |
| `workers` | Thin Qt wrappers declaring workflow type, dependency factory and signals |
| `core` | Shared logging, language, redaction and small utilities |

Domain and application modules must not import Qt, inference frameworks, UI or
adapter implementations. `tests/test_architecture.py` checks these boundaries
and imports every workflow without loading Qt, Torch or Transformers.

## Workflow execution

The realtime, export, document, meeting and source workflows are ordinary Python
objects. They receive frozen dependency records from
`adapters/workflow_bindings.py`; tests can replace these with controlled fakes.
Provider and platform selection belongs in those bindings, not in the engines.

`adapters/qt/workflow_thread.py` runs an engine in a QThread and queues events
back to the UI. Each run has a generation identifier. Events from a replaced
run are discarded when delivered, and completion is recorded after the thread
stops. Source workflows retain their path-and-error signal contract.

The application JobManager owns cancellation tokens, progress and terminal
status. Active jobs remain registered; terminal history is bounded. Closing the
window requests cancellation and keeps the Qt event loop alive until workers
stop. Task Center combines registry entries with native media-process status.

`application/speech.py` writes synthesis to a temporary sibling file, checks
cancellation and output, then publishes with atomic replacement. Failure or
cancellation preserves any existing output.

## UI composition

`ui/features/context.py` constructs explicit feature controllers.
`ui/features/initialize.py` wires them into the window. Controllers access
their owning feature directly, for example media playback/document state,
transcript state, runtime state and lifecycle worker references.

The context's named binding table supports dynamic widget names used by settings
and catalogue controls. It is not a catch-all forwarding interface on the
window. Add explicit ownership for new state. Pure UI helper functions remain
separate from widget controllers.

The former monolithic UI builder is divided among `ui/views`. Each builder
creates one functional area; `SettingsSections` carries the resulting layouts
to the final assembly step.

## Configuration and storage

AppConfig assembles ten dataclass sections. Existing flat constructor names,
environment mappings and saved field names remain stable; consumers can take
immutable section snapshots such as `config.tts`.

Settings schema 1 accepts unversioned settings as schema 0. A save refuses a
future schema before modifying any split settings files. Each file is written
through a temporary file, flushed and atomically replaced. Existing separate
secret and local-runtime stores remain in use; the collection of files is not
a single transactional database.

ArtifactCache leases protect active TTS files from in-process pruning. Unused
entries are limited by age and total size. Publication is atomic, and keys
include the pinned VieNeu SDK, model and codec revisions. Leases are local to
one process; they do not coordinate independent application instances.

## VieNeu v3 Turbo runtime

VieNeu runs in its dedicated Python environment. CPU ONNX and GPU PyTorch use
the same v3 Turbo bundle; no earlier model version is an execution fallback.
The SDK profile records its package version, patch revision and hashes of
patched modules. Startup checks the profile and the local model bundle.

The external interpreter cannot import modules stored only in PyInstaller's
archive. `scripts/vieneu_runtime_sources.json` therefore lists the small raw
source subset copied by both the spec and portable builder. A test imports
this subset outside the checkout. The offline verification script also accepts
`--source-root` to exercise the packaged source with sockets denied and an
empty temporary Hugging Face cache.

The Windows build resolves native libraries from its Python environment and
Windows directories. An inherited PATH from unrelated desktop tools can select
an incompatible ICU DLL and prevent QtGui from loading; the spec removes those
directories from dependency discovery.

Legacy model directories left on this workstation are not included in packages
or selected by runtime code. Their previously requested permanent deletion was
blocked by automatic approval review; restructuring does not retry that action.

## Verification and dependencies

Run `python -m pytest` for the complete suite, `python -m pytest -m fast` for
quick feedback, and `python -m ruff check .` for static checks. CI separates fast
and native tests and builds and launches the Windows package. Model inference
checks run locally with the prepared model bundle and dedicated runtime.

`pyproject.toml` defines dependency groups. A test keeps the convenience
`requirements.txt` profile equal to the base and offline-ai groups. Release
constraints and the isolated VieNeu requirements remain separate because the
host and TTS SDK require different inference dependencies.

See `restructure_status.md` for the implementation and validation record, and
`test_coverage_map.md` for the workflow test inventory.
