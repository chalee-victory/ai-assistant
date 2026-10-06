"""
firebase.py — Firestore 클라이언트 초기화

환경변수 우선순위:
  1. FIREBASE_KEY_PATH  : 로컬 개발 — 서비스 계정 JSON 파일 경로 (C:/keys/...)
  2. FIREBASE_SERVICE_ACCOUNT_JSON : 배포 환경 — JSON 내용을 문자열로 주입

앱 모듈이 이 파일을 import 하면 자동으로 초기화되며,
db 객체를 통해 Firestore 컬렉션에 접근한다.
"""

import json
import firebase_admin
from firebase_admin import credentials, firestore

from config import FIREBASE_KEY_PATH, FIREBASE_SERVICE_ACCOUNT_JSON


def _init_app() -> None:
    """Firebase 앱을 한 번만 초기화한다 (중복 초기화 방지)."""
    if firebase_admin._apps:
        return  # 이미 초기화됨

    if FIREBASE_KEY_PATH:
        # 로컬: 파일 경로로 인증
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
    else:
        # 배포: 환경변수의 JSON 문자열로 인증
        service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(service_account_info)

    firebase_admin.initialize_app(cred)


_init_app()

# 앱 전체에서 이 객체를 import해서 사용한다
db: firestore.Client = firestore.client()
