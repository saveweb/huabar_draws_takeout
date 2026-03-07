import asyncio
from datetime import datetime, timedelta, timezone
import filetype
import glob as glob_mod
import json
import os
import urllib.parse

import httpx
from tqdm import tqdm

from url_type import (
    A, Q, B, W,
    get_urltype
)

API_BASE = "http://127.0.0.63:8539/api/"

def is_keyable(url: str)->bool:
    if not url:
        return False
    return get_urltype(url) in [A, Q]

def get_key(url: str)->str:
    parsed = urllib.parse.urlparse(url)
    return parsed.path.lstrip("/").replace("haowanlab/", "")

def detect_image_ext(file_path: str) -> str | None:
    """检测文件类型，如果是图片则返回扩展名（如 '.jpg'），否则返回 None。"""
    kind = filetype.guess(file_path)
    if kind and kind.mime.startswith("image/"):
        return f".{kind.extension}"
    return None

def find_existing_file(path: str) -> str | None:
    """查找 path 或 path.* 是否已存在，返回找到的路径或 None。"""
    if os.path.exists(path):
        return path
    matches = glob_mod.glob(path + ".*")
    return matches[0] if matches else None

def write_user_bak_meta(jid: str, notes: list[dict]):
    usr_dir = jid.split('@')[0]
    os.makedirs(f'user_backups/{usr_dir}', exist_ok=True)

    with open(f'user_backups/{usr_dir}/notes.json', 'w') as f:
        f.write(json.dumps(notes, ensure_ascii=False, indent=2))

async def download_to_bak(sem:asyncio.Semaphore, client:httpx.AsyncClient, url, jid, key):
    usr_dir = jid.split('@')[0]
    path = f'user_backups/{usr_dir}/notes_data/{key}'
    if find_existing_file(path):
        return
    os.makedirs(f'user_backups/{usr_dir}/notes_data/', exist_ok=True)
    async with sem:
        r = await client.get(url, follow_redirects=True)
        r.raise_for_status()
        with open(path, 'wb') as f:
            f.write(r.content)
        ext = detect_image_ext(path)
        if ext:
            os.rename(path, path + ext)

async def get_zipname(client:httpx.AsyncClient, key:str):
    # qiniu-draw-20240127-072800.3565.zip
    # ali-draw-20240127-072800.3565.zip
    r = await client.get(API_BASE+"get_zipname", params={"key": key})
    r_json = r.json()
    if 'error' in r_json:
        print(r_json)
        return None
    return r_json["zipname"]

def zipname2identifier(zipname:str):
    # qiniu-draw-20240127-072800.3565.zip
    # ali-draw-20240127-072800.3565.zip
    # ->>
    # huabar_ali-draw-20240130-00
    # huabar_qiniu-draw-20240130-00
    sp = zipname.split('-')
    sp[3] = sp[3][:2]
    return 'huabar_' + '-'.join(sp)

def post_process(jid: str):
        # cd user_backups/$jid && pwd && pandoc --from markdown --to html notes.md -s > notes.html
    import subprocess
    usr_dir = jid.split('@')[0]
    subprocess.run(['pandoc', f'user_backups/{usr_dir}/notes.md', '--standalone', '--output', f'user_backups/{usr_dir}/notes.html'], check=True)
    # rm ${jid}.zip
    if os.path.exists(f'user_backups/{usr_dir}.zip'):
        os.unlink(f'user_backups/{usr_dir}.zip')
    # zip -r $jid $jid
    subprocess.run(['zip', '-r', f'user_backups/{usr_dir}.zip', f'user_backups/{usr_dir}'], check=True)

    print(f"备份预览: https://huabar-takeout-preview.saveweb.org/{usr_dir}/notes.html")
    print(f"备份: https://huabar-takeout-preview.saveweb.org/{usr_dir}.zip")
    print()
    print("您好。请尽快下载压缩包，链接将于数周后失效。祝好。")

    print("To clean up, run: rm -rf user_backups/*")




async def main():
    jid = input("jid: ") # zeg97iab-0@zhizhiyaya.com/HuaLiao
    from_local = input("from local notes.json? (y/n): [default: n]").strip().lower() == 'y'
    
    async with httpx.AsyncClient(timeout=60) as client:
        if from_local:
            with open(f'{jid.split("@")[0]}/notes.json', 'r') as f:
                notes = json.load(f)
        else:
            r = await client.get(API_BASE+"notes", params={"jid": jid})
            notes = r.json()
            write_user_bak_meta(jid, notes)
        await download_notes_data(client, jid, notes)
        gen_markdown(jid, notes)

    post_process(jid)

