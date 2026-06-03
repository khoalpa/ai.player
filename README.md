# AI Player

AI Player là ứng dụng Windows dùng PySide6 để xem video, đọc tài liệu và tạo bản lồng tiếng gần thời gian thực bằng ASR, dịch máy, OCR và TTS. Mặc định dự án ưu tiên workflow offline: Faster Whisper cho nhận dạng giọng nói, NLLB cho dịch, VieNeu-TTS cho giọng đọc tiếng Việt và Tesseract cho OCR phụ đề cứng.

## Tính Năng Chính

- Mở video cục bộ, URL media trực tiếp hoặc trang video được `yt-dlp` hỗ trợ.
- Cache video URL theo chất lượng phát (`360p`, `480p`, `720p`, `1080p`, `best`) để xem và xử lý ổn định hơn.
- Nhận dạng lời thoại bằng `faster-whisper`, có VAD, chọn thiết bị `cpu`/`cuda`/`auto` và compute type.
- Dịch bằng NLLB CTranslate2 int8, NLLB local hoặc bỏ qua dịch khi chỉ cần đọc lại transcript gốc.
- Tạo giọng đọc bằng VieNeu-TTS nội bộ (`standard`/`turbo`, `subprocess`/`in-process`) hoặc Edge TTS.
- Chọn nguồn đầu vào: âm gốc, âm hệ thống, micro, hệ thống + micro, transcript, editor tài liệu hoặc OCR phụ đề cứng.
- Mở `.pptx`, `.docx`, `.pdf`, `.txt`, `.md`, `.rtf`, `.csv`, `.json`, trích nội dung thành transcript và phát như một timeline.
- Export audio `.wav`, video `.mp4` đã lồng tiếng, transcript và video review chất lượng cao cho tài liệu.
- Có Runtime Doctor trong CLI/UI để kiểm tra Python package, FFmpeg, Tesseract, GPU runtime, model/cache và thiết bị capture.
- Giao diện có gói ngôn ngữ `vi`/`en`, preset hiệu năng và tab quản lý model offline.

## Yêu Cầu

1. Windows 10/11.
2. Python 3.10+.
3. FFmpeg và ffplay trong `PATH`.
4. Tesseract OCR trong `PATH` nếu dùng nguồn `Subtitle`. App cũng tìm đường dẫn mặc định `C:\Program Files\Tesseract-OCR\tesseract.exe`.
5. LibreOffice nếu muốn render đúng ảnh gốc của `.pptx`/`.docx` trong khung tài liệu.
6. Internet cho lần đầu tải model hoặc khi dùng Edge TTS. Sau khi tải đủ model, các workflow offline có thể chạy không cần mạng.

## Cài Đặt

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,offline-ai]"
```

Nếu chỉ chạy app nhẹ, không cài model AI offline/GPU:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --profile lite
```

