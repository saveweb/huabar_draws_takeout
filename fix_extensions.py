import glob
import json
import os
import subprocess

import filetype

from takeout import detect_image_ext, gen_markdown


def fix_user(usr_dir: str):
    notes_data_dir = f"user_backups/{usr_dir}/notes_data"
    if not os.path.isdir(notes_data_dir):
        return

    renamed = 0
    for filepath in glob.glob(os.path.join(notes_data_dir, "*")):
        basename = os.path.basename(filepath)
        if "." in basename:
            continue
        ext = detect_image_ext(filepath)
        if ext:
            os.rename(filepath, filepath + ext)
            renamed += 1

    print(f"{usr_dir}: renamed {renamed} files")

    notes_json_path = f"user_backups/{usr_dir}/notes.json"
    if not os.path.exists(notes_json_path):
        print(f"  warning: {notes_json_path} not found, skipping markdown regeneration")
        return

    with open(notes_json_path, "r") as f:
        notes = json.load(f)

    jid = notes[0]["payload"]["jid"]
    gen_markdown(jid, notes)
    subprocess.run(
        ["pandoc", f"user_backups/{usr_dir}/notes.md", "--standalone",
         "--output", f"user_backups/{usr_dir}/notes.html"],
        check=True,
    )
    # repack zip
    if os.path.exists(f'user_backups/{usr_dir}.zip'):
        os.unlink(f'user_backups/{usr_dir}.zip')
    subprocess.run(['zip', '-r', f'user_backups/{usr_dir}.zip', f'user_backups/{usr_dir}'], check=True)
    print(f"  regenerated notes.md, notes.html and zip")


def main():
    if not os.path.isdir("user_backups"):
        print("user_backups/ directory not found")
        return

    for entry in sorted(os.listdir("user_backups")):
        path = os.path.join("user_backups", entry)
        if os.path.isdir(path) and not entry.endswith(".zip"):
            fix_user(entry)


if __name__ == "__main__":
    main()
