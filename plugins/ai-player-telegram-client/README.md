# AI Player Telegram Client

Plugin nội bộ này bổ sung khả năng đăng nhập và tải nội dung Telegram bằng tài khoản người dùng thông qua Telethon. Plugin chỉ dành cho các bản dựng nội bộ của AI Player.

## Cài đặt

Cài plugin vào môi trường ảo của AI Player:

```powershell
D:\project\ai.player\.venv\Scripts\python.exe -m pip install D:\project\ai-player-telegram-client
```

## Tạo bản dựng nội bộ

Chạy lệnh sau tại thư mục dự án AI Player:

```powershell
cd D:\project\ai.player
.\scripts\build_internal.ps1 `
  -PrivateTelegramPackage D:\project\ai-player-telegram-client `
  -PrivateYtdlpPluginPackage D:\project\ai-player-adult-extractors
```

## Dữ liệu đăng nhập

Plugin lưu metadata đăng nhập đã được bảo vệ và phiên Telethon trong vùng cấu hình riêng của AI Player:

```text
data/config/private/telegram
```

Không commit nội dung thư mục này hoặc chia sẻ tệp phiên Telethon.
