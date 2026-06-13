import json, os

text_dir = "/home/user/zaini-case-audit/zaini_case_audit_output/staging/text"
parts_dir = "/home/user/zaini-case-audit/zaini_case_audit_output/staging/parts"
os.makedirs(text_dir, exist_ok=True)
os.makedirs(parts_dir, exist_ok=True)

records = []

# Root folders
records.append({
    "id": "1huYi1aeh7af3Je8Yp2-dpxu2ZO4uMoR4",
    "title": "اعادة فتح الشكوى الثانية برقم 199058 ـ في 13-11-1445 ـ 21-05-2024",
    "mimeType": "application/vnd.google-apps.folder",
    "fileExtension": None,
    "fileSize": None,
    "createdTime": "2026-04-07T11:17:45.724Z",
    "modifiedTime": "2026-04-07T11:17:45.724Z",
    "viewUrl": "https://drive.google.com/drive/folders/1huYi1aeh7af3Je8Yp2-dpxu2ZO4uMoR4",
    "owner": "anwar.bahmishan@ozco.com",
    "parentId": "1MqvRb940DF0vLBXP66oucVVtDaDmo1nU",
    "parent_path": "اعادة فتح الشكوى الثانية برقم 199058 ـ في 13-11-1445 ـ 21-05-2024",
    "is_folder": True,
    "text_chars": None,
    "text_file": None,
    "read_status": None,
    "read_error": None,
})

records.append({
    "id": "1dJBxUfBSNi1FwQEPaPTmTiI9JnhYAcWn",
    "title": "الاحكام الصادرة في القضية - 42824717",
    "mimeType": "application/vnd.google-apps.folder",
    "fileExtension": None,
    "fileSize": None,
    "createdTime": "2026-04-07T11:17:45.727Z",
    "modifiedTime": "2026-04-07T11:17:45.727Z",
    "viewUrl": "https://drive.google.com/drive/folders/1dJBxUfBSNi1FwQEPaPTmTiI9JnhYAcWn",
    "owner": "anwar.bahmishan@ozco.com",
    "parentId": "1MqvRb940DF0vLBXP66oucVVtDaDmo1nU",
    "parent_path": "الاحكام الصادرة في القضية - 42824717",
    "is_folder": True,
    "text_chars": None,
    "text_file": None,
    "read_status": None,
    "read_error": None,
})

records.append({
    "id": "1WH6uCngO7Jz841kHxrUFjGck5RbHiv-B",
    "title": "مذكرة التماس من المحامي الشهري بتاريخ 13-07-1445- 42824717",
    "mimeType": "application/vnd.google-apps.folder",
    "fileExtension": None,
    "fileSize": None,
    "createdTime": "2026-04-07T11:17:45.748Z",
    "modifiedTime": "2026-04-07T11:17:45.748Z",
    "viewUrl": "https://drive.google.com/drive/folders/1WH6uCngO7Jz841kHxrUFjGck5RbHiv-B",
    "owner": "anwar.bahmishan@ozco.com",
    "parentId": "1MqvRb940DF0vLBXP66oucVVtDaDmo1nU",
    "parent_path": "مذكرة التماس من المحامي الشهري بتاريخ 13-07-1445- 42824717",
    "is_folder": True,
    "text_chars": None,
    "text_file": None,
    "read_status": None,
    "read_error": None,
})

# The PDF file under root 2
fid = "1uPbyNqN995l9ZPBqWVmINd-m_7ByD-48"
text_path = os.path.join(text_dir, fid + ".txt")
text_chars = len(open(text_path, encoding="utf-8").read())
records.append({
    "id": fid,
    "title": "حكم نهائي الشيخ اسامة زيني ـ 42824717 - 25-08-1445 رفض الالتماس.pdf",
    "mimeType": "application/pdf",
    "fileExtension": "pdf",
    "fileSize": "358519",
    "createdTime": "2026-04-07T11:17:49.962Z",
    "modifiedTime": "2024-05-05T07:28:49Z",
    "viewUrl": "https://drive.google.com/file/d/1uPbyNqN995l9ZPBqWVmINd-m_7ByD-48/view?usp=drivesdk",
    "owner": "anwar.bahmishan@ozco.com",
    "parentId": "1dJBxUfBSNi1FwQEPaPTmTiI9JnhYAcWn",
    "parent_path": "الاحكام الصادرة في القضية - 42824717",
    "is_folder": False,
    "text_chars": text_chars,
    "text_file": text_path,
    "read_status": "ok" if text_chars >= 20 else "empty",
    "read_error": None,
})

with open(os.path.join(parts_dir, "agent_b.jsonl"), "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print("records:", len(records), "text_chars:", text_chars)
