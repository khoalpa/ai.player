# AI Player

AI Player là ứng dụng Windows viết bằng PySide6, kết hợp phát video, đọc tài liệu và lồng tiếng gần thời gian thực trong một quy trình duy nhất. Ứng dụng dùng ASR để nhận dạng lời thoại, dịch máy để chuyển ngôn ngữ, OCR để đọc phụ đề cứng và TTS để tạo giọng nói.

Thiết lập mặc định ưu tiên xử lý offline: Faster Whisper đảm nhiệm nhận dạng giọng nói, NLLB xử lý bản dịch, VieNeu-TTS tạo giọng đọc tiếng Việt và Tesseract nhận dạng phụ đề cứng.

## Tính năng nổi bật

- Mở video cục bộ, URL media trực tiếp hoặc trang video được `yt-dlp` hỗ trợ.
- Lưu đệm video từ URL theo chất lượng phát (`360p`, `480p`, `720p`, `1080p`, `best`) để xem và xử lý ổn định hơn.
- Nhận dạng lời thoại bằng `faster-whisper`, có VAD, chọn thiết bị `cpu`/`cuda`/`auto` và compute type.
- Dịch bằng NLLB 1.3B local hoặc bỏ qua dịch khi chỉ cần đọc lại transcript gốc.
- Tạo giọng đọc bằng VieNeu-TTS v3 Turbo 48 kHz (tiến trình riêng) hoặc Edge TTS.
- Chọn nguồn đầu vào: âm gốc, âm hệ thống, micro, hệ thống + micro, transcript, editor tài liệu hoặc OCR phụ đề cứng.
- Mở `.pptx`, `.docx`, `.pdf`, `.txt`, `.md`, `.rtf`, `.csv`, `.json`, trích nội dung thành transcript và phát như một timeline.
- Xuất audio `.wav`, video `.mp4` đã lồng tiếng, transcript và video review chất lượng cao cho tài liệu.
- Dùng Runtime Doctor trong CLI hoặc UI để kiểm tra gói Python, FFmpeg, Tesseract, runtime GPU, model, cache và thiết bị thu âm.
- Runtime hiển thị số lần thiếu bộ đệm/fallback và độ trễ P95 của pipeline trong phiên; số liệu chỉ nằm trong bộ nhớ và không chứa nội dung media.
- Có tab `Tác vụ` để theo dõi tải model, warmup, cache URL, export, provider preview và các lỗi gần đây ở một nơi.
- Có bộ nhớ đệm cho ASR, làm sạch văn bản/bản dịch và TTS, giúp xử lý lại cùng nội dung nhanh hơn; có thể xem hoặc xóa từng loại cache trong UI.
- Giao diện có gói ngôn ngữ `vi`/`en`, preset hiệu năng và tab quản lý model offline.

## Yêu cầu hệ thống

1. Windows 10/11.
2. Python 3.10+.
3. FFmpeg và ffplay trong `PATH`.
4. Tesseract OCR trong `PATH` nếu dùng nguồn `Subtitle`. App cũng tìm đường dẫn mặc định `C:\Program Files\Tesseract-OCR\tesseract.exe`.
5. LibreOffice nếu muốn render đúng ảnh gốc của `.pptx`/`.docx` trong khung tài liệu.
6. Internet cho lần đầu tải model hoặc khi dùng Edge TTS. Sau khi tải đủ model, các workflow offline có thể chạy không cần mạng.

## Cài đặt

Các lệnh bên dưới gọi trực tiếp `.\.venv\Scripts\python.exe` thay vì `python`. Cách này bảo đảm dự án chạy đúng môi trường ảo ngay cả khi `python` chưa có trong `PATH` hoặc đang trỏ tới alias của Microsoft Store.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,offline-ai]"
```

Để dùng bản nhẹ, không cài model AI offline hoặc thành phần GPU:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --profile lite
```

