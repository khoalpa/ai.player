"""Composition root for an application session.

Providers are imported here or by adapter factories, never by domain models.
Each window has an independent task registry and immutable initial settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai_player.adapters.storage.settings_store import load_app_config
from ai_player.application.jobs import JobManager
from ai_player.configuration import AppConfig


@dataclass
class ApplicationContext:
    config: AppConfig
    jobs: JobManager = field(default_factory=JobManager)


def create_application_context(config: AppConfig | None = None) -> ApplicationContext:
    return ApplicationContext(config if config is not None else load_app_config(AppConfig.from_env()))
