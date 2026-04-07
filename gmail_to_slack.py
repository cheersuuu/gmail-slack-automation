import os
import base64
import re
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from slack_sdk import WebClient

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


def format_message(subject, sender, snippet):
    return (
        f"📩 액션 필요 메일\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*제목* : {subject}\n"
        f"*보낸 사람* : {sender}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*📝 요약*\n"
        f"{snippet}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


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

        message = format_message(subject, sender, snippet)

        slack.chat_postMessage(
            channel=my_user_id,
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
