from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TypedDict, cast

# Type alias for raw JSON dicts from json.load
type JsonDict = dict[str, object]


class _ForwardInfo(TypedDict, total=False):
    from_name: str | None
    from_id: int | None
    date: str | None
    post_author: str | None


class MessageData(TypedDict, total=False):
    id: int
    chat_id: int
    date: str | None
    text: str | None
    grouped_id: int | None
    forward: _ForwardInfo | None
    reply_to: int | None
    folder: str


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Saved Messages Backup</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #e7ebf0;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            width: 100%;
            max-width: 800px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
        }}
        .message {{
            margin-bottom: 20px;
            padding: 10px 15px;
            border-radius: 12px;
            background-color: white;
            position: relative;
            word-wrap: break-word;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }}
        .message.forwarded {{
            border-left: 3px solid #3390ec;
            background-color: #f8fbff;
        }}
        .message-header {{
            font-size: 0.8em;
            color: #888;
            margin-bottom: 5px;
        }}
        .message-date {{
            font-size: 0.7em;
            color: #aaa;
            text-align: right;
            margin-top: 5px;
        }}
        .media {{
            margin-top: 10px;
        }}
        .media img {{
            max-width: 100%;
            border-radius: 5px;
        }}
        .media video {{
            max-width: 100%;
            border-radius: 5px;
        }}
        .media audio {{
            width: 100%;
        }}
        .file-link {{
            display: inline-block;
            margin-top: 5px;
            padding: 5px 10px;
            background-color: #3390ec;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-size: 0.9em;
        }}
        .telegraph-link {{
            display: block;
            margin-top: 10px;
            padding: 10px;
            background-color: #f0f7ff;
            border: 1px solid #cce5ff;
            border-radius: 5px;
            text-decoration: none;
            color: #004085;
        }}
        .album-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }}
        .album-item {{
            flex: 1 1 200px;
            max-width: 100%;
        }}
        .album-item img, .album-item video {{
            width: 100%;
            height: auto;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Saved Messages</h1>
        <div id="messages">
            {messages_html}
        </div>
    </div>
</body>
</html>
"""

IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "webp")
VIDEO_EXTS = ("mp4", "webm", "mov")
AUDIO_EXTS = ("mp3", "ogg", "wav", "m4a")
SKIP_FILES = ("meta.json", "message.txt")


def _parse_message_data(raw: object, folder_name: str) -> MessageData | None:
    """Validate and parse raw JSON data into a MessageData dict."""
    if not isinstance(raw, dict):
        return None
    d = cast(JsonDict, raw)
    result = MessageData()
    raw_id = d.get("id")
    if isinstance(raw_id, int):
        result["id"] = raw_id
    raw_chat_id = d.get("chat_id")
    if isinstance(raw_chat_id, int):
        result["chat_id"] = raw_chat_id
    raw_date = d.get("date")
    if isinstance(raw_date, str) or raw_date is None:
        result["date"] = raw_date
    raw_text = d.get("text")
    if isinstance(raw_text, str) or raw_text is None:
        result["text"] = raw_text
    raw_grouped = d.get("grouped_id")
    if isinstance(raw_grouped, int) or raw_grouped is None:
        result["grouped_id"] = raw_grouped
    raw_forward = d.get("forward")
    if isinstance(raw_forward, dict):
        result["forward"] = cast(_ForwardInfo, cast(object, raw_forward))
    elif raw_forward is None:
        result["forward"] = None
    raw_reply = d.get("reply_to")
    if isinstance(raw_reply, int) or raw_reply is None:
        result["reply_to"] = raw_reply
    result["folder"] = folder_name
    return result


def _render_media_file(
    file_name: str,
    msg_folder: str,
    is_album: bool,
) -> str:
    """Render HTML for a single media file."""
    file_rel_path = f"{msg_folder}/{file_name}"
    ext = file_name.rsplit(".", maxsplit=1)[-1].lower()
    div_class = "album-item" if is_album else "media"

    if ext in IMAGE_EXTS:
        return f'<div class="{div_class}"><img src="{file_rel_path}" alt="Image"></div>'
    if ext in VIDEO_EXTS:
        return f'<div class="{div_class}"><video controls src="{file_rel_path}"></video></div>'
    if ext in AUDIO_EXTS:
        return (
            f'<div class="media"><audio controls src="{file_rel_path}"></audio></div>'
        )
    return f'<div class="media"><a href="{file_rel_path}" class="file-link">Download {file_name}</a></div>'


def _render_linked_media(
    lf_name: str,
    msg_folder: str,
    linked_item: str,
) -> str:
    """Render HTML for a media file inside a linked message folder."""
    lf_rel_path = f"{msg_folder}/{linked_item}/{lf_name}"
    lext = lf_name.rsplit(".", maxsplit=1)[-1].lower()

    if lext in IMAGE_EXTS:
        return f'<div class="media"><img src="{lf_rel_path}" alt="Image"></div>'
    if lext in VIDEO_EXTS:
        return f'<div class="media"><video controls src="{lf_rel_path}"></video></div>'
    if lext in AUDIO_EXTS:
        return f'<div class="media"><audio controls src="{lf_rel_path}"></audio></div>'
    return f'<div class="media"><a href="{lf_rel_path}" class="file-link">Download {lf_name}</a></div>'


def _should_skip_file(file_name: str) -> bool:
    """Check if a file should be skipped when scanning for media."""
    return (
        file_name in SKIP_FILES
        or file_name.startswith("telegraph_")
        or file_name.startswith("linked_")
        or file_name.startswith(".")
    )


def _format_date(date_str: str | None) -> str:
    """Format an ISO date string for display."""
    if date_str:
        try:
            date_obj = datetime.fromisoformat(date_str)
            return date_obj.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return date_str
    return "Unknown date"


def _sort_key(msg: MessageData) -> tuple[str, int]:
    """Sort key for messages: by date then by id."""
    return (msg.get("date") or "", msg.get("id", 0))


def generate_html(
    base_path: str = "./downloads",
    output_file: str = "index.html",
) -> None:
    messages: list[MessageData] = []

    if not os.path.exists(base_path):
        print(f"Directory {base_path} does not exist.")
        return

    # Walk through the downloads directory
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path) and not item.startswith("."):
            meta_path = os.path.join(item_path, "meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)  # pyright: ignore[reportAny]
                    parsed = _parse_message_data(raw_data, item)  # pyright: ignore[reportAny]
                    if parsed is not None:
                        messages.append(parsed)
                except Exception as e:
                    print(f"Error reading {meta_path}: {e}")

    # Sort messages by date
    messages.sort(key=_sort_key)

    # Group messages by grouped_id
    grouped_list: list[list[MessageData]] = []
    current_group: list[MessageData] = []
    last_grouped_id: int | None = None

    for msg in messages:
        gid = msg.get("grouped_id")
        if gid is not None:
            if gid == last_grouped_id:
                current_group.append(msg)
            else:
                if current_group:
                    grouped_list.append(current_group)
                current_group = [msg]
                last_grouped_id = gid
        else:
            if current_group:
                grouped_list.append(current_group)
                current_group = []
                last_grouped_id = None
            grouped_list.append([msg])

    if current_group:
        grouped_list.append(current_group)

    messages_html = ""
    for group in grouped_list:
        # We take primary info from the first message in group
        main_msg = group[0]
        msg_id = main_msg.get("id", 0)
        date_str = main_msg.get("date")
        display_date = _format_date(date_str)

        # Captions can be in any message of the group, find the first non-empty one
        text = ""
        for msg in group:
            msg_text = msg.get("text")
            if msg_text:
                text = msg_text.replace("\n", "<br>")
                break

        forward = main_msg.get("forward")

        msg_class = "message"
        header_html = ""
        if forward:
            msg_class += " forwarded"
            from_name: str | int = (
                forward.get("from_name") or forward.get("from_id") or "Unknown"
            )
            header_html = (
                f'<div class="message-header">Forwarded from {from_name}</div>'
            )

        media_html = ""
        is_album = len(group) > 1

        if is_album:
            media_html += '<div class="album-grid">'

        for msg in group:
            msg_folder = msg.get("folder", "")
            folder_path = os.path.join(base_path, msg_folder)

            # Find media files in the folder
            for file_name in os.listdir(folder_path):
                if _should_skip_file(file_name):
                    continue
                media_html += _render_media_file(file_name, msg_folder, is_album)

            # Check for Telegraph folders
            for dir_item in os.listdir(folder_path):
                if dir_item.startswith("telegraph_"):
                    telegraph_path = f"{msg_folder}/{dir_item}/index.html"
                    media_html += (
                        f'<a href="{telegraph_path}" class="telegraph-link">'
                        f"Telegraph Page: {dir_item}</a>"
                    )

            # Check for linked messages
            for dir_item in os.listdir(folder_path):
                if dir_item.startswith("linked_"):
                    linked_meta_path = os.path.join(folder_path, dir_item, "meta.json")
                    if os.path.exists(linked_meta_path):
                        with open(linked_meta_path, "r", encoding="utf-8") as f:
                            linked_raw = json.load(f)  # pyright: ignore[reportAny]

                        linked_text = ""
                        if isinstance(linked_raw, dict):
                            linked_dict = cast(JsonDict, linked_raw)
                            raw_linked_text = linked_dict.get("text", "")
                            if isinstance(raw_linked_text, str) and raw_linked_text:
                                linked_text = raw_linked_text.replace("\n", "<br>")

                        media_html += (
                            '<div class="message forwarded" '
                            'style="margin-top: 10px; font-size: 0.9em;">'
                        )
                        media_html += '<div class="message-header">Linked Content</div>'
                        media_html += f"<div>{linked_text}</div>"

                        # Media in linked folder
                        linked_folder_full = os.path.join(folder_path, dir_item)
                        for lf_name in os.listdir(linked_folder_full):
                            if lf_name in SKIP_FILES or lf_name.startswith("."):
                                continue
                            media_html += _render_linked_media(
                                lf_name, msg_folder, dir_item
                            )
                        media_html += "</div>"

        if is_album:
            media_html += "</div>"

        messages_html += f"""
        <div class="{msg_class}" id="msg-{msg_id}">
            {header_html}
            <div class="message-text">{text}</div>
            {media_html}
            <div class="message-date">#{msg_id} - {display_date}</div>
        </div>
        """

    full_html = HTML_TEMPLATE.format(messages_html=messages_html)

    final_path = os.path.join(base_path, output_file)
    tmp_path = final_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            _ = f.write(full_html)
        os.replace(tmp_path, final_path)
        print(f"HTML backup generated at {final_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"Error generating HTML: {e}")


if __name__ == "__main__":
    generate_html()