Để cài runtime đầy đủ cho build portable, GPU và tách giọng bằng Demucs:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging,offline-ai,gpu,audio-separation]"
```

Để cài runtime AI CPU/offline cơ bản bằng tệp requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Chuẩn bị runtime

Tải bộ model offline mặc định:

```powershell
.\scripts\download_offline_models.ps1
```

Các script tải riêng:

```powershell
.\scripts\download_whisper_model.ps1
.\scripts\download_translator_models.ps1
.\scripts\download_vieneu_tts_models.ps1          # CPU
# GPU NVIDIA: .\scripts\download_vieneu_tts_models.ps1 -Cuda
.\scripts\download_tessdata_models.ps1
.\scripts\download_speaker_gender_model.ps1
```

VieNeu dùng SDK `3.8.3` trong môi trường `.venv-vieneu`, tách khỏi bộ nhận dạng và dịch của ứng dụng.
Bộ mô hình v3 Turbo và codec MOSS được cố định phiên bản trong `ai_player/runtime/vieneu_v3.py`.
Ứng dụng chỉ chạy `v3turbo`; khi GPU lỗi, nó có thể thử lại cùng mô hình trên CPU.
Các cấu hình v1/v2 được chuyển một chiều sang v3 khi nạp và lưu thiết lập.

Kiểm thử âm thanh thật với kết nối mạng bị chặn và bộ nhớ đệm Hugging Face trống:

```powershell
.\.venv\Scripts\python.exe scripts\verify_vieneu_offline.py
.\.venv\Scripts\python.exe scripts\verify_vieneu_offline.py --device cuda
```

Báo cáo và âm thanh mẫu nằm trong `output/vieneu-v3-verification`.
Sau khi kiểm thử offline đạt, xem các thư mục cũ cần dọn bằng
`.\scripts\remove_legacy_vieneu.ps1 -WhatIf`; chạy lại không có `-WhatIf` để xóa vĩnh viễn chúng.
Bản Portable Lite cần cài môi trường TTS và tải bộ mô hình tại thư mục gốc trên máy đích trước khi dùng offline.

Kiểm tra nhanh môi trường:

```powershell
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py
```

Trong CI hoặc môi trường không cần liệt kê thiết bị audio:

```powershell
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci
```

## Kiểm tra dependency

Trước khi chia sẻ build, chạy audit dependency theo `docs/dependency_audit.md`:

```powershell
.\scripts\audit_dependencies.ps1
```

## Chạy ứng dụng

```powershell
.\.venv\Scripts\python.exe main.py
```

Hoặc nhấp đúp vào:

```bat
open_app.bat
```

## Tạo bản portable

```powershell
.\scripts\build_portable.ps1
```

Kết quả được ghi vào `dist\portable\AI Player Lite`. Gói Lite không chứa thư mục `models\`; muốn chạy hoàn toàn offline, bạn cần tải hoặc sao chép model vào máy đích.

## Quy trình sử dụng

1. Bấm `Mở file`, `Mở URL`, `Mở tài liệu` hoặc dùng tab editor/tác vụ meeting.
2. Chọn preset trong tab `Cơ bản`: `Quick preview`, `Offline lite`, `Balanced` hoặc `Quality / Export`.
3. Chọn nguồn audio/transcript, ngôn ngữ nguồn/đích, provider dịch và provider TTS.
4. Bấm `Lồng tiếng` để phát gần thời gian thực.
5. Theo dõi tab `Tác vụ` nếu app đang tải/cache URL, warmup runtime, export hoặc chạy provider preview.
6. Bấm `Export` để xuất transcript, audio, video hoặc bản review chất lượng cao.

Trong app, bấm nút `?` để mở `Hướng dẫn sử dụng`. Hướng dẫn này tự đi theo ngôn ngữ giao diện và hiển thị cả cấu hình hiện tại để dễ biết thiết lập nào đang làm chậm hoặc ảnh hưởng chất lượng.

### Bảng thuật ngữ Trung–Việt

Trong phần giữ thuật ngữ, mỗi dòng của file thuật ngữ có thể dùng một trong hai dạng:

```text
OpenAI
人工智能 = trí tuệ nhân tạo
师傅 => sư phụ
江湖 = giang hồ
```

Dòng chỉ có một cụm sẽ giữ nguyên cụm đó. Dòng `nguồn = đích` hoặc `nguồn => đích` buộc mọi luồng dịch dùng cách dịch đã duyệt; cụm dài được ưu tiên trước cụm ngắn. Khi nguồn là tiếng Trung và đích là tiếng Việt, pipeline cũng bảo toàn số, ngày, tỷ lệ phần trăm và chuẩn hóa dấu câu trước khi tạo phụ đề hoặc giọng đọc. Sau khi sửa file thuật ngữ, hãy xóa cache Translation trong tab `Tác vụ` nếu video đã được xử lý trước đó.

## Theo dõi tác vụ và cache

Tab `Tác vụ` gom các việc nền để dễ biết app đang bận ở đâu:

- `Đang chạy`: warmup runtime, tải model, cache URL, chuẩn bị media, dubbing/export, provider preview.
- `Cache`: số lần dùng lại/ghi cache ASR, text/translation cleanup, TTS và URL đã tải về.
- `Lỗi gần đây`: lỗi gần đây để thử lại, đổi provider hoặc giảm thiết lập nặng.

Các cache workflow giúp lặp lại cùng nguồn nhanh hơn, nhất là khi chỉnh dịch/TTS hoặc export lại. Nếu kết quả cũ bị sai, đổi model/provider hoặc muốn đo benchmark sạch, dùng mục `Cache` trong tab `Tác vụ` để xóa riêng ASR, Text, TTS hoặc xóa tất cả.

Mặc định các cache ASR, text workflow và TTS được bật. Có thể tắt bằng biến môi trường:

```powershell
$env:AI_PLAYER_ASR_CACHE="0"
$env:AI_PLAYER_WORKFLOW_TEXT_CACHE="0"
$env:AI_PLAYER_TTS_CACHE="0"
```

## Chọn nhanh theo mục tiêu

| Mục tiêu | Thiết lập nên bắt đầu | Ghi chú |
| --- | --- | --- |
| Xem nhanh | `Quick preview`, Edge TTS, bộ đệm thấp hoặc cân bằng | Phù hợp để kiểm tra nội dung trước; cần Internet cho Edge TTS. |
| Chạy offline | `Offline lite`, NLLB 1.3B, VieNeu-TTS local | Nên dùng GPU nếu có; CPU vẫn chạy được nhưng đoạn đầu có thể lâu. |
| Đọc tài liệu | Nguồn `Editor`/tài liệu, giọng rõ, tắt dịch nếu chỉ cần đọc nguyên văn | Với file dài, chia nhỏ nội dung hoặc giảm max ký tự TTS nếu tạo giọng chậm. |
| Xuất bản | `Quality / Export`, tăng buffer/lookahead, kiểm tra transcript trước khi xuất | Chậm hơn nhưng giảm lỗi nhịp, lỗi dịch và lỗi âm thanh ở video cuối. |

## Xử lý sự cố thường gặp

| Dấu hiệu | Cách thử trước |
| --- | --- |
| Nút Play chưa bật | Đợi đủ bộ đệm, giảm `Bộ đệm`, hoặc chuyển sang Edge TTS để tạo âm nhanh hơn. |
| Âm đích lệch nhịp | Bật `Tự khớp âm thanh`, tăng lookahead, hoặc giảm tốc độ/độ dài đoạn nếu giọng bị kéo dài. |
| URL web không mở | Bật cache video URL, giảm chất lượng phát, hoặc dùng URL media trực tiếp nếu có. |
| Dịch/đọc sai thuật ngữ | Bật giữ thuật ngữ và chọn file thuật ngữ; kiểm tra lại ngôn ngữ nguồn trước khi chạy. |
| App xử lý quá chậm | Tránh mở nhiều cửa sổ cùng lúc, dùng Edge TTS khi cần nhanh, hoặc giảm model/thiết lập local nặng trên CPU. |
| Kết quả lặp lại không đổi sau khi chỉnh model/provider | Xóa cache workflow liên quan trong tab `Tác vụ`, rồi chạy lại. |
| Không rõ app đang làm gì | Mở tab `Tác vụ`; nếu một tác vụ nền bị kẹt lâu, dùng `Dừng tất cả` rồi thử lại với preset nhẹ hơn. |

## Nguồn và định dạng được hỗ trợ

Video cục bộ:

- `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`

URL media trực tiếp:

- `.mp4`, `.mkv`, `.mov`, `.webm`, `.avi`, `.m4v`, `.m3u8`, `.mpd`
- Protocol hợp lệ: `http`, `https`, `rtsp`, `rtmp`, `mms`

Trang video qua `yt-dlp`:

- YouTube, TikTok, Facebook, Instagram, Threads, X/Twitter, Vimeo, Dailymotion, public Telegram previews.
- Bản dựng nội bộ có thể cài plugin `yt-dlp` riêng và khai báo host bổ sung bằng `AI_PLAYER_EXTRA_YTDLP_HOSTS`.
- Có thể mở rộng danh sách host dành cho adult extractor qua `data/config/private/adult_sites.local.json` hoặc bằng cách probe URL với `scripts/probe_adult_site.py`.
- Bản dựng nội bộ có thể cài gói Telegram client riêng để đăng nhập bằng Telethon và tải nội dung Telegram cần xác thực.
- Có thể duyệt URL kênh và playlist YouTube ngay trong ứng dụng. Bản dựng nội bộ dùng `ai-player-youtube-client` để có adapter YouTube chuyên biệt; nếu không cài gói này, AI Player đọc metadata từ trang YouTube công khai.

Tài liệu:

- PowerPoint: `.pptx`
- Word: `.docx`
- PDF: `.pdf`
- Text/Markdown/RTF: `.txt`, `.text`, `.md`, `.rtf`
- Data text: `.csv`, `.json`

Định dạng Office cũ `.doc` và `.ppt` chưa được hỗ trợ trực tiếp; hãy lưu lại thành `.docx` hoặc `.pptx`.

## Nguồn đầu vào

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

## Model mặc định

Các đường dẫn model mặc định nằm trong `models\`:

```text
models/asr/faster-whisper-large-v3
models/translation/nllb-200-1.3B
models/tts/vieneu/v3-turbo
models/ocr/tessdata_best
models/speaker_gender/common-voice-gender-detection
```

Preset `Balanced` mặc định dùng Whisper large-v3, NLLB 1.3B, VieNeu-TTS v3 Turbo và target language `vi`.

## Biến môi trường hữu ích

```powershell
$env:AI_PLAYER_GUI_LANGUAGE="vi"                 # vi, en
$env:AI_PLAYER_PERFORMANCE_PRESET="balanced"     # low_latency, offline_lite, balanced, quality
$env:AI_PLAYER_AUDIO_SOURCE="original"           # original, system, microphone, system_microphone, transcript, document_editor, subtitle
$env:AI_PLAYER_TRANSCRIPT_PATH="D:\path\subtitles.srt"
$env:AI_PLAYER_ASR_CACHE="1"
$env:AI_PLAYER_WORKFLOW_TEXT_CACHE="1"
$env:AI_PLAYER_WORKFLOW_TEXT_CACHE_ENTRIES="4096"
$env:AI_PLAYER_TTS_CACHE="1"

