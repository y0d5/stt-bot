# STT Bot — Whisper API + Telegram

## 파일 구조

```
stt-bot/
├── bot.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 배포 절차 (Railway)

### 1단계 — 새 텔레그램 봇 만들기

1. 텔레그램에서 @BotFather 검색
2. `/newbot` 입력
3. 봇 이름 입력 (예: YoungSTT)
4. 봇 username 입력 (예: young_stt_bot)
5. 발급된 **토큰** 복사해 두기

---

### 2단계 — GitHub에 업로드

1. GitHub에서 새 repository 생성 (예: `stt-bot`)
2. 세 파일 업로드: `bot.py`, `requirements.txt`, `Dockerfile`

---

### 3단계 — Railway 새 서비스 추가

1. railway.app 접속 → 기존 프로젝트 클릭
2. **+ New Service** → **GitHub Repo** 선택
3. `stt-bot` repository 선택

---

### 4단계 — Railway Variables 설정 (필수)

**절대 Config 파일 수정 금지 — Variables에만 추가**

| 변수명 | 값 |
|--------|-----|
| `TELEGRAM_BOT_TOKEN` | @BotFather에서 발급받은 토큰 |
| `OPENAI_API_KEY` | OpenAI API 키 (sk-...) |

---

### 5단계 — 배포 확인

Railway 로그에 아래 메시지가 뜨면 성공:

```
STT 봇 시작
```

---

## 사용법

| 동작 | 방법 |
|------|------|
| 음성 변환 | 텔레그램 마이크 버튼으로 녹음 후 전송 |
| 파일 변환 | m4a/mp3/wav 파일 첨부 전송 |
| 언어 변경 | `/lang en` `/lang ko` `/lang ja` `/lang auto` |

## 비용 추정

| 사용량 | Whisper 비용 |
|--------|-------------|
| 월 1,000분 | 약 $6 (8,400원) |
| 월 2,000분 | 약 $12 (16,800원) |
| 월 2,500분 | 약 $15 (21,000원) |
