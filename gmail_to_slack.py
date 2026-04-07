import os
import base64
import re
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from slack_sdk import WebClient
import requests

ACTION_LABEL_QUERY = 'label:"🔥 Action"'


def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def extract_body(message):
    payload = message.get("payload", {})

    def decode_part(part):
        data = part.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return ""

    def find_text(payload):
        mime_type = payload.get("mimeType", "")
        if mime_type == "text/plain":
            return decode_part(payload)
        if mime_type == "text/html":
            html = decode_part(payload)
            return re.sub(r"<[^>]+>", " ", html)
        for part in payload.get("parts", []):
            result = find_text(part)
            if result:
                return result
        return ""

    return find_text(payload).strip()


PROMPT_TEMPLATE = """다음 이메일을 분석하고 아래 형식 그대로 출력해. 다른 말은 절대 붙이지 마.

[Header rules]
- 액션이 필요하면: 📩 액션 필요 메일
- 답변 대기 중이면: 📩 대기 메일
- 참고용이면: 📩 참고 메일

[Importance rules]
- 높음: urgent, deadline soon, complaint, finance, inventory, shipment, live campaign issue
- 중간: review/reply needed but not urgent
- 낮음: informational only

[Category rules - 하나만 선택]
발주 / 출고 / 재고 / 정산 / 광고 / 일정 / 문의 / 클레임 / 보고 / 계약 / 요청 / 공유 / 기타

[Writing rules]
- 한국어로만 작성
- 짧고 실용적으로
- 마감일/할 일 누락 금지
- 암묵적 액션도 추론
- 할 일 없으면 "해야 할 일: 없음"
- 스레드에서 가장 최신 액션 우선

[출력 형식]
{{헤더}}
━━━━━━━━━━━━━━━━━━━━
*제목* : {subject}
*보낸 사람* : {sender}
━━━━━━━━━━━━━━━━━━━━
*📝 요약*
{{핵심 내용 2~3줄}}

*✅ 할 일*
- {{할 일 1}}
- {{할 일 2}}

*⏰ 마감*  {{마감일시, 없으면 "언급 없음"}}
*🔥 우선순위*  {{높음 / 중간 / 낮음}}
*🏷 카테고리*  {{카테고리}}
━━━━━━━━━━━━━━━━━━━━

이메일 내용:
제목: {subject}
발신자: {sender}

{body}"""


def summarize_email(subject, sender, body):
    api_key = os.environ["GEMINI_API_KEY"].strip()
    prompt = PROMPT_TEMPLATE.format(subject=subject, sender=sender, body=body[:3000])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload)
    if not response.ok:
        print(f"Gemini API 오류: {response.status_code} {response.text}")
        response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def main():
    gmail = get_gmail_service()

    results = (
        gmail.users()
        .messages()
        .list(userId="me", q=f"{ACTION_LABEL_QUERY} is:unread", maxResults=20)
        .execute()
    )
    messages = results.get("messages", [])

    if not messages:
        print("미읽음 Action 메일 없음.")
        return

    slack = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    my_user_id = slack.auth_test()["user_id"]
    dm_channel = slack.conversations_open(users=[my_user_id])["channel"]["id"]

    for msg in messages:
        full = (
            gmail.users()
            .messages()
            .get(userId="me", id=msg["id"], format="full")
            .execute()
        )

        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        subject = headers.get("Subject", "(제목 없음)")
        sender = headers.get("From", "Unknown")
        snippet = full.get("snippet", "").replace("&quot;", '"').replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")

        body = extract_body(full)
        message = summarize_email(subject, sender, body)

        slack.chat_postMessage(
            channel=dm_channel,
            text=message,
        )

        gmail.users().messages().modify(
            userId="me",
            id=msg["id"],
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

        print(f"처리 완료: {subject}")

    print(f"총 {len(messages)}개 메일 처리 완료.")


if __name__ == "__main__":
    main()