$env:AI_PLAYER_WHISPER_MODEL="models\asr\faster-whisper-large-v3"
$env:AI_PLAYER_WHISPER_DEVICE="auto"             # auto, cpu, cuda
$env:AI_PLAYER_WHISPER_COMPUTE="int8"
$env:AI_PLAYER_WHISPER_BEAM_SIZE="1"
$env:AI_PLAYER_WHISPER_VAD_FILTER="1"

$env:AI_PLAYER_TRANSLATOR_PROVIDER="nllb"        # nllb, none
$env:AI_PLAYER_TRANSLATION_MODEL="models\translation\nllb-200-1.3B"
$env:AI_PLAYER_TRANSLATION_DEVICE="auto"
$env:AI_PLAYER_TARGET_LANGUAGE="vi"
$env:AI_PLAYER_PRESERVE_SOURCE_TERMS="1"
$env:AI_PLAYER_PRESERVED_SOURCE_TERMS="OpenAI, API, NLLB, 先生, 오빠, gpt-4.1-mini"

$env:AI_PLAYER_TTS_PROVIDER="vieneu"             # vieneu, edge, none
$env:AI_PLAYER_TTS_VOICE="Doan"
$env:AI_PLAYER_TTS_MALE_VOICE="Binh"
$env:AI_PLAYER_TTS_FEMALE_VOICE="Doan"

