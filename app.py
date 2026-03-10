import asyncio
import json
import os

import httpx
import pandas as pd
import streamlit as st

from search import fetch_all_user_details, format_register_time, search_users_api
from takeout import (
    API_BASE,
    download_notes_data,
    gen_markdown,
    post_process,
    write_user_bak_meta,
)

st.title("画吧作品备份工具")

# ── 搜索 ──────────────────────────────────────────────
st.header("搜索用户")

keyword = st.text_input("用户名关键词", key="keyword")
if st.button("搜索") and keyword:
    async def _search():
        async with httpx.AsyncClient(timeout=60) as client:
            users = await search_users_api(client, keyword)
            return await fetch_all_user_details(client, users)

    with st.spinner("搜索中..."):
        users = asyncio.run(_search())

    exact = sorted([u for u in users if u.is_exact_match], key=lambda u: u.notes_count, reverse=True)
    other = sorted([u for u in users if not u.is_exact_match], key=lambda u: u.notes_count, reverse=True)
    st.session_state["search_results"] = exact + other

if "search_results" in st.session_state:
    users = st.session_state["search_results"]
    df = pd.DataFrame([{
        "精确匹配": "⭐" if u.is_exact_match else "",
        "用户名": u.authorname,
        "作品数": u.notes_count,
        "注册时间": format_register_time(u.register_time),
        "JID": u.jid,
    } for u in users])
    st.dataframe(df, use_container_width=True)

    options = [u.jid for u in users]
    selected = st.selectbox(
        "选择用户",
        options,
        format_func=lambda j: next(f"{u.authorname}（{u.notes_count} 作品）" for u in users if u.jid == j),
    )
    if st.button("填入导出"):
        st.session_state["export_jid"] = selected
        st.success(f"已填入：{selected}")

# ── 导出 ──────────────────────────────────────────────
st.header("导出备份")

jid = st.text_input("JID", value=st.session_state.get("export_jid", ""), key="export_jid_input")
from_local = st.checkbox("从本地 notes.json 加载（跳过 API 拉取）")

if st.button("开始导出") and jid:
    async def _export():
        async with httpx.AsyncClient(timeout=300) as client:
            if from_local:
                usr_dir = jid.split("@")[0]
                with open(f"user_backups/{usr_dir}/notes.json", "r") as f:
                    notes = json.load(f)
            else:
                r = await client.get(API_BASE + "notes", params={"jid": jid})
                notes = r.json()
                write_user_bak_meta(jid, notes)
            await download_notes_data(client, jid, notes)
            gen_markdown(jid, notes)

    with st.spinner("下载中（进度见终端）..."):
        asyncio.run(_export())

    post_process(jid)

    usr_dir = jid.split("@")[0]
    st.success("导出完成！")
    st.write(f"备份预览：https://huabar-takeout-preview.saveweb.org/{usr_dir}/notes.html")
    st.write(f"备份：https://huabar-takeout-preview.saveweb.org/{usr_dir}.zip")
    st.write("您好。请尽快下载压缩包，链接将于数周后失效。祝好。")
