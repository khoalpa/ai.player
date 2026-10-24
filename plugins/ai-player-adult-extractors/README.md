# AI Player Adult Extractors

Plugin `yt-dlp` riêng dành cho các bản dựng nội bộ của AI Player. Plugin mở rộng danh sách website được chấp nhận và cung cấp bộ phân tích dự phòng cho những nguồn chưa được `yt-dlp` hỗ trợ trực tiếp.

## Cài đặt cục bộ

```powershell
.\.venv\Scripts\python.exe -m pip install -e D:\project\ai-player-adult-extractors
```

## Tạo bản dựng nội bộ

```powershell
.\scripts\build_internal.ps1 `
  -PrivateYtdlpPluginPackage D:\project\ai-player-adult-extractors
```

Script build đọc `yt_dlp_plugins/extractor/adult_sites_registry.json` và tự động điền `AI_PLAYER_EXTRA_YTDLP_HOSTS`. Khi bổ sung mirror, hãy cập nhật registry trước, sau đó thêm hoặc sửa test tương ứng cho extractor.

## Thêm website mà không sửa mã

1. Chạy probe với một URL mẫu:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\probe_adult_site.py "https://example.test/watch/demo" --site-key example
   ```

2. Kiểm tra HTML fixture đã được che dữ liệu nhạy cảm và bản nháp registry trong `data\tmp\adult-site-probe`. Nếu upstream `yt-dlp` đã có extractor phù hợp, probe sẽ đánh dấu bản nháp bằng `"delegate_to_ytdlp": true`. Nếu chưa, probe tạo cấu hình extractor tổng quát với `iframe_depth`, `media_patterns` và `iframe_patterns`.
3. Chép entry vào một trong hai vị trí:
   - `yt_dlp_plugins/extractor/adult_sites_registry.json`: website dùng chung và được commit.
   - `data/config/private/adult_sites.local.json`: website riêng, chỉ dùng trên máy cục bộ.
4. Bổ sung `media_patterns` hoặc `iframe_patterns` nếu parser tổng quát không tự tìm thấy media.

Parser tổng quát đã nhận diện các mẫu HTML5 và player phổ biến như `contentUrl`, `streamUrl`, `hlsUrl`, `mp4Url`, `videoSrc`, thuộc tính media và iframe nhúng bằng `data-player-url`. Nó cũng xử lý payload thông dụng của `jwplayer().setup(...)` và `videojs().src(...)`, khóa chất lượng như `quality_720p`, cùng các thuộc tính iframe `data-iframe`, `data-embed-url` và `data-player-src`.

Ví dụ registry cục bộ:

```json
{
  "example": {
    "domains": ["example.test", "*.example.test"],
    "iframe_depth": 2,
    "accept_language": "en-US,en;q=0.9",
    "media_patterns": ["data-stream=[\"'](?P<url>[^\"']+)[\"']"],
    "iframe_patterns": ["data-player=[\"'](?P<url>[^\"']+)[\"']"]
  }
}
```

Chỉ viết extractor riêng cho từng website khi extractor tổng quát không xử lý được API có token, player nhiều bước, luồng bắt buộc đăng nhập hoặc cơ chế chống bot.

Với host đã được upstream `yt-dlp` hỗ trợ, hãy thêm domain vào registry cùng `"delegate_to_ytdlp": true`. AI Player khi đó chấp nhận URL và chuyển nó cho extractor gốc của `yt-dlp` thay vì parser tổng quát.

Các nhóm host đang được ủy quyền gồm Eporner, ManyVids, ThisVid, Tube8, YouJizz, PornTube, Nuvid, PornoXO, Rule34Video, FC2, AlphaPorno, HellPorno, LoveHomePorn, NubilesPorn, PeekVids, PlayVids, Pornbox, PornerBros, PornFlip, Pornotube, PornTop, các host thuộc nhóm Txxx, XXXYMovies, ZenPorn, MyVidster, Murrtube, Toypics và những host tube/live lớn đã thêm trước đó. Với host JAV/Asia chưa có extractor gốc, trước tiên hãy tạo entry registry tổng quát; chỉ chuyển sang extractor riêng nếu kết quả probe cho thấy cần token hoặc player nhiều bước.

## Chạy bản phát triển

Khởi động ứng dụng từ mã nguồn với danh sách host riêng:

```bat
D:\project\ai-player-adult-extractors\run_ai_player_internal.bat
```
