from __future__ import annotations

import argparse
import string
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_player.core.cli_encoding import prefer_utf8_stdio  # noqa: E402
from ai_player.core.config import LOCAL_WHISPER_MODEL_PATH  # noqa: E402
from ai_player.services.whisper_runtime import clear_shared_whisper_models, get_shared_whisper_model  # noqa: E402


def main() -> int:
    prefer_utf8_stdio(sys.stdout, sys.stderr)
    args = _parse_args()
    samples = _sample_paths(args.samples)
    if not samples:
        print(f"No WAV samples found in {args.samples}")
        return 2

    clear_shared_whisper_models()
    model = get_shared_whisper_model(
        args.model,
        device=args.device,
        compute_type=args.compute,
        local_files_only=args.offline,
    )

    total_words = 0
    total_edits = 0
    for sample in samples:
        expected_path = sample.with_suffix(".txt")
        if not expected_path.exists():
            continue
        expected = expected_path.read_text(encoding="utf-8").strip()
        segments, info = model.transcribe(
            str(sample),
            beam_size=args.beam_size,
            vad_filter=not args.no_vad,
            language=args.language or None,
        )
        predicted = " ".join((getattr(segment, "text", "") or "").strip() for segment in segments).strip()
        expected_words = _normalize_words(expected)
        predicted_words = _normalize_words(predicted)
        edits = _levenshtein(expected_words, predicted_words)
        total_words += len(expected_words)
        total_edits += edits
        wer = edits / max(1, len(expected_words))
        language = getattr(info, "language", "?")
        probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        print(f"{sample.name}: WER={wer:.2%} language={language} prob={probability:.3f}")
        if args.show_text:
            print(f"  expected: {expected}")
            print(f"  actual:   {predicted}")

    total_wer = total_edits / max(1, total_words)
    print(f"TOTAL: words={total_words} edits={total_edits} WER={total_wer:.2%}")
    if args.max_wer is not None and total_wer > args.max_wer:
        print(f"WER {total_wer:.2%} exceeds threshold {args.max_wer:.2%}")
        return 1
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small Faster Whisper ASR regression pass.")
    parser.add_argument(
        "--samples",
        default=str(Path("ai_player") / "vieneu_tts" / "vieneu" / "assets" / "samples"),
        help="Folder containing .wav samples with matching .txt references.",
    )
    parser.add_argument("--model", default=LOCAL_WHISPER_MODEL_PATH)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute", default="int8")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--language", default="vi")
    parser.add_argument("--offline", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-vad", action="store_true")
    parser.add_argument("--show-text", action="store_true")
    parser.add_argument("--max-wer", type=float, default=None, help="Optional failing threshold, e.g. 0.30.")
    return parser.parse_args()


def _sample_paths(value: str) -> list[Path]:
    path = Path(value)
    if path.is_file():
        return [path]
    return sorted(path.glob("*.wav"))


def _normalize_words(text: str) -> list[str]:
    punctuation = str.maketrans("", "", string.punctuation)
    return text.lower().translate(punctuation).split()


def _levenshtein(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for index, left_word in enumerate(left, 1):
        current = [index]
        for right_index, right_word in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_word != right_word),
                )
            )
        previous = current
    return previous[-1]


if __name__ == "__main__":
    raise SystemExit(main())
