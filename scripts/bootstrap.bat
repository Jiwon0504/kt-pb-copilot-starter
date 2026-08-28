@echo off
REM 스타터 기동 스크립트 (Windows)
cd /d "%~dp0.."
echo -- 1) 의존성 확인
python -m pip install -q -r requirements.txt
echo -- 2) .env 확인
if not exist .env copy .env.example .env
echo -- 3) 파싱 . 청킹 . 색인
python -W ignore src\rag.py bootstrap
echo.
echo 완료.  python src\rag.py ask "나루 ELS 제417회의 중도해지 수수료율은?"