def gen_markdown(jid, notes):
    usr_dir = jid.split('@')[0]
    os.makedirs(f'user_backups/{usr_dir}', exist_ok=True)
    with open(f'user_backups/{usr_dir}/notes.md', 'w') as f:
        f.write(f"""\
# {notes[0]['payload']['authorname']} 的画吧作品备份

```
jid: {jid}
注册时间: {notes[0]['payload']['registertime']}
作品数: {len(notes)}
(作品详细元数据见 notes.json)
```
""")
        for note in notes:
            noteid       = note["payload"]["noteid"]
            noteossurl   = note["payload"]["noteossurl"]
            original_url = note["payload"]["original_url"]
            notename     = note["payload"]["notename"]
            notestatus   = note["payload"]["notestatus"]
            notebrief   = note["payload"]["notebrief"]
            notetime     = note["payload"]["notetime"]
            strokecount = note["payload"]["strokecount"] # 画笔数
            width = note["payload"]["width"]
            high = note["payload"]["high"]
            usedcbnum = note["payload"]["usedcbnum"] # 含 X 款自定义笔刷
            praise = note["payload"]["praise"] # 收到的投花数
            comnum = note["payload"]["comnum"] # 评论数
            f.write(f"""\
---

```
作品ID: {noteid}
上传时间: {datetime.fromtimestamp(notetime, tz=timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)
作品名: {notename}
作品状态: {"正常" if notestatus == 0 else "已删除" if notestatus == 2 else notestatus}
描述: {notebrief}
画笔数: {strokecount}
宽x高: {width}x{high}
自定义笔刷数: {usedcbnum}
投花数: {praise}
评论数: {comnum}
```

""")
            f.write("原图: ")
            if is_keyable(original_url):
                key = get_key(original_url)
                actual = find_existing_file(f'user_backups/{usr_dir}/notes_data/{key}')
                display_name = os.path.basename(actual) if actual else key
                f.write(f"![{key}](notes_data/{display_name})"+'{loading="lazy"}\n\n')
            else:
                f.write(f"不可用 ({original_url})\n\n")
            f.write("原始工程文件: \n")
            if is_keyable(noteossurl):
                key = get_key(noteossurl)
                f.write(f"[{key}](notes_data/{key})\n\n")
            else:
                f.write(f"不可用 ({noteossurl})\n\n")

async def download_notes_data(client, jid, notes):
    sem = asyncio.Semaphore(10)
    cors = []
    for note in notes:
        noteossurl   = note["payload"]["noteossurl"]
        original_url = note["payload"]["original_url"]
        for url_name, url in [("noteossurl", noteossurl), ("original_url", original_url)]:
            if not url:
                continue
            urltype = get_urltype(url)
            if urltype in [A, Q]:
                key = get_key(url)
                zipname = await get_zipname(client, key)
                if not zipname:
                    print(url, key, "木有ZIP包")
                    continue
                identifier = zipname2identifier(zipname)
                # https://archive.org/download/huabar_qiniu-draw-20240120-18/qiniu-draw-20240120-184331.3072.zip/qiniu%2F0a3aab2963b53de19fc043182cfeee0d
                # https://archive.org/download/huabar_ali-draw-20240130-00/ali-draw-20240130-000635.2413.zip/ali%2F0b9274cd8384cc3d936d2341c7f7bdbd.data
                ia_url = f"https://archive.org/download/{identifier}/{zipname}/{urltype}/{key}"
                cors.append(
                    download_to_bak(sem=sem, client=client, url=ia_url, jid=jid, key=key)
                )
            elif url == "http://huaba-operate.oss-cn-hangzhou.aliyuncs.com/deletepic.png":
                pass
            elif urltype == W:
                if url_name == "noteossurl":
                    continue
                if "notecontent" in url:
                    newurl = 'http://[TODOTODO]:5000/' + url.split("notecontent.oss-cn-hangzhou.aliyuncs.com/")[1] # TODO
                    cors.append(
                        download_to_bak(sem=sem, client=client, url=newurl, jid=jid, key=get_key(url))
                    )
                    continue
                assert False, url
            elif urltype == B:
                pass
            else:
                assert False, url
    
    if cors:
        with tqdm(total=len(cors), desc="Downloading") as pbar:
            for f in asyncio.as_completed(cors):
                await f
                pbar.update(1)


if __name__ == "__main__":
    asyncio.run(main())