Nếu muốn runtime đầy đủ để build portable, GPU và tách giọng bằng Demucs:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging,offline-ai,gpu,audio-separation]"
```

Nếu chỉ muốn cài bằng requirements cho runtime AI CPU/offline cơ bản, có thể dùng:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Chuẩn Bị Runtime

Tải bộ model offline mặc định:

```powershell
.\scripts\download_offline_models.ps1
```

Các script tải riêng:

```powershell
.\scripts\download_whisper_model.ps1
.\scripts\download_translator_models.ps1
.\scripts\download_vieneu_tts_models.ps1
.\scripts\download_tessdata_models.ps1
.\scripts\download_speaker_gender_model.ps1
```

Kiểm tra nhanh môi trường:

```powershell
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py
```

Trong CI hoặc môi trường không cần liệt kê thiết bị audio:

```powershell
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci
```

## Dependency Audit

Trước khi chia sẻ build, chạy audit dependency theo `docs/dependency_audit.md`:

```powershell
.\scripts\audit_dependencies.ps1
```

## License

AI Player được phân phối theo giấy phép MIT. Xem `LICENSE`.

## Chạy App

```powershell
.\.venv\Scripts\python.exe main.py
```

Hoặc double-click:

```bat
open_app.bat
```

## Build Portable

```powershell
.\scripts\build_portable.ps1
```

Output được ghi vào `dist\portable\AI Player Lite`. Gói Lite không bundle thư mục `models\`, vì vậy cần tải hoặc copy model offline riêng nếu muốn chạy không cần mạng.

## Luồng Sử Dụng

1. Bấm `Mở file`, `Mở URL`, `Mở tài liệu` hoặc dùng tab editor/tác vụ meeting.
2. Chọn preset trong tab `Cơ bản`: `Quick preview`, `Offline lite`, `Balanced` hoặc `Quality / Export`.
3. Chọn nguồn audio/transcript, ngôn ngữ nguồn/đích, provider dịch và provider TTS.
4. Bấm `Lồng tiếng` để phát gần thời gian thực.
5. Bấm `Export` để xuất transcript, audio, video hoặc bản review chất lượng cao.

Trong app, bấm nút `?` để mở `Hướng dẫn sử dụng`. Hướng dẫn này tự đi theo ngôn ngữ giao diện và hiển thị cả cấu hình hiện tại để dễ biết thiết lập nào đang làm chậm hoặc ảnh hưởng chất lượng.

## Chọn Nhanh Theo Mục Tiêu

| Mục tiêu | Thiết lập nên bắt đầu | Ghi chú |
| --- | --- | --- |
| Xem nhanh | `Quick preview`, Edge TTS, bộ đệm thấp hoặc cân bằng | Phù hợp để kiểm tra nội dung trước; cần Internet cho Edge TTS. |
| Chạy offline | `Offline lite`, NLLB CTranslate2, VieNeu-TTS local | Nên dùng GPU nếu có; CPU vẫn chạy được nhưng đoạn đầu có thể lâu. |
| Đọc tài liệu | Nguồn `Editor`/tài liệu, giọng rõ, tắt dịch nếu chỉ cần đọc nguyên văn | Với file dài, chia nhỏ nội dung hoặc giảm max ký tự TTS nếu tạo giọng chậm. |
| Xuất bản | `Quality / Export`, tăng buffer/lookahead, kiểm tra transcript trước khi xuất | Chậm hơn nhưng giảm lỗi nhịp, lỗi dịch và lỗi âm thanh ở video cuối. |

## Sự Cố Thường Gặp

| Dấu hiệu | Cách thử trước |
| --- | --- |
| Nút Play chưa bật | Đợi đủ bộ đệm, giảm `Bộ đệm`, hoặc chuyển sang Edge TTS để tạo âm nhanh hơn. |
| Âm đích lệch nhịp | Bật `Tự khớp âm thanh`, tăng lookahead, hoặc giảm tốc độ/độ dài đoạn nếu giọng bị kéo dài. |
| URL web không mở | Bật cache video URL, giảm chất lượng phát, hoặc dùng URL media trực tiếp nếu có. |
| Dịch/đọc sai thuật ngữ | Bật giữ thuật ngữ và chọn file thuật ngữ; kiểm tra lại ngôn ngữ nguồn trước khi chạy. |
| App xử lý quá chậm | Tránh mở nhiều cửa sổ cùng lúc, dùng Edge TTS khi cần nhanh, hoặc giảm model/thiết lập local nặng trên CPU. |

## Nguồn Và Định Dạng Hỗ Trợ

Video cục bộ:

- `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`

URL media trực tiếp:

- `.mp4`, `.mkv`, `.mov`, `.webm`, `.avi`, `.m4v`, `.m3u8`, `.mpd`
- Protocol hợp lệ: `http`, `https`, `rtsp`, `rtmp`, `mms`

Trang video qua `yt-dlp`:

- YouTube, TikTok, Facebook, Instagram, Threads, X/Twitter, Vimeo, Dailymotion, public Telegram previews.
- Internal builds can install private `yt-dlp` plugin packages and declare their
  extra hosts with `AI_PLAYER_EXTRA_YTDLP_HOSTS`.
- Internal builds can also install a private Telegram client package for
  Telethon-backed login and authenticated Telegram downloads.
- YouTube channel and playlist URLs can be browsed in-app; internal builds can
  install `ai-player-youtube-client` for a dedicated YouTube adapter, otherwise
  AI Player uses the public YouTube page metadata fallback.

Tài liệu:

- PowerPoint: `.pptx`
- Word: `.docx`
- PDF: `.pdf`
- Text/Markdown/RTF: `.txt`, `.text`, `.md`, `.rtf`
- Data text: `.csv`, `.json`

Định dạng Office cũ `.doc` và `.ppt` chưa được hỗ trợ trực tiếp; hãy lưu lại thành `.docx` hoặc `.pptx`.

## Nguồn Đầu Vào

Dropdown `Nguồn` hỗ trợ:

- `Original`: lấy audio track đầu tiên của video.
- `System`: capture âm hệ thống bằng `soundcard`/WASAPI loopback, fallback qua FFmpeg DirectShow khi cần.
- `Microphone`: capture micro bằng `soundcard`, fallback DirectShow.
- `System + Microphone`: dùng cho meeting hoặc ghi đồng thời âm hệ thống và micro.
- `Transcript`: đọc `.srt`, `.vtt` hoặc `.txt`; nếu có timestamp, app phát theo timeline.
- `Editor`: biến nội dung nhập hoặc tài liệu đã mở thành timeline đọc.
- `Subtitle`: OCR phụ đề cứng ở vùng dưới video bằng Tesseract.

Chỉ định thiết bị capture bằng biến môi trường:

```powershell
$env:AI_PLAYER_CAPTURE_SYSTEM_DEVICE="Speakers"
$env:AI_PLAYER_CAPTURE_MICROPHONE_DEVICE="Microphone Array"
```

Liệt kê thiết bị DirectShow:

```powershell
ffmpeg -hide_banner -f dshow -list_devices true -i dummy
```

## Model Mặc Định

Các đường dẫn model mặc định nằm trong `models\`:

```text
models/asr/faster-whisper-base
models/translation/nllb-200-distilled-600M
models/translation/nllb-200-distilled-600M-ct2-int8
models/translation/nllb-200-1.3B
models/tts/vieneu/turbo
models/tts/vieneu/standard
models/ocr/tessdata
models/speaker_gender/common-voice-gender-detection
models/transcript_cleanup/Qwen2.5-3B-Instruct
```

Preset `Balanced` mặc định dùng Whisper base, NLLB CTranslate2 int8, VieNeu-TTS standard và target language `vi`.

## Cấu Hình Hữu Ích

```powershell
$env:AI_PLAYER_GUI_LANGUAGE="vi"                 # vi, en
$env:AI_PLAYER_PERFORMANCE_PRESET="balanced"     # low_latency, offline_lite, balanced, quality
$env:AI_PLAYER_AUDIO_SOURCE="original"           # original, system, microphone, system_microphone, transcript, document_editor, subtitle
$env:AI_PLAYER_TRANSCRIPT_PATH="D:\path\subtitles.srt"

