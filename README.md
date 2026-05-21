# AI Player

AI Player là video player Windows dùng PySide6, cho phép xem video nguồn nhưng nghe bản lồng tiếng gần thời gian thực bằng tiếng Việt hoặc ngôn ngữ đích đã chọn.

## Tính năng

- Mở video cục bộ hoặc URL video được `yt-dlp` hỗ trợ.
- Nhận dạng lời thoại bằng `faster-whisper`.
- Dịch bằng NLLB local hoặc backend dịch khả dụng trong app.
- Tạo giọng đọc bằng VieNeu-TTS nội bộ hoặc Edge TTS.
- Điều chỉnh âm gốc, âm lồng tiếng, tốc độ, buffer, thiết bị/model xử lý.
- Lưu transcript, export âm/video đã lồng tiếng, và xuất bản xem lại MP4 chất lượng cao cho cả video/tài liệu.
- Chọn nguồn đầu vào: âm gốc, âm hệ thống, micro, transcript, phụ đề cứng OCR.
- Mở tài liệu `.pptx`, `.docx`, `.pdf`, `.txt`, `.md`, `.rtf`, `.csv`, `.json` để trích text, dịch và phát âm.
- Hiển thị GUI theo phong cách Windows 11, hỗ trợ đổi ngôn ngữ giao diện `vi`/`en`.

## Yêu cầu hệ thống

1. Windows 10/11.
2. Python 3.10+.
3. FFmpeg và ffplay trong `PATH`.
4. Tesseract OCR trong `PATH` nếu dùng nguồn `Subtitle`. App cũng tự tìm đường dẫn mặc định `C:\Program Files\Tesseract-OCR\tesseract.exe`.
5. Internet cho lần đầu tải model hoặc dùng Edge TTS, trừ khi đã chuẩn bị offline đầy đủ.

## Cài đặt

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Cấu trúc dự án

```text
ai_player/
  app.py                 # entrypoint QApplication
  core/                  # cấu hình, lưu settings, catalog runtime
  services/              # dịch, TTS, OCR, đọc tài liệu, nguồn video/audio
  workers/               # QThread/worker xử lý nền và export
  ui/                    # cửa sổ chính, mixin giao diện, media player, dialog
  resources/languages/   # gói ngôn ngữ giao diện và dropdown
  vieneu_tts/            # runtime VieNeu-TTS nội bộ
data/config/             # settings và transcript tạm do app tạo
docs/                    # tài liệu kỹ thuật
models/                  # model offline tải về
scripts/                 # tiện ích tải model, chuẩn bị runtime, kiểm tra môi trường
```

Chuẩn bị model offline nếu cần:

```powershell
.\scripts\download_offline_models.ps1
```

Kiểm tra nhanh runtime, thư viện, tool ngoài, model/cache và thiết bị capture:

```powershell
.\.venv\Scripts\python.exe .\scripts\runtime_doctor.py
```

## Chạy app

```powershell
.\.venv\Scripts\python.exe main.py
```

Hoặc double-click:

```bat
open_app.bat
```

## Nguồn và định dạng đã hỗ trợ

Tệp video cục bộ:

- `.mp4`
- `.mkv`
- `.avi`
- `.mov`
- `.webm`

URL media trực tiếp:

- `.mp4`
- `.mkv`
- `.mov`
- `.webm`
- `.avi`
- `.m4v`
- `.m3u8`
- `.mpd`

Trang web video được hỗ trợ qua `yt-dlp`:

- YouTube: `youtube.com`, `m.youtube.com`, `music.youtube.com`, `youtu.be`
- TikTok: `tiktok.com`, `vm.tiktok.com`, `vt.tiktok.com`
- Facebook: `facebook.com`, `m.facebook.com`, `web.facebook.com`, `fb.watch`
- Instagram và Threads: `instagram.com`, `threads.net`
- X/Twitter: `x.com`, `twitter.com`
- Vimeo: `vimeo.com`
- Dailymotion: `dailymotion.com`, `dai.ly`
- Telegram: `t.me`, `telegram.me`
- BuomTV: `buomtv.*`, `*.buomtv.*`
- JAV/adult video: `missav.ai`, `missav.com`, `missav.ws`, `supjav.com`, `javmost.com`, `javmost.cx`, `javgg.net`, `javgg.to`, `r18.com`, `javlibrary.com`, `javhd.com`
- Live/cam: `chaturbate.com`, `chaturbate.eu`, `chaturbate.global`, `stripchat.com`, `bongacams*.com`, `bongacams*.net`, `livejasmin.com`, `cam4.com`, `camsoda.com`