$env:AI_PLAYER_VIENEU_TTS_MODE="v3turbo"
$env:AI_PLAYER_VIENEU_TTS_RUNTIME="subprocess"   # subprocess
$env:AI_PLAYER_VIENEU_TTS_DEVICE="auto"
$env:AI_PLAYER_VIENEU_TTS_BACKEND="auto"

$env:AI_PLAYER_OCR_MODEL="models\ocr\tessdata_best"
$env:AI_PLAYER_OCR_PSM="6"
$env:AI_PLAYER_OCR_MIN_CONFIDENCE="35"
$env:AI_PLAYER_OCR_CROP_TOP_RATIO="0.58"
$env:AI_PLAYER_OCR_CROP_HEIGHT_RATIO="0.38"
```

Transcript cleanup dùng Groq:

```powershell
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_MODE="off"
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_PROVIDER="groq"
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_MODEL="openai/gpt-oss-20b"
$env:AI_PLAYER_TRANSCRIPT_CLEANUP_API_BASE=""
```

Nếu dùng Edge TTS:

```powershell
$env:AI_PLAYER_TTS_PROVIDER="edge"
$env:AI_PLAYER_TTS_VOICE="vi-VN-HoaiMyNeural"
```

## Kiểm tra và phát triển

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py --ci
```

