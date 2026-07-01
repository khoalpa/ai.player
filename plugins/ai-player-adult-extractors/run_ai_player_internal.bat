@echo off
setlocal
set "PROJECT_ROOT=D:\project\ai.player"
set "AI_PLAYER_EXTRA_YTDLP_HOSTS=missav.ai,missav.com,missav.ws,supjav.com,javmost.com,javmost.cx,javgg.net,javgg.to,r18.com,javlibrary.com,javhd.com,njav.com,livejasmin.com,vlxx.*,*.vlxx.*,buomtv.*,*.buomtv.*,eporner.com,spankbang.com,drtuber.com,tnaflix.com,empflix.com,4tube.com,beeg.com,sunporno.com,xvideos.com,xnxx.com,xhamster.com,youporn.com,redtube.com,pornhub.com,chaturbate.com,chaturbate.eu,chaturbate.global,stripchat.com,bongacams.com,bongacams.net,cam4.com,camsoda.com"
cd /d "%PROJECT_ROOT%"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py
) else (
  if exist "%SystemRoot%\py.exe" (
    py -3 main.py
  ) else (
    python main.py
  )
)