Tệp tài liệu:

- PowerPoint: `.pptx`
- Word: `.docx`
- PDF: `.pdf`
- Text/Markdown/RTF: `.txt`, `.text`, `.md`, `.rtf`
- Dữ liệu text: `.csv`, `.json`

URL hợp lệ có thể dùng giao thức `http`, `https`, `rtsp`, `rtmp` hoặc `mms`. Các định dạng Office cũ `.doc` và `.ppt` nên được lưu lại thành `.docx` hoặc `.pptx` trước khi mở.

## Mở tài liệu

Bấm `Mở tài liệu` để chọn PowerPoint, Word, PDF hoặc text/data file. App sẽ hiển thị trang/slide gốc trong khung video, trích nội dung thành transcript tạm tại `data\config\current_document_transcript.srt`, tự chuyển `Nguồn` sang `Transcript`, rồi dùng pipeline dịch/TTS hiện có để đọc từng trang hoặc slide.

Khi phát tài liệu, app tự chuyển sang trang kế tiếp theo timeline của từng trang. Trang/slide không có chữ vẫn hiển thị bản gốc trong vài giây rồi tự chuyển tiếp mà không tạo giọng đọc.

PDF được render trực tiếp bằng PyMuPDF. Với `.pptx`/`.docx`, app render bản gốc qua LibreOffice nếu có `soffice`/`libreoffice` trong `PATH` hoặc ở đường dẫn mặc định `C:\Program Files\LibreOffice\program\soffice.exe`. Khung video chỉ hiển thị ảnh trang/slide, không hiển thị text dịch hoặc text trích thuần.

Định dạng hỗ trợ trực tiếp:

- PowerPoint: `.pptx`
- Word: `.docx`
- PDF: `.pdf`
- Text: `.txt`, `.text`, `.md`, `.rtf`
- Data text: `.csv`, `.json`

Các định dạng Office cũ `.doc` và `.ppt` nên được lưu lại thành `.docx` hoặc `.pptx` trước khi mở.

## Xuất bản xem lại chất lượng cao

Sau khi mở video hoặc tài liệu, chọn preset `Chất lượng / Xuất bản` nếu cần, rồi bấm `Export` -> `Xuất bản xem lại chất lượng cao (.mp4)`.

- Với video, app xử lý toàn bộ file từ đầu: tách audio, nhận diện lời thoại, dịch, tạo giọng đích, căn theo timeline và mux lại thành MP4.
- Với tài liệu, app dùng transcript đã trích từ trang/slide, tạo giọng đọc cho toàn bộ nội dung, dựng video 1080p từ ảnh trang/slide gốc và ghép audio AAC bitrate cao để xem lại.
- Nếu tài liệu không có ảnh trang gốc, app tự dựng trang chữ 1080p làm fallback thay vì chỉ lưu transcript.

## Nguồn đầu vào

Dropdown `Nguồn` trong tab `Cơ bản` hỗ trợ:

- `Âm gốc`: lấy audio track đầu tiên của video, đây là luồng xử lý mặc định.
- `Âm hệ thống`: ưu tiên capture WASAPI loopback bằng `soundcard`; nếu không được sẽ fallback qua FFmpeg DirectShow. Không bắt buộc cài VB-CABLE/Stereo Mix khi WASAPI loopback hoạt động.
- `Micro`: ưu tiên capture bằng `soundcard`; nếu không được sẽ fallback qua FFmpeg DirectShow.
- `Transcript`: đọc `.srt`, `.vtt` hoặc `.txt`; nếu file có timestamp, app sẽ phát theo timeline.
- `Subtitle`: OCR phụ đề cứng ở vùng dưới video bằng Tesseract, rồi dịch/TTS từ text OCR.

