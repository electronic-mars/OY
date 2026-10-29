@echo off
rem Test clips for the self-test. Audio tracks are silent on purpose: test runs must not
rem make noise while the owner works.
chcp 65001 >nul
cd /d "%~dp0.."
if not exist tests\media mkdir tests\media
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=1280x720:rate=30" -f lavfi -i "anullsrc=r=48000:cl=stereo" -t 20 -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 64k tests\media\test720.mp4
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=1920x1080:rate=25" -f lavfi -i "anullsrc=r=48000:cl=stereo" -t 15 -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 64k tests\media\test1080.mkv
(echo 1& echo 00:00:01,000 --^> 00:00:06,000& echo Hello, subtitles!& echo.& echo 2& echo 00:00:07,000 --^> 00:00:12,000& echo Second line) > tests\media\test720.srt
rem Two audio tracks (eng stereo, ukr 5.1), one embedded subtitle track, a title tag; plus an external audio file.
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=1280x720:rate=25" -f lavfi -i "anullsrc=r=48000:cl=stereo" -f lavfi -i "anullsrc=r=44100:cl=5.1" -i tests\media\test720.srt -t 30 -map 0:v -map 1:a -map 2:a -map 3:s -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 64k -c:s srt -metadata:s:a:0 language=eng -metadata:s:a:0 title="English" -metadata:s:a:1 language=ukr -metadata:s:a:1 title="Ukrainian 5.1" -metadata:s:s:0 language=eng -metadata title="Test film" tests\media\test_multi.mkv
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "anullsrc=r=48000:cl=mono" -t 30 -c:a libopus tests\media\test_multi.extra.opus
rem 90 s clip: resume only remembers files longer than a minute.
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=640x360:rate=25" -f lavfi -i "anullsrc=r=48000:cl=stereo" -t 90 -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -b:a 32k tests\media\test_long.mkv
