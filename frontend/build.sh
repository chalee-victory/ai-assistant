#!/bin/bash
# Vercel 빌드 스크립트
# Vercel 환경변수 API_BASE_URL 값을 config.js로 출력한다.
# Vercel 프로젝트 설정 > Build Command: bash build.sh
# Vercel 프로젝트 설정 > Output Directory: . (현재 디렉터리)

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
echo "window.API_BASE_URL = \"${API_BASE_URL}\";" > config.js
echo "[build.sh] config.js 생성 완료 (API_BASE_URL=${API_BASE_URL})"