Các language packs OCR có thể đặt trong `models\ocr\tessdata`. App ưu tiên thư mục này trước, sau đó mới dùng tessdata trong thư mục cài Tesseract.

Có thể chỉ định thiết bị capture bằng biến môi trường. Với `soundcard`, dùng một phần tên thiết bị loa/micro; với fallback DirectShow, dùng đúng tên DirectShow:

```powershell
$env:AI_PLAYER_SYSTEM_AUDIO_DEVICE="virtual-audio-capturer"
$env:AI_PLAYER_MICROPHONE_DEVICE="Microphone Array (Intel(R) Smart Sound Technology for Digital Microphones)"
```

Liệt kê thiết bị DirectShow:

```powershell
ffmpeg -hide_banner -f dshow -list_devices true -i dummy
```

## Cấu hình hữu ích

```powershell
$env:AI_PLAYER_GUI_LANGUAGE="vi"            # vi, en
$env:AI_PLAYER_AUDIO_SOURCE="original"      # original, system, microphone, transcript, subtitle
$env:AI_PLAYER_TRANSCRIPT_PATH="D:\path\subtitles.srt"
$env:AI_PLAYER_WHISPER_MODEL="models\asr\faster-whisper-base"
$env:AI_PLAYER_WHISPER_DEVICE="auto"        # auto, cpu, cuda
$env:AI_PLAYER_WHISPER_BEAM_SIZE="1"        # 1 nhanh, 5+ uu tien chinh xac
$env:AI_PLAYER_WHISPER_VAD_FILTER="1"       # loc doan khong co giong noi
$env:AI_PLAYER_TRANSLATION_DEVICE="auto"    # auto, cpu, cuda
$env:AI_PLAYER_OCR_MODEL="models\ocr\tessdata_best"
$env:AI_PLAYER_OCR_PSM="6"
$env:AI_PLAYER_OCR_MIN_CONFIDENCE="35"
$env:AI_PLAYER_OCR_CROP_TOP_RATIO="0.58"
$env:AI_PLAYER_OCR_CROP_HEIGHT_RATIO="0.38"
$env:AI_PLAYER_SEGMENT_SECONDS="8"
$env:AI_PLAYER_DUBBING_MIN_READY_AHEAD_SECONDS="10"
$env:AI_PLAYER_DUBBING_ENABLED_BY_DEFAULT="1"
$env:AI_PLAYER_TTS_PROVIDER="vieneu"        # vieneu, edge
$env:AI_PLAYER_TTS_VOICE="Doan"
```

VieNeu-TTS nội bộ có thể chạy `standard` hoặc `turbo` tùy model đã tải:

```powershell
$env:AI_PLAYER_VIENEU_TTS_MODE="standard"   # standard, turbo
$env:AI_PLAYER_VIENEU_TTS_RUNTIME="subprocess"
$env:AI_PLAYER_VIENEU_TTS_DEVICE="auto"
$env:AI_PLAYER_VIENEU_TTS_BACKEND="auto"
```

Nếu dùng Edge TTS:

```powershell
$env:AI_PLAYER_TTS_PROVIDER="edge"
$env:AI_PLAYER_TTS_VOICE="vi-VN-HoaiMyNeural"
```

Tải OCR language pack chất lượng cao hơn:

```powershell
.\scripts\download_tessdata_models.ps1 -Quality best
```

## Ghi chú

- Nguồn `Âm gốc`, `Transcript`, và `Subtitle` có thể tạm pause video để chuẩn bị buffer.
- Nguồn `Âm hệ thống` và `Micro` là capture live, nên app không ép pause theo cơ chế buffer cũ.
- OCR phụ đề cứng phụ thuộc chất lượng video, vị trí phụ đề, font, tương phản và gói ngôn ngữ Tesseract đã cài.
- Nếu chạy offline, hãy tải đủ Whisper/NLLB/VieNeu model trước khi bật các tùy chọn offline.
- Để render đúng ảnh gốc của PowerPoint/Word trong khung video, hãy cài LibreOffice hoặc bảo đảm `soffice`/`libreoffice` nằm trong `PATH`.
