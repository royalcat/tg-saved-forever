import json
import os
from datetime import datetime

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

def generate_html(base_path="./downloads", output_file="index.html"):
    messages = []
    
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
                        msg_data = json.load(f)
                        msg_data["folder"] = item
                        messages.append(msg_data)
                except Exception as e:
                    print(f"Error reading {meta_path}: {e}")

    # Sort messages by date
    messages.sort(key=lambda x: x.get("date", ""))

    messages_html = ""
    for msg in messages:
        msg_id = msg.get("id")
        date_str = msg.get("date")
        if date_str:
            try:
                date_obj = datetime.fromisoformat(date_str)
                display_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                display_date = date_str
        else:
            display_date = "Unknown date"

        text = msg.get("text", "")
        if text:
            text = text.replace("\n", "<br>")
        else:
            text = ""
            
        forward = msg.get("forward")
        
        msg_class = "message"
        header_html = ""
        if forward:
            msg_class += " forwarded"
            from_name = forward.get("from_name") or forward.get("from_id") or "Unknown"
            header_html = f'<div class="message-header">Forwarded from {from_name}</div>'

        # Find media files in the folder
        media_html = ""
        folder_path = os.path.join(base_path, msg["folder"])
        for file in os.listdir(folder_path):
            if file in ["meta.json", "message.txt"] or file.startswith("telegraph_") or file.startswith("linked_") or file.startswith("."):
                continue
            
            file_rel_path = f"{msg['folder']}/{file}"
            ext = file.split(".")[-1].lower()
            
            if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
                media_html += f'<div class="media"><img src="{file_rel_path}" alt="Image"></div>'
            elif ext in ["mp4", "webm", "mov"]:
                media_html += f'<div class="media"><video controls src="{file_rel_path}"></video></div>'
            elif ext in ["mp3", "ogg", "wav", "m4a"]:
                media_html += f'<div class="media"><audio controls src="{file_rel_path}"></audio></div>'
            else:
                media_html += f'<div class="media"><a href="{file_rel_path}" class="file-link">Download {file}</a></div>'

        # Check for Telegraph folders
        for item in os.listdir(folder_path):
            if item.startswith("telegraph_"):
                telegraph_path = f"{msg['folder']}/{item}/index.html"
                media_html += f'<a href="{telegraph_path}" class="telegraph-link">Telegraph Page: {item}</a>'

        # Check for linked messages
        linked_html = ""
        for item in os.listdir(folder_path):
            if item.startswith("linked_"):
                linked_meta_path = os.path.join(folder_path, item, "meta.json")
                if os.path.exists(linked_meta_path):
                    with open(linked_meta_path, "r", encoding="utf-8") as f:
                        linked_msg = json.load(f)
                        linked_text = linked_msg.get("text", "")
                        if linked_text:
                            linked_text = linked_text.replace("\n", "<br>")
                        else:
                            linked_text = ""
                            
                        linked_html += f'<div class="message forwarded" style="margin-top: 10px; font-size: 0.9em;">'
                        linked_html += f'<div class="message-header">Linked Content</div>'
                        linked_html += f'<div>{linked_text}</div>'
                        
                        # Media in linked folder
                        linked_folder_full = os.path.join(folder_path, item)
                        for lf in os.listdir(linked_folder_full):
                            if lf in ["meta.json", "message.txt"] or lf.startswith("."): continue
                            lf_rel_path = f"{msg['folder']}/{item}/{lf}"
                            lext = lf.split(".")[-1].lower()
                            if lext in ["jpg", "jpeg", "png", "gif", "webp"]:
                                linked_html += f'<div class="media"><img src="{lf_rel_path}" alt="Image"></div>'
                            elif lext in ["mp4", "webm", "mov"]:
                                linked_html += f'<div class="media"><video controls src="{lf_rel_path}"></video></div>'
                            elif lext in ["mp3", "ogg", "wav", "m4a"]:
                                linked_html += f'<div class="media"><audio controls src="{lf_rel_path}"></audio></div>'
                            else:
                                linked_html += f'<div class="media"><a href="{lf_rel_path}" class="file-link">Download {lf}</a></div>'
                        linked_html += '</div>'

        messages_html += f"""
        <div class="{msg_class}" id="msg-{msg_id}">
            {header_html}
            <div class="message-text">{text}</div>
            {media_html}
            {linked_html}
            <div class="message-date">#{msg_id} - {display_date}</div>
        </div>
        """

    full_html = HTML_TEMPLATE.format(messages_html=messages_html)
    
    with open(os.path.join(base_path, output_file), "w", encoding="utf-8") as f:
        f.write(full_html)
    
    print(f"HTML backup generated at {os.path.join(base_path, output_file)}")

if __name__ == "__main__":
    generate_html()
