import sys


def main() -> int:
    if "--demucs-runner" in sys.argv:
        sys.argv.remove("--demucs-runner")
        from ai_player.adapters.media.demucs_runner import main as demucs_runner_main

        return demucs_runner_main()

    from ai_player.app import main as application_main

    return application_main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback

        from ai_player.configuration import RUNTIME_DIR
        from ai_player.core.redaction import redact_secrets

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        (RUNTIME_DIR / "ai-player-startup-error.log").write_text(
            redact_secrets(traceback.format_exc()), encoding="utf-8"
        )
        raise