$env:AI_PLAYER_WHISPER_MODEL="models\asr\faster-whisper-base"
$env:AI_PLAYER_WHISPER_DEVICE="auto"             # auto, cpu, cuda
$env:AI_PLAYER_WHISPER_COMPUTE="int8"
$env:AI_PLAYER_WHISPER_BEAM_SIZE="1"
$env:AI_PLAYER_WHISPER_VAD_FILTER="1"

$env:AI_PLAYER_TRANSLATOR_PROVIDER="nllb_ct2"    # nllb_ct2, nllb, none
$env:AI_PLAYER_TRANSLATION_MODEL="models\translation\nllb-200-distilled-600M-ct2-int8"
$env:AI_PLAYER_TRANSLATION_DEVICE="auto"
$env:AI_PLAYER_TARGET_LANGUAGE="vi"
$env:AI_PLAYER_PRESERVE_SOURCE_TERMS="1"
$env:AI_PLAYER_PRESERVED_SOURCE_TERMS="OpenAI, API, NLLB, 先生, 오빠, gpt-4.1-mini"

$env:AI_PLAYER_TTS_PROVIDER="vieneu"             # vieneu, edge, none
$env:AI_PLAYER_TTS_VOICE="Doan"
$env:AI_PLAYER_TTS_MALE_VOICE="Binh"
$env:AI_PLAYER_TTS_FEMALE_VOICE="Doan"

