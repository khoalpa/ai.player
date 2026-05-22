import sys

from ai_player.app import main

if __name__ == "__main__":
    if "--demucs-runner" in sys.argv:
        sys.argv.remove("--demucs-runner")
        from ai_player.services.demucs_runner import main as demucs_runner_main

        raise SystemExit(demucs_runner_main())
    raise SystemExit(main())
