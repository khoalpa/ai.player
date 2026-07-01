@echo off
setlocal
set "PROJECT_ROOT=D:\project\ai.player"
set "AI_PLAYER_EXTRA_YTDLP_HOSTS=missav.ai,missav.com,missav.ws,supjav.com,javmost.com,javmost.cx,javgg.net,javgg.to,r18.com,javlibrary.com,javhd.com,njav.com,livejasmin.com,vlxx.*,*.vlxx.*,buomtv.*,*.buomtv.*,eporner.com,spankbang.com,drtuber.com,tnaflix.com,empflix.com,4tube.com,beeg.com,sunporno.com,xvideos.com,xnxx.com,xhamster.com,youporn.com,redtube.com,pornhub.com,chaturbate.com,chaturbate.eu,chaturbate.global,stripchat.com,bongacams.com,bongacams.net,cam4.com,camsoda.com,manyvids.com,thisvid.com,tube8.com,youjizz.com,porntube.com,nuvid.com,pornoxo.com,rule34video.com,fc2.com,jable.tv,netflav.com,avgle.com,alphaporno.com,hellporno.com,hellporno.net,lovehomeporn.com,members.nubiles-porn.com,peekvids.com,playvids.com,pornbox.com,pornerbros.com,pornflip.com,pornotube.com,porntop.com,hclips.com,hdzog.com,hdzog.tube,hotmovs.com,hotmovs.tube,inporn.com,privatehomeclips.com,tubepornclassic.com,txxx.com,txxx.tube,upornia.com,upornia.tube,vjav.com,vjav.tube,vxxx.com,voyeurhit.com,voyeurhit.tube,xxxymovies.com,zenporn.com,myvidster.com,murrtube.net,videos.toypics.net"
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
