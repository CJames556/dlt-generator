#!/usr/bin/env python3
"""
fetch_lottery.py - 大乐透开奖数据自动抓取脚本
从体彩官方API获取最近10期开奖结果，写入 lottery_data.json
供 GitHub Actions 定时调用，网页端通过同域 fetch 读取此JSON文件。
"""

import urllib.request
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# 北京时间
BJT = timezone(timedelta(hours=8))

API_URL = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=85&provinceId=0&pageSize=10&isVerify=1&pageNo=1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.sporttery.cn/jc/jsq/dlt/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

OUTPUT_FILE = "lottery_data.json"


def fetch_data():
    """从体彩官方API获取最近10期大乐透开奖数据"""
    req = urllib.request.Request(API_URL, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=20)
    raw = resp.read()
    data = json.loads(raw)

    if not data.get("success") or not data.get("value"):
        raise ValueError(f"API返回异常: success={data.get('success')}")

    items = data["value"]["list"]
    draws = []
    for item in items:
        no = str(item["lotteryDrawNum"])
        dt = str(item["lotteryDrawTime"])
        result = str(item["lotteryDrawResult"]).strip()

        # 格式: "01 04 10 23 25 01 12"  → 前5个前区，后2个后区
        nums = result.split()
        if len(nums) != 7:
            print(f"  [警告] {no} 期号码数量异常: {result}")
            continue

        front = [int(n) for n in nums[:5]]
        back = [int(n) for n in nums[5:7]]

        # 验证范围
        if not all(1 <= n <= 35 for n in front):
            print(f"  [警告] {no} 期前区号码超出范围: {front}")
            continue
        if not all(1 <= n <= 12 for n in back):
            print(f"  [警告] {no} 期后区号码超出范围: {back}")
            continue

        draws.append({"no": no, "dt": dt, "f": front, "b": back})

    if len(draws) == 0:
        raise ValueError("未能解析出任何有效开奖数据")

    return draws


def main():
    print(f"=== 大乐透数据抓取 {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')} BJT ===")

    # 1. 获取新数据
    print("正在从体彩官方API获取数据...")
    try:
        new_draws = fetch_data()
    except Exception as e:
        print(f"[错误] 获取数据失败: {e}")
        sys.exit(1)

    print(f"成功获取 {len(new_draws)} 期数据:")
    for d in new_draws:
        front_str = " ".join(f"{n:02d}" for n in d["f"])
        back_str = " ".join(f"{n:02d}" for n in d["b"])
        print(f"  {d['no']} ({d['dt']}): {front_str} + {back_str}")

    # 2. 读取现有数据（如果存在）
    old_draws = None
    old_latest = ""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            old_draws = old_data.get("draws", [])
            old_latest = old_data.get("latestIssue", "")
            print(f"现有数据最新期号: {old_latest}")
        except Exception:
            pass

    # 3. 比较是否有新数据
    new_latest = new_draws[0]["no"]
    if old_latest == new_latest:
        print(f"数据未变化（最新期号 {new_latest}），无需更新，跳过写入")
        print("::set-output name=changed::false")
        return

    # 4. 写入新数据
    output = {
        "lastUpdated": datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S"),
        "latestIssue": new_latest,
        "latestDate": new_draws[0]["dt"],
        "draws": new_draws,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n已写入 {OUTPUT_FILE}")
    print(f"最新期号: {new_latest} ({new_draws[0]['dt']})")
    print(f"更新时间: {output['lastUpdated']}")

    # 如果有新期号，打印变化
    if old_draws:
        old_nos = {d["no"] for d in old_draws}
        new_items = [d for d in new_draws if d["no"] not in old_nos]
        if new_items:
            print(f"\n新增 {len(new_items)} 期:")
            for d in new_items:
                front_str = " ".join(f"{n:02d}" for n in d["f"])
                back_str = " ".join(f"{n:02d}" for n in d["b"])
                print(f"  ★ {d['no']} ({d['dt']}): {front_str} + {back_str}")

    # 告知 GitHub Actions 需要提交
    print("::set-output name=changed::true")


if __name__ == "__main__":
    main()
