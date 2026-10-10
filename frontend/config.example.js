// config.example.js — 로컬 개발용 설정 예시
// 이 파일을 복사해 config.js로 만드세요:
//   cp config.example.js config.js   (macOS/Linux)
//   copy config.example.js config.js (Windows)
//
// config.js는 .gitignore에 포함되어 있으므로 커밋되지 않습니다.
// Vercel 배포 시에는 build.sh가 환경변수 API_BASE_URL로 config.js를 자동 생성합니다.

window.API_BASE_URL = "http://localhost:8000";
