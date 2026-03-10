import asyncio
import os

import httpx
from datetime import datetime, timezone, timedelta
from typing import List
import csv

API_BASE = os.environ.get("API_BASE", "http://127.0.0.63:8539/api/")


class UserInfo:
    def __init__(
        self, jid: str, authorname: str, register_time: str = None, notes_count: int = 0
    ):
        self.jid = jid
        self.authorname = authorname
        self.register_time = register_time
        self.notes_count = notes_count
        self.is_exact_match = False


async def search_users_api(
    client: httpx.AsyncClient, keyword: str, limit: int = 10000
) -> List[UserInfo]:
    """通过 API 搜索用户"""
    print(f"🔎 正在搜索包含 '{keyword}' 的用户...")

    try:
        r = await client.get(
            API_BASE + "search", params={"q": keyword, "limit": limit}, timeout=30
        )
        r.raise_for_status()
        results = r.json()

        users = []
        keyword_lower = keyword.lower()

        for item in results:
            user = UserInfo(item["Jid"], item["Name"])
            # 标记精确匹配
            if user.authorname.lower() == keyword_lower:
                user.is_exact_match = True
            users.append(user)

        print(f"✅ 找到 {len(users)} 个匹配的用户\n")
        return users

    except Exception as e:
        print(f"❌ 搜索出错: {e}")
        return []


async def get_user_details(client: httpx.AsyncClient, user: UserInfo) -> UserInfo:
    """获取单个用户的详细信息"""
    try:
        r = await client.get(API_BASE + "notes", params={"jid": user.jid}, timeout=30)

        if r.status_code == 200:
            notes = r.json()
            if notes and len(notes) > 0:
                user.notes_count = len(notes)
                # 从第一个作品中获取注册时间
                if "payload" in notes[0] and "registertime" in notes[0]["payload"]:
                    user.register_time = notes[0]["payload"]["registertime"]

        return user

    except Exception as e:
        return user


def format_register_time(register_time: str) -> str:
    """格式化注册时间"""
    if not register_time:
        return "未知"
    try:
        # 假设 registertime 是时间戳格式（秒）
        if register_time.isdigit():
            timestamp = int(register_time)
            # 如果是毫秒时间戳，转换为秒
            if timestamp > 10000000000:
                timestamp = timestamp // 1000
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            return dt.astimezone(timezone(timedelta(hours=8))).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        return register_time
    except Exception as e:
        return "解析失败"


async def fetch_all_user_details(
    client: httpx.AsyncClient, users: List[UserInfo]
) -> List[UserInfo]:
    """批量获取所有用户的详细信息"""
    total = len(users)
    print(f"📊 正在获取 {total} 个用户的详细信息...")

    tasks = [get_user_details(client, user) for user in users]
    results = await asyncio.gather(*tasks)

    print(f"✅ 获取完成！\n")
    return results


def display_results(users: List[UserInfo]):
    """排序并显示结果"""
    # 分组排序
    exact_matches = [u for u in users if u.is_exact_match]
    other_matches = [u for u in users if not u.is_exact_match]

    # 各自按作品数排序
    exact_matches.sort(key=lambda u: u.notes_count, reverse=True)
    other_matches.sort(key=lambda u: u.notes_count, reverse=True)

    # 合并
    sorted_users = exact_matches + other_matches

    # 打印
    print(f"{'=' * 120}")
    print(f"📊 搜索结果（精确匹配优先，按作品数排序）")
    print(f"{'=' * 120}")

    for user in sorted_users:
        exact_mark = "⭐" if user.is_exact_match else "  "
        register_time_str = format_register_time(user.register_time)
        display_name = (
            user.authorname[:20] + "..."
            if len(user.authorname) > 20
            else user.authorname
        )

        print(
            f"{exact_mark} 注册: {register_time_str} | 作品: {user.notes_count:4d} | JID: {user.jid} | {display_name}"
        )

    print(f"{'=' * 120}\n")

    return sorted_users


def save_results_to_csv(users: List[UserInfo], keyword: str):
    """将搜索结果保存到 CSV 文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"search_results_{keyword}_{timestamp}.csv"

    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["精确匹配", "用户名", "JID", "注册时间", "作品数"])

        for user in users:
            writer.writerow(
                [
                    "是" if user.is_exact_match else "否",
                    user.authorname,
                    user.jid,
                    format_register_time(user.register_time),
                    user.notes_count,
                ]
            )

    print(f"💾 搜索结果已保存到: {filename}\n")
    return filename


def print_summary(users: List[UserInfo]):
    """打印统计摘要"""
    exact_matches = [u for u in users if u.is_exact_match]
    users_with_works = [u for u in users if u.notes_count > 0]

    print(f"📈 统计摘要:")
    print(f"   总用户数: {len(users)}")
    print(f"   精确匹配: {len(exact_matches)}")
    print(f"   有作品的用户: {len(users_with_works)}")

    if users_with_works:
        total_works = sum(u.notes_count for u in users_with_works)
        avg_works = total_works / len(users_with_works)
        max_works_user = max(users_with_works, key=lambda u: u.notes_count)

        print(f"   总作品数: {total_works}")
        print(f"   平均作品数: {avg_works:.1f}")
        print(
            f"   最多作品: {max_works_user.notes_count} ({max_works_user.authorname})"
        )
    print()


async def export_user(jid: str):
    """提示如何导出用户"""
    print(f"\n{'=' * 80}")
    print(f"📦 准备导出用户")
    print(f"{'=' * 80}")
    print(f"\n💡 请运行以下命令:")
    print(f"   uv run takeout.py")
    print(f"\n   然后输入 JID: {jid}\n")


async def main():
    print("✨ 欢迎使用画吧用户搜索工具～")
    print("   (精确匹配优先，按作品数排序)\n")

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            # 获取搜索关键词
            keyword = input("🔍 请输入要搜索的用户名关键词（输入 q 退出）: ").strip()

            if keyword.lower() == "q":
                print("👋 再见啦～")
                break

            if not keyword:
                print("⚠️  关键词不能为空哦～\n")
                continue

            # 通过 API 搜索用户
            matched_users = await search_users_api(client, keyword)

            if not matched_users:
                print("😢 没有找到匹配的用户呢...\n")
                continue

            # 批量获取详细信息
            matched_users = await fetch_all_user_details(client, matched_users)

            # 排序并显示结果
            sorted_users = display_results(matched_users)

            # 打印统计摘要
            print_summary(sorted_users)

            # 更新 matched_users 为排序后的结果
            matched_users = sorted_users

            print(f"{'-' * 80}\n")


if __name__ == "__main__":
    asyncio.run(main())
