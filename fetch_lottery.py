#!/usr/bin/env python3
"""
fetch_lottery.py - 大乐透开奖数据自动抓取脚本（多源备用）
数据源1: 体彩官方API (sporttery.cn) - 国内可用
数据源2: 500.com HTML页面 - 备用，国际可用
供 GitHub Actions 定时调用，网页端通过同域 fetch 读取 lottery_data.json
"""

import urllib.request
import json
import re
import os
import sys
import io
from datetime import datetime, timezone, timedelta

# 解决 Windows 编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BJT = timezone(timedelta(hours=8))

OUTPUT_FILE = "lottery_data.json"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_from_sporttery():
    """数据源1: 体彩官方API"""
    url = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=85&provinceId=0&pageSize=10&isVerify=1&pageNo=1"
    headers = {
        **BROWSER_HEADERS,
        "Referer": "https://www.sporttery.cn/jc/jsq/dlt/",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }

    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=20)
    data = json.loads(resp.read())

    if not data.get("success") or not data.get("value"):
        raise ValueError(f"API返回异常: success={data.get('success')}")

    items = data["value"]["list"]
    draws = []
    for item in items:
        no = str(item["lotteryDrawNum"])
        dt = str(item["lotteryDrawTime"])
        result = str(item["lotteryDrawResult"]).strip()
        nums = result.split()
        if len(nums) != 7:
            continue
        front = [int(n) for n in nums[:5]]
        back = [int(n) for n in nums[5:7]]
        if not all(1 <= n <= 35 for n in front) or not all(1 <= n <= 12 for n in back):
            continue
        draws.append({"no": no, "dt": dt, "f": front, "b": back})

    if not draws:
        raise ValueError("未能解析出有效数据")
    return draws, "体彩官方API"


def fetch_from_500com():
    """数据源2: 500.com HTML页面解析"""
    url = "https://datachart.500.com/dlt/history/newinc/history.php?limit=10&sort=0"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    resp = urllib.request.urlopen(req, timeout=20)
    raw = resp.read()

    # 500.com 使用 GBK 编码
    html = raw.decode('gbk', errors='replace')

    # 解析数据行 (class="t_tr1")
    rows = re.findall(r'<tr class="t_tr1">(.*?)</tr>', html, re.DOTALL)
    draws = []

    for row in rows:
        # 移除 HTML 注释（500.com 有注释掉的列）
        row = re.sub(r'<!--.*?-->', '', row, flags=re.DOTALL)
        
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        clean_tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]

        # 跳过表头行
        if len(clean_tds) < 10:
            continue

        # 结构: [issue, f1, f2, f3, f4, f5, b1, b2, ...prize..., date]
        issue = clean_tds[0]
        if not re.match(r'^\d{5}$', issue):
            continue

        try:
            front = [int(clean_tds[i]) for i in range(1, 6)]
            back = [int(clean_tds[i]) for i in range(6, 8)]
        except (ValueError, IndexError):
            continue

        if not all(1 <= n <= 35 for n in front) or not all(1 <= n <= 12 for n in back):
            continue

        # 最后一列是开奖日期
        dt = clean_tds[-1]
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', dt):
            # 如果日期格式不对，跳过
            continue

        draws.append({"no": issue, "dt": dt, "f": front, "b": back})

    if not draws:
        raise ValueError("500.com: 未能解析出有效数据")
    return draws, "500.com"


def main():
    print(f"=== 大乐透数据抓取 {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')} BJT ===")

    new_draws = None
    source_name = ""

    # 尝试数据源1: 体彩官方API
    print("\n[1] 尝试体彩官方API...")
    try:
        new_draws, source_name = fetch_from_sporttery()
        print(f"  [成功] 通过体彩官方API获取 {len(new_draws)} 期数据")
    except Exception as e:
        print(f"  [失败] {e}")

    # 尝试数据源2: 500.com
    if not new_draws:
        print("\n[2] 尝试 500.com...")
        try:
            new_draws, source_name = fetch_from_500com()
            print(f"  [成功] 通过 500.com 获取 {len(new_draws)} 期数据")
        except Exception as e:
            print(f"  [失败] {e}")

    if not new_draws:
        print("\n[错误] 所有数据源均失败！")
        sys.exit(1)

    # 打印获取的数据
    print(f"\n数据来源: {source_name}")
    print(f"共 {len(new_draws)} 期数据:")
    for d in new_draws:
        front_str = " ".join(f"{n:02d}" for n in d["f"])
        back_str = " ".join(f"{n:02d}" for n in d["b"])
        print(f"  {d['no']} ({d['dt']}): {front_str} + {back_str}")

    # 读取现有数据
    old_latest = ""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            old_latest = old_data.get("latestIssue", "")
            print(f"\n现有数据最新期号: {old_latest}")
        except Exception:
            pass

    # 比较是否有新数据
    new_latest = new_draws[0]["no"]
    if old_latest == new_latest:
        print(f"数据未变化（最新期号 {new_latest}），无需更新，跳过写入")
        print("::set-output name=changed::false")
        return

    # 写入新数据
    output = {
        "lastUpdated": datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S"),
        "latestIssue": new_latest,
        "latestDate": new_draws[0]["dt"],
        "source": source_name,
        "draws": new_draws,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n已写入 {OUTPUT_FILE}")
    print(f"最新期号: {new_latest} ({new_draws[0]['dt']})")
    print(f"更新时间: {output['lastUpdated']}")
    print(f"数据来源: {source_name}")
    print("::set-output name=changed::true")


if __name__ == "__main__":
    main()