$env:AI_PLAYER_VIENEU_TTS_MODE="standard"        # standard, turbo
$env:AI_PLAYER_VIENEU_TTS_RUNTIME="subprocess"   # subprocess, auto, inprocess
$env:AI_PLAYER_VIENEU_TTS_DEVICE="auto"
$env:AI_PLAYER_VIENEU_TTS_BACKEND="auto"

$env:AI_PLAYER_OCR_MODEL="models\ocr\tessdata"
$env:AI_PLAYER_OCR_PSM="6"
$env:AI_PLAYER_OCR_MIN_CONFIDENCE="35"
$env:AI_PLAYER_OCR_CROP_TOP_RATIO="0.58"
$env:AI_PLAYER_OCR_CROP_HEIGHT_RATIO="0.38"
```

Transcript cleanup có thể dùng Ollama, model local hoặc OpenAI-compatible endpoint:

```powershell
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_MODE="off"
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_PROVIDER="ollama"      # ollama, local, openai
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_MODEL="llama3.1"
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_API_BASE="http://127.0.0.1:11434"
```

Nếu dùng Edge TTS:

```powershell
$env:AI_PLAYER_TTS_PROVIDER="edge"
$env:AI_PLAYER_TTS_VOICE="vi-VN-HoaiMyNeural"
```

## Kiểm Tra Và Phát Triển

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci
```

CI hiện chạy trên `windows-latest` với Python 3.11, gồm lint, test và Runtime Doctor chế độ CI.

Benchmark/tiện ích:

```powershell
.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py
.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py --baseline data\tmp\previous-workflow-benchmark.json --max-regression-percent 35
.\.venv\Scripts\python.exe .\scripts\compare_performance_presets.py
.\scripts\backup_local.ps1
```

## Cấu Trúc Dự Án

```text
ai_player/
  app.py                 # entrypoint QApplication
  core/                  # config, settings, GPU/runtime diagnostics, catalog model
  services/              # ASR, translation, TTS, OCR, document reader, video/audio helpers
  workers/               # QThread workers cho dubbing, export, meeting, warmup
  ui/                    # main window, media player, dialogs, settings tabs
  resources/languages/   # gói ngôn ngữ UI và dropdown vi/en
  vieneu_tts/            # runtime VieNeu-TTS nội bộ
docs/                    # MVP, recovery notes, release checklist, portable build
samples/                 # demo transcript/video nhỏ
scripts/                 # tải model, build portable, doctor, benchmark, backup
tests/                   # smoke/unit tests đã khôi phục
models/                  # model offline tải về, không commit
data/                    # settings, cache và transcript tạm do app tạo
```

## Ghi Chú Hiện Tại

- Offline model folders cần tải lại sau khi clone.
- NLLB, Whisper lớn và VieNeu model đầy đủ nên được kiểm tra thủ công trên máy Windows/GPU trước khi phát hành build cho người dùng cuối.
- Khi export từ nguồn live (`system`, `microphone`, `system_microphone`, `subtitle`), app có thể yêu cầu chuyển sang nguồn file/transcript ổn định hơn.

## Donation

Nếu AI Player hữu ích với bạn, bạn có thể ủng hộ tác giả qua VietQR/MB Bank:

- Ngân hàng: `MB Bank`
- Số tài khoản: `0914030780`
- Chủ tài khoản: `LE PHAM ANH KHOA`
- Nội dung gợi ý: `Donation AI Player`

![Donation VietQR](docs/assets/donation-mbb-0914030780.jpg)