CI hiện chạy trên `windows-latest` với Python 3.11, gồm lint, test và Runtime Doctor chế độ CI.

Benchmark/tiện ích:

```powershell
.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py
.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py --check-baselines --baseline .\docs\workflow_benchmark_baselines.json
.\.venv\Scripts\python.exe .\scripts\workflow_benchmark.py --baseline data\tmp\previous-workflow-benchmark.json --max-regression-percent 35
.\.venv\Scripts\python.exe .\scripts\compare_performance_presets.py
.\scripts\backup_local.ps1
```

Trong UI, mục `Sức khỏe workflow` ở tab `Tác vụ` đọc baseline trong `docs\workflow_benchmark_baselines.json` và kết quả benchmark local gần nhất để báo workflow nào đang chậm hơn ngưỡng.

## Cấu trúc dự án

```text
ai_player/
  app.py                 # entrypoint QApplication
  bootstrap.py           # cấu hình và bộ quản lý tác vụ dùng chung
  configuration/         # 10 nhóm cấu hình, phiên bản dữ liệu lưu
  domain/                # quy tắc xử lý, lịch âm thanh, dữ liệu thuần
  application/           # quy trình xử lý độc lập giao diện và nhà cung cấp
  adapters/              # AI, TTS, media, nguồn dữ liệu, lưu trữ, bộ chạy Qt
  runtime/               # hồ sơ môi trường, mô hình, chẩn đoán và khởi động
  core/                  # ghi nhật ký, ngôn ngữ, che thông tin bí mật
  workers/               # lớp nối Qt mỏng cho các quy trình xử lý
  ui/features/           # bộ điều khiển theo chức năng, sở hữu trạng thái rõ ràng
  ui/views/              # các bộ dựng thanh công cụ, bảng và nhóm cài đặt
  resources/languages/   # gói ngôn ngữ UI và dropdown vi/en
  resources/tts/         # danh sách giọng VieNeu v3 Turbo
docs/                    # MVP, recovery notes, release checklist, portable build
samples/                 # demo transcript/video nhỏ
scripts/                 # tải model, build portable, doctor, benchmark, backup
tests/                   # smoke/unit tests đã khôi phục
models/                  # model offline tải về, không commit
data/                    # settings, cache và transcript tạm do app tạo
```

## Lưu ý hiện tại

- Offline model folders cần tải lại sau khi clone.
- NLLB, Whisper lớn và VieNeu model đầy đủ nên được kiểm tra thủ công trên máy Windows/GPU trước khi phát hành build cho người dùng cuối.
- Khi export từ nguồn live (`system`, `microphone`, `system_microphone`, `subtitle`), app có thể yêu cầu chuyển sang nguồn file/transcript ổn định hơn.

## Giấy phép

AI Player được phân phối theo giấy phép MIT. Xem `LICENSE` để biết đầy đủ điều khoản.
