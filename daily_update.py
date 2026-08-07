#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小美丽 - 每日信息收集自动化脚本 (GitHub Actions 云端版)
每天北京时间 8:00 自动执行，收集 4 个板块数据，生成看板 HTML。
作为本地 WorkBuddy 自动化的云端备份方案。
数据源：aihot API + 头条热榜 + 百度热搜 + B站搜索API
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import re
import sys
import os
from datetime import datetime, timedelta, timezone

# ========== Configuration ==========
BEIJING_TZ = timezone(timedelta(hours=8))
BEIJING_NOW = datetime.now(BEIJING_TZ)
DATE_STR = f"{BEIJING_NOW.year}年{BEIJING_NOW.month}月{BEIJING_NOW.day}日"
WEEK_MAP = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
WEEK_STR = WEEK_MAP[BEIJING_NOW.weekday()]
DATE_SHORT = f"{BEIJING_NOW.year}-{BEIJING_NOW.month:02d}-{BEIJING_NOW.day:02d} {WEEK_STR}"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

# SSL context
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# HTTP headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}

# ========== HTTP Helper ==========
def fetch_url(url, headers=None, timeout=15):
    """Fetch URL content with error handling"""
    try:
        req = urllib.request.Request(url, headers=headers or HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "charset=gbk" in content_type.lower() or "charset=gb2312" in content_type.lower():
                return data.decode("gbk", errors="replace")
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("gbk", errors="replace")
    except Exception as e:
        print(f"  [WARN] Fetch failed: {url[:80]} - {e}", file=sys.stderr)
        return None

def fetch_json(url, headers=None, timeout=15):
    """Fetch URL and parse as JSON"""
    text = fetch_url(url, headers, timeout)
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return None

def clean_html(text):
    """Remove HTML tags from text"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return text.strip()

def format_play_count(n):
    """Format play count: 10000 -> 1.0万"""
    if n >= 100000000:
        return f"{n/100000000:.1f}亿"
    elif n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)

# ========== Data Fetching ==========

def fetch_aihot_news():
    """Fetch AI hot news from aihot API"""
    print("[1/6] Fetching AI hot news...")
    data = fetch_json("https://aihot.virxact.com/api/v1/dailies/latest")
    if not data:
        return []
    items = []
    sections = data.get("report", {}).get("sections", [])
    for section in sections:
        label = section.get("label", "")
        for item in section.get("items", []):
            items.append({
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "category": label,
                "url": item.get("url", ""),
            })
    print(f"  Got {len(items)} AI news items")
    return items[:7]

def fetch_toutiao_hot():
    """Fetch Toutiao hot board"""
    print("[2/6] Fetching Toutiao hot board...")
    data = fetch_json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    if not data:
        return []
    items = []
    for item in data.get("data", []):
        items.append({
            "title": item.get("Title", ""),
            "url": item.get("Url", ""),
            "hot": item.get("HotValue", 0),
            "label": item.get("Label", ""),
            "image": item.get("Image", ""),
        })
    items.sort(key=lambda x: x["hot"], reverse=True)
    print(f"  Got {len(items)} Toutiao hot items")
    return items

def fetch_baidu_hot():
    """Fetch Baidu hot search"""
    print("[3/6] Fetching Baidu hot search...")
    data = fetch_json("https://top.baidu.com/api/board?platform=pc&tab=realtime")
    if not data:
        return []
    items = []
    cards = data.get("data", {}).get("cards", [])
    for card in cards:
        for item in card.get("content", []):
            items.append({
                "title": item.get("word", ""),
                "desc": item.get("desc", ""),
                "url": item.get("url", ""),
                "hot": item.get("hotScore", 0),
                "rawUrl": item.get("rawUrl", ""),
            })
    items.sort(key=lambda x: int(x["hot"]) if str(x["hot"]).isdigit() else 0, reverse=True)
    print(f"  Got {len(items)} Baidu hot items")
    return items

def fetch_bilibili_videos():
    """Fetch office automation videos from Bilibili search"""
    print("[4/6] Fetching Bilibili videos...")
    keywords = [
        "Python自动化办公", "Excel教程", "RPA自动化",
        "AI办公工具", "Word教程", "PPT教程",
        "办公效率", "WPS教程",
    ]
    all_videos = []
    seen_bvids = set()
    for kw in keywords:
        encoded_kw = urllib.parse.quote(kw)
        url = f"https://api.bilibili.com/x/web-interface/search/all/v2?keyword={encoded_kw}&order=click&page=1"
        data = fetch_json(url, headers=BILI_HEADERS)
        if not data:
            continue
        results = data.get("data", {}).get("result", [])
        for r in results:
            if r.get("result_type") != "video":
                continue
            for v in r.get("data", []):
                bvid = v.get("bvid", "")
                if bvid in seen_bvids:
                    continue
                seen_bvids.add(bvid)
                title = clean_html(v.get("title", ""))
                play = v.get("play", 0) or 0
                all_videos.append({
                    "title": title,
                    "bvid": bvid,
                    "url": v.get("arcurl", "") or f"https://www.bilibili.com/video/{bvid}",
                    "author": v.get("author", ""),
                    "play": play,
                    "tag": clean_html(v.get("tag", "")),
                    "desc": v.get("description", ""),
                    "duration": v.get("duration", ""),
                })
    all_videos.sort(key=lambda x: x["play"], reverse=True)
    print(f"  Got {len(all_videos)} unique videos")
    return all_videos[:20]

def filter_news_by_keywords(items, keywords, exclude_keywords=None, limit=20, fallback_items=None):
    """Filter news items by keywords, pad with fallback if not enough"""
    result = []
    seen_titles = set()
    for item in items:
        title = item.get("title", "")
        desc = item.get("desc", item.get("summary", ""))
        text = title + " " + desc
        if any(kw in text for kw in keywords):
            if exclude_keywords and any(ek in text for ek in exclude_keywords):
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            result.append(item)
            if len(result) >= limit:
                break
    # Pad with fallback items if not enough
    if len(result) < limit and fallback_items:
        for item in fallback_items:
            title = item.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            result.append(item)
            if len(result) >= limit:
                break
    return result

def fetch_training_news(toutiao_items, baidu_items):
    """Fetch training industry news from filtered hot search"""
    print("[5/6] Filtering training industry news...")
    keywords = [
        "培训", "职业教育", "职业技能", "企业培训", "教培", "技能培训",
        "AI培训", "培训券", "内训师", "TTT", "公考", "职业资格", "技能认证",
        "考证", "证书", "讲师", "内训", "赋能", "职业", "技能", "就业",
        "创业", "实习", "就业率", "人才", "招聘", "职业院校", "技校",
        "产教融合", "校企合作", "双师", "实训", "培训基地", "数字技能",
    ]
    all_items = toutiao_items + baidu_items
    result = filter_news_by_keywords(all_items, keywords, limit=20, fallback_items=all_items)
    print(f"  Got {len(result)} training items (keyword matched: {min(len(result), 20)})")
    return result

def fetch_education_news(toutiao_items, baidu_items):
    """Fetch education news from filtered hot search"""
    print("[6/6] Filtering education news...")
    keywords = [
        "高考", "大学", "教育", "学校", "艺考", "招生", "录取",
        "教育部", "学生", "考研", "校园", "中小学", "分数线", "投档",
        "考生", "志愿", "985", "211", "警校", "军校", "毕业", "开学",
        "暑假", "留学", "奖学金", "助学", "义务教育", "幼儿园",
        "高中", "初中", "小学", "毕业生", "就业", "博士", "硕士",
        "研究型大学", "中外合作", "本科", "专科", "职教", "新课标",
    ]
    all_items = toutiao_items + baidu_items
    result = filter_news_by_keywords(all_items, keywords, limit=20, fallback_items=all_items)
    print(f"  Got {len(result)} education items (keyword matched: {min(len(result), 20)})")
    return result

# ========== HTML Generation ==========

def gen_news_section(aihot, toutiao, baidu):
    """Generate news section HTML"""
    # AI hot news
    ai_html = ""
    tag_map = {"模型发布": "tag-green", "产品发布": "tag-blue", "行业动态": "tag-orange",
               "技术突破": "tag-purple", "安全漏洞": "tag-red"}
    for i, item in enumerate(aihot[:7]):
        tag_class = "tag-blue"
        for k, v in tag_map.items():
            if k in item.get("category", ""):
                tag_class = v
                break
        ai_html += f'''<div class="card"><div class="card-title"><span class="rnk">{i+1}</span>{item["title"]}</div><div class="card-meta">AI HOT · {item["category"]} · {BEIJING_NOW.month}月{BEIJING_NOW.day}日 <span class="card-tag {tag_class}">{item["category"]}</span></div><div class="card-summary">{item["summary"]}</div></div>\n'''

    # Domestic news (from Toutiao + Baidu, filter for domestic keywords, take top 10)
    domestic_keywords = ["中国", "我国", "国内", "省", "市", "部", "院", "委", "局", "法", "政", "经", "农", "医", "科", "技", "建", "能", "电", "水", "路", "桥"]
    all_items = []
    seen = set()
    for item in toutiao + baidu:
        title = item.get("title", "")
        if title and title not in seen:
            seen.add(title)
            all_items.append(item)
    # Filter out international-looking titles
    intl_keywords = ["美国", "俄罗斯", "伊朗", "朝鲜", "日本", "韩国", "英国", "法国", "德国",
                     "欧盟", "北约", "联合国", "以色列", "乌克兰", "特朗普", "拜登", "普京"]
    domestic = [item for item in all_items if not any(kw in item["title"] for kw in intl_keywords)][:10]
    if len(domestic) < 10:
        domestic = all_items[:10]

    dom_html = ""
    for i, item in enumerate(domestic):
        title = item.get("title", "")
        desc = item.get("desc", item.get("summary", ""))
        source = "头条" if item in toutiao else "百度"
        if not desc:
            desc = item.get("title", "")
        dom_html += f'<li><strong>{title}</strong> — {desc[:80]} <span class="src">[{source}]</span></li>\n'

    # International news
    intl = [item for item in all_items if any(kw in item["title"] for kw in intl_keywords)][:10]
    if len(intl) < 3:
        intl = all_items[10:20] if len(all_items) > 10 else all_items

    intl_html = ""
    for i, item in enumerate(intl):
        title = item.get("title", "")
        desc = item.get("desc", item.get("summary", ""))
        source = "头条" if item in toutiao else "百度"
        if not desc:
            desc = item.get("title", "")
        intl_html += f'<li><strong>{title}</strong> — {desc[:80]} <span class="src">[{source}]</span></li>\n'

    total = len(aihot) + len(domestic) + len(intl)

    observation = gen_news_observation(aihot, domestic, intl)

    return f'''<div class="stats-row">
<div class="stat-card"><div class="stat-num">{len(aihot)}</div><div class="stat-label">AI 热点</div></div>
<div class="stat-card"><div class="stat-num">{len(domestic)}</div><div class="stat-label">国内新闻</div></div>
<div class="stat-card"><div class="stat-num">{len(intl)}</div><div class="stat-label">国际新闻</div></div>
<div class="stat-card"><div class="stat-num">{total}</div><div class="stat-label">总条数</div></div>
</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">1</span>AI 热点速递（流量Top {len(aihot)}）</div>
{ai_html}</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">2</span>国内新闻（流量Top {len(domestic)}）</div>
<ol class="compact-list">
{dom_html}</ol>
</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">3</span>国际新闻（流量Top {len(intl)}）</div>
<ol class="compact-list">
{intl_html}</ol>
</div>
<div class="observation">
<div class="observation-title">今日观察</div>
{observation}
</div>'''

def gen_news_observation(aihot, domestic, intl):
    """Generate simple news observation"""
    ai_titles = [item["title"][:15] for item in aihot[:3]]
    dom_titles = [item["title"][:15] for item in domestic[:3]]
    intl_titles = [item["title"][:15] for item in intl[:3]]
    obs = f'<p><strong>AI行业</strong>：今日AI热点关键词：{", ".join(ai_titles)}。'
    if aihot:
        obs += f'热度最高为"{aihot[0]["title"][:20]}"。</p>'
    else:
        obs += '</p>'
    obs += f'<p><strong>国内</strong>：国内热搜关键词：{", ".join(dom_titles)}。</p>'
    obs += f'<p><strong>国际</strong>：国际焦点：{", ".join(intl_titles)}。</p>'
    return obs

def gen_training_section(training_items):
    """Generate training industry section HTML"""
    if not training_items:
        return gen_empty_section("暂无培训行业数据，可能数据源API暂时不可用")

    top5 = training_items[:5]
    rest = training_items[5:20]

    cards_html = ""
    for i, item in enumerate(top5):
        hot = int(item.get("hot", 0)) if str(item.get("hot", "0")).isdigit() else 0
        border_color = ["#ef4444", "#f59e0b", "#ef4444", "#3b82f6", "#3b82f6"][i] if i < 5 else "#3b82f6"
        title = item.get("title", "")
        desc = item.get("desc", item.get("summary", ""))
        url = item.get("url", item.get("rawUrl", ""))
        source = "头条" if "toutiao" in url.lower() else "百度"
        cards_html += f'<div class="card" style="border-left:4px solid {border_color}"><div class="card-title"><span class="rnk">{i+1}</span>{title}</div>\n'
        cards_html += f'<div class="card-meta">热度搜索 · {source} · {BEIJING_NOW.month}月{BEIJING_NOW.day}日 <span class="card-tag tag-blue">热搜</span></div>\n'
        if desc:
            cards_html += f'<div class="card-summary">{desc[:120]}</div>\n'
        if url:
            cards_html += f'<a class="card-link" href="{url}" target="_blank">阅读原文 →</a></div>\n'
        else:
            cards_html += '</div>\n'

    list_html = ""
    for i, item in enumerate(rest):
        title = item.get("title", "")
        desc = item.get("desc", "")
        source = "头条" if "toutiao" in item.get("url", "").lower() else "百度"
        list_html += f'<li><strong>{title}</strong>'
        if desc:
            list_html += f' — {desc[:60]}'
        list_html += f' <span class="src">[{source}]</span></li>\n'

    observation = '<p><strong>培训行业动态</strong>：以上为今日热搜中与培训行业相关的条目。建议结合本地WorkBuddy版本获取更详细的分析。</p>'

    return f'''<div class="stats-row">
<div class="stat-card"><div class="stat-num">{len(training_items)}</div><div class="stat-label">热门条目</div></div>
<div class="stat-card"><div class="stat-num">{len(top5)}</div><div class="stat-label">详细卡片</div></div>
<div class="stat-card"><div class="stat-num">{len(rest)}</div><div class="stat-label">列表条目</div></div>
</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">1</span>流量Top 5（详细）</div>
{cards_html}</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">2</span>排行榜 6-{len(training_items)}</div>
<ol class="compact-list" start="6">
{list_html}</ol>
</div>
<div class="observation">
<div class="observation-title">今日观察</div>
{observation}
</div>'''

def gen_education_section(education_items):
    """Generate education news section HTML"""
    if not education_items:
        return gen_empty_section("暂无教育新闻数据，可能数据源API暂时不可用")

    top5 = education_items[:5]
    rest = education_items[5:20]

    cards_html = ""
    for i, item in enumerate(top5):
        title = item.get("title", "")
        desc = item.get("desc", item.get("summary", ""))
        url = item.get("url", item.get("rawUrl", ""))
        source = "头条" if "toutiao" in url.lower() else "百度"
        cards_html += f'<div class="card"><div class="card-title"><span class="rnk">{i+1}</span>{title}</div>\n'
        cards_html += f'<div class="card-meta">{source} · {BEIJING_NOW.month}月{BEIJING_NOW.day}日 <span class="card-tag tag-blue">热搜</span></div>\n'
        if desc:
            cards_html += f'<div class="card-summary">{desc[:120]}</div>\n'
        if url:
            cards_html += f'<a class="card-link" href="{url}" target="_blank">阅读原文 →</a></div>\n'
        else:
            cards_html += '</div>\n'

    list_html = ""
    for i, item in enumerate(rest):
        title = item.get("title", "")
        desc = item.get("desc", "")
        source = "头条" if "toutiao" in item.get("url", "").lower() else "百度"
        list_html += f'<li><strong>{title}</strong>'
        if desc:
            list_html += f' — {desc[:60]}'
        list_html += f' <span class="src">[{source}]</span></li>\n'

    observation = '<p><strong>教育动态</strong>：以上为今日热搜中与教育相关的条目。建议结合本地WorkBuddy版本获取更详细的分析。</p>'

    return f'''<div class="stats-row">
<div class="stat-card"><div class="stat-num">{len(education_items)}</div><div class="stat-label">热门条目</div></div>
<div class="stat-card"><div class="stat-num">{len(top5)}</div><div class="stat-label">详细卡片</div></div>
<div class="stat-card"><div class="stat-num">{len(rest)}</div><div class="stat-label">列表条目</div></div>
</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">1</span>流量Top 5（详细）</div>
{cards_html}</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">2</span>排行榜 6-{len(education_items)}</div>
<ol class="compact-list" start="6">
{list_html}</ol>
</div>
<div class="observation">
<div class="observation-title">今日观察</div>
{observation}
</div>'''

def gen_automation_section(videos):
    """Generate office automation videos section HTML"""
    if not videos:
        return gen_empty_section("暂无办公自动化视频数据，可能B站API暂时不可用")

    top5 = videos[:5]
    rest = videos[5:20]
    max_play = top5[0]["play"] if top5 else 1

    cards_html = ""
    for i, v in enumerate(top5):
        play_str = format_play_count(v["play"])
        heat_pct = round(v["play"] / max_play * 100, 1) if max_play > 0 else 0
        tags = v.get("tag", "").split(",")[:2]
        tag_html = ""
        for t in tags:
            t = t.strip()
            if t:
                tag_html += f'<span class="card-tag tag-blue">{t}</span>'
        cards_html += f'<div class="card"><div class="card-title"><span class="rnk">{i+1}</span>{v["title"]}</div>\n'
        cards_html += f'<div class="card-meta">B站 · UP主：{v["author"]} · 播放量：{play_str} {tag_html}</div>\n'
        desc = v.get("desc", v.get("tag", ""))
        if desc:
            cards_html += f'<div class="card-summary">{clean_html(desc)[:120]}</div>\n'
        cards_html += f'<div class="card-meta">热度：<span class="heat-bar"><span class="heat-fill" style="width:{heat_pct}%"></span></span> {heat_pct}%</div>\n'
        cards_html += f'<a class="card-link" href="{v["url"]}" target="_blank">观看视频 →</a></div>\n'

    table_html = ""
    for i, v in enumerate(rest):
        play_str = format_play_count(v["play"])
        idx = i + 6
        difficulty = "进阶" if any(kw in v["title"] for kw in ["高级", "进阶", "实战", "源码"]) else "入门"
        table_html += f'<tr><td>{idx}</td><td>{v["title"]}</td><td>B站</td><td>{v["author"]}</td><td>{difficulty}</td><td><a href="{v["url"]}" target="_blank">观看→</a></td></tr>\n'

    observation = '''<div class="observation-title">学习路径建议</div>
<p><strong>零基础入门（1-2周）</strong>：先从Python基础教程开始，能看懂代码、改参数就行。</p>
<p><strong>办公自动化实战（2-4周）</strong>：专找"Python自动化办公"类视频，有源代码的优先。</p>
<p><strong>今日观察</strong>：此数据由云端自动收集，如需更精准的排行和分析，请查看本地WorkBuddy版本。</p>'''

    return f'''<div class="stats-row">
<div class="stat-card"><div class="stat-num">{len(videos)}</div><div class="stat-label">热门视频</div></div>
<div class="stat-card"><div class="stat-num">{format_play_count(max_play)}</div><div class="stat-label">最高播放</div></div>
<div class="stat-card"><div class="stat-num">B站</div><div class="stat-label">主平台</div></div>
</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">1</span>播放量Top 5（详细）</div>
{cards_html}</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">2</span>完整排行榜 6-{len(videos)}</div>
<table>
<thead><tr><th>序号</th><th>标题</th><th>平台</th><th>UP主</th><th>难度</th><th>链接</th></tr></thead>
<tbody>
{table_html}</tbody>
</table>
</div>
<div class="rpt-section">
<div class="rpt-section-title"><span class="num">3</span>学习建议</div>
<div class="observation">
{observation}
</div>
</div>'''

def gen_empty_section(msg):
    """Generate empty section when no data"""
    return f'<div class="observation"><div class="observation-title">提示</div><p>{msg}</p></div>'

# ========== Full HTML Template ==========

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="小美丽">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#1e293b">
<meta name="format-detection" content="telephone=no">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="icon-512.png">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
<link rel="manifest" href="manifest.json">
<title>小美丽</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;color:#333;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.app{display:flex;min-height:100vh}
.sidebar{width:260px;background:#1e293b;color:#cbd5e1;display:flex;flex-direction:column;position:fixed;height:100vh;overflow-y:auto;z-index:100;padding-top:env(safe-area-inset-top)}
.sidebar::-webkit-scrollbar{width:4px}
.sidebar::-webkit-scrollbar-thumb{background:#475569;border-radius:2px}
.sb-header{padding:24px 20px;border-bottom:1px solid #334155}
.sb-title{font-size:17px;font-weight:700;color:#f1f5f9;display:flex;align-items:center;gap:8px}
.sb-subtitle{font-size:11px;color:#64748b;margin-top:6px;letter-spacing:1px}
.sb-date{padding:16px 20px;border-bottom:1px solid #334155}
.sb-date-label{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px}
.sb-date-item{padding:8px 12px;border-radius:6px;font-size:13px;cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:8px}
.sb-date-item:hover{background:#334155}
.sb-date-item.active{background:#3b82f6;color:#fff;font-weight:600}
.sb-date-item .dot{width:6px;height:6px;border-radius:50%;background:#64748b}
.sb-date-item.active .dot{background:#fff}
.sb-nav-label{padding:16px 20px 8px;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px}
.sb-nav{padding:0 12px 20px;flex:1}
.sb-nav-item{display:flex;align-items:center;padding:11px 12px;border-radius:8px;cursor:pointer;margin-bottom:3px;transition:all .2s}
.sb-nav-item:hover{background:#334155}
.sb-nav-item.active{background:#3b82f6}
.sb-nav-icon{font-size:18px;margin-right:10px;width:24px;text-align:center}
.sb-nav-text{font-size:14px;flex:1}
.sb-nav-item.active .sb-nav-text{color:#fff;font-weight:600}
.sb-nav-badge{font-size:10px;padding:2px 7px;border-radius:10px;background:#334155;color:#94a3b8;font-weight:500}
.sb-nav-item.active .sb-nav-badge{background:rgba(255,255,255,.25);color:#fff}
.sb-footer{padding:16px 20px;border-top:1px solid #334155;font-size:11px;color:#475569}
.sb-status{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.sb-status-dot{width:6px;height:6px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.main{flex:1;margin-left:260px;display:flex;flex-direction:column;min-height:100vh}
.main-header{background:#fff;padding:20px 32px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.main-title{font-size:20px;font-weight:700;color:#0f172a;display:flex;align-items:center;gap:10px}
.main-meta{font-size:13px;color:#64748b;display:flex;align-items:center;gap:12px}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge-blue{background:#eff6ff;color:#2563eb}
.badge-green{background:#f0fdf4;color:#16a34a}
.badge-orange{background:#fff7ed;color:#ea580c}
.content{padding:28px 32px;max-width:960px;width:100%;margin:0 auto}
.rpt-section{margin-bottom:28px}
.rpt-section-title{font-size:16px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;display:flex;align-items:center;gap:8px}
.rpt-section-title .num{background:#3b82f6;color:#fff;font-size:12px;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;margin-bottom:12px;transition:box-shadow .2s}
.card:hover{box-shadow:0 4px 12px rgba(0,0,0,.06)}
.card-title{font-size:15px;font-weight:600;color:#0f172a;margin-bottom:6px;display:flex;align-items:flex-start;gap:6px}
.card-title .rnk{color:#3b82f6;font-weight:700;margin-right:2px;min-width:20px}
.card-meta{font-size:12px;color:#94a3b8;margin-bottom:8px}
.card-summary{font-size:13px;color:#475569;line-height:1.7}
.card-link{font-size:12px;color:#3b82f6;text-decoration:none;margin-top:6px;display:inline-block}
.card-link:hover{text-decoration:underline}
.card-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-right:4px}
.tag-blue{background:#eff6ff;color:#2563eb}.tag-green{background:#f0fdf4;color:#16a34a}.tag-orange{background:#fff7ed;color:#ea580c}.tag-red{background:#fef2f2;color:#dc2626}.tag-purple{background:#faf5ff;color:#9333ea}
.observation{background:linear-gradient(135deg,#f0f9ff,#e0f2fe);border-left:4px solid #3b82f6;border-radius:0 10px 10px 0;padding:16px 20px;margin:20px 0}
.observation-title{font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px;display:flex;align-items:center;gap:6px}
.observation p{font-size:13px;color:#475569;line-height:1.8;margin-bottom:8px}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px;margin:8px 0}
th{background:#f8fafc;padding:10px 14px;text-align:left;font-weight:600;color:#475569;border-bottom:2px solid #e2e8f0;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
td{padding:10px 14px;border-bottom:1px solid #f1f5f9;color:#475569}
tr:hover td{background:#f8fafc}
td a{color:#3b82f6;text-decoration:none}td a:hover{text-decoration:underline}
.subhead{font-size:14px;font-weight:600;color:#1e293b;margin:18px 0 10px;padding-left:10px;border-left:3px solid #3b82f6}
.compact-list{list-style:none;padding:0}
.compact-list li{padding:9px 0 9px 24px;font-size:13px;color:#475569;border-bottom:1px solid #f8fafc;position:relative;line-height:1.6}
.compact-list li:last-child{border-bottom:none}
.compact-list li::before{content:counter(item);counter-increment:item;position:absolute;left:0;top:9px;font-size:11px;font-weight:700;color:#3b82f6;width:18px;height:18px;background:#eff6ff;border-radius:50%;display:flex;align-items:center;justify-content:center}
.compact-list{counter-reset:item}
.compact-list li strong{color:#0f172a}
.compact-list li .src{font-size:11px;color:#94a3b8;margin-left:4px}
.stats-row{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}
.stat-card{flex:1;min-width:120px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;text-align:center}
.stat-num{font-size:28px;font-weight:800;color:#3b82f6}
.stat-label{font-size:12px;color:#64748b;margin-top:4px}
.heat-bar{display:inline-block;width:60px;height:6px;background:#f1f5f9;border-radius:3px;margin-left:6px;vertical-align:middle;overflow:hidden}
.heat-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#f59e0b,#ef4444)}
.menu-btn{display:none;position:fixed;top:calc(env(safe-area-inset-top,0px) + 20px);left:14px;z-index:200;width:48px;height:48px;border-radius:12px;background:#1e293b;border:none;cursor:pointer;align-items:center;justify-content:center;box-shadow:0 2px 12px rgba(0,0,0,.2)}
.menu-btn span{display:block;width:20px;height:2px;background:#fff;border-radius:1px;position:relative;transition:all .3s}
.menu-btn span::before,.menu-btn span::after{content:'';position:absolute;left:0;width:20px;height:2px;background:#fff;border-radius:1px;transition:all .3s}
.menu-btn span::before{top:-6px}
.menu-btn span::after{top:6px}
.menu-btn.open span{background:transparent}
.menu-btn.open span::before{top:0;transform:rotate(45deg)}
.menu-btn.open span::after{top:0;transform:rotate(-45deg)}
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:150;opacity:0;transition:opacity .3s}
.overlay.show{display:block;opacity:1}
@media(max-width:768px){
.menu-btn{display:flex}
.sidebar{transform:translateX(-100%);transition:transform .3s ease;z-index:180;box-shadow:4px 0 20px rgba(0,0,0,.15)}
.sidebar.open{transform:translateX(0)}
.main{margin-left:0}
.main-header{padding:16px 16px 16px 68px}
.main-title{font-size:17px}
.main-meta{font-size:11px;gap:8px}
.main-meta .badge{font-size:10px;padding:2px 8px}
.content{padding:16px}
.rpt-section{margin-bottom:22px}
.rpt-section-title{font-size:15px}
.card{padding:14px}
.card-title{font-size:14px}
.card-summary{font-size:12px}
.stats-row{gap:8px}
.stat-card{min-width:80px;padding:12px 8px}
.stat-num{font-size:22px}
.stat-label{font-size:10px}
table{font-size:12px}
th,td{padding:8px 10px}
.observation{padding:14px}
.observation p{font-size:12px}
.compact-list li{font-size:12px;padding:8px 0 8px 24px}
.subhead{font-size:13px}
}
@media(max-width:480px){
.stats-row{flex-direction:row;flex-wrap:wrap}
.stat-card{flex:1 1 40%}
.main-header{flex-direction:column;align-items:flex-start;gap:6px}
}
</style>
</head>
<body>
<div class="app">
<button class="menu-btn" id="menuBtn"><span></span></button>
<div class="overlay" id="overlay"></div>
<aside class="sidebar" id="sidebar">
<div class="sb-header"><div class="sb-title">__TITLE_EMOJI__ 一人公司工作台</div><div class="sb-subtitle">DAILY INTELLIGENCE DASHBOARD</div></div>
<div class="sb-date"><div class="sb-date-label">__DATE_EMOJI__ 日期</div><div class="sb-date-item active"><span class="dot"></span>__DATE_SHORT__</div></div>
<div class="sb-nav-label">__NAV_EMOJI__ 信息分类</div>
<nav class="sb-nav">
<div class="sb-nav-item active" data-rpt="news"><span class="sb-nav-icon">__NEWS_EMOJI__</span><span class="sb-nav-text">新闻日报</span><span class="sb-nav-badge">__NEWS_COUNT__条</span></div>
<div class="sb-nav-item" data-rpt="training"><span class="sb-nav-icon">__TRAIN_EMOJI__</span><span class="sb-nav-text">培训行业</span><span class="sb-nav-badge">__TRAIN_COUNT__条</span></div>
<div class="sb-nav-item" data-rpt="education"><span class="sb-nav-icon">__EDU_EMOJI__</span><span class="sb-nav-text">教育新闻</span><span class="sb-nav-badge">__EDU_COUNT__条</span></div>
<div class="sb-nav-item" data-rpt="automation"><span class="sb-nav-icon">__AUTO_EMOJI__</span><span class="sb-nav-text">办公自动化视频</span><span class="sb-nav-badge">__AUTO_COUNT__个</span></div>
</nav>
<div class="sb-footer"><div class="sb-status"><span class="sb-status-dot"></span>云端自动更新 · 每日8:00</div><div>数据来源：aihot + 头条 + 百度 + B站</div></div>
</aside>
<main class="main">
<div class="main-header">
<div class="main-title" id="mTitle">__NEWS_EMOJI__新闻日报</div>
<div class="main-meta" id="mMeta"><span>__DATE_STR__</span><span class="badge badge-blue">AI热点__NEWS_AI_COUNT__ + 国内__NEWS_DOM_COUNT__ + 国际__NEWS_INTL_COUNT__</span></div>
</div>
<div class="content" id="rptBox"></div>
</main>
</div>
<script>
const R={
news:{
title:'<span class="icon">__NEWS_EMOJI__</span>新闻日报',
meta:'<span>__DATE_STR__</span><span class="badge badge-blue">AI热点__NEWS_AI_COUNT__ + 国内__NEWS_DOM_COUNT__ + 国际__NEWS_INTL_COUNT__</span>',
html:`__NEWS_HTML__`
},
training:{
title:'<span class="icon">__TRAIN_EMOJI__</span>培训行业日报',
meta:'<span>__DATE_STR__</span><span class="badge badge-green">流量Top __TRAIN_COUNT__</span>',
html:`__TRAIN_HTML__`
},
education:{
title:'<span class="icon">__EDU_EMOJI__</span>教育新闻日报',
meta:'<span>__DATE_STR__</span><span class="badge badge-orange">流量Top __EDU_COUNT__</span>',
html:`__EDU_HTML__`
},
automation:{
title:'<span class="icon">__AUTO_EMOJI__</span>办公自动化学习视频',
meta:'<span>__DATE_STR__</span><span class="badge badge-orange">播放量Top __AUTO_COUNT__</span>',
html:`__AUTO_HTML__`
}
};
document.querySelectorAll('.sb-nav-item').forEach(item=>{item.addEventListener('click',()=>{document.querySelectorAll('.sb-nav-item').forEach(i=>i.classList.remove('active'));item.classList.add('active');const k=item.dataset.rpt;document.getElementById('mTitle').innerHTML=R[k].title;document.getElementById('mMeta').innerHTML=R[k].meta;document.getElementById('rptBox').innerHTML=R[k].html;document.querySelector('.main').scrollTo({top:0,behavior:'smooth'});closeMenu();})});
document.querySelectorAll('.sb-date-item').forEach(item=>{item.addEventListener('click',()=>{document.querySelectorAll('.sb-date-item').forEach(i=>i.classList.remove('active'));item.classList.add('active');})});
document.getElementById('rptBox').innerHTML=R.news.html;
const menuBtn=document.getElementById('menuBtn');
const sidebar=document.getElementById('sidebar');
const overlay=document.getElementById('overlay');
function openMenu(){sidebar.classList.add('open');overlay.classList.add('show');menuBtn.classList.add('open')}
function closeMenu(){sidebar.classList.remove('open');overlay.classList.remove('show');menuBtn.classList.remove('open')}
menuBtn.addEventListener('click',()=>{sidebar.classList.contains('open')?closeMenu():openMenu()});
overlay.addEventListener('click',closeMenu);
</script>
</body>
</html>'''

# ========== Main ==========

def main():
    print(f"=== 小美丽云端自动更新 {DATE_STR} {WEEK_STR} ===")
    print()

    # Fetch all data
    aihot = fetch_aihot_news()
    toutiao = fetch_toutiao_hot()
    baidu = fetch_baidu_hot()
    videos = fetch_bilibili_videos()
    training = fetch_training_news(toutiao, baidu)
    education = fetch_education_news(toutiao, baidu)

    print()
    print("=== Generating HTML ===")

    # Generate section HTML
    news_count_ai = len(aihot)
    news_count_dom = 10
    news_count_intl = 10
    news_html = gen_news_section(aihot, toutiao, baidu)
    training_html = gen_training_section(training)
    education_html = gen_education_section(education)
    automation_html = gen_automation_section(videos)

    # Fill template
    replacements = {
        "__TITLE_EMOJI__": "\U0001f3e2",
        "__DATE_EMOJI__": "\U0001f4c5",
        "__NAV_EMOJI__": "\U0001f4c2",
        "__NEWS_EMOJI__": "\U0001f30d",
        "__TRAIN_EMOJI__": "\U0001f4da",
        "__EDU_EMOJI__": "\U0001f393",
        "__AUTO_EMOJI__": "\u26a1",
        "__DATE_SHORT__": DATE_SHORT,
        "__DATE_STR__": f"{DATE_STR} · {WEEK_STR}",
        "__NEWS_COUNT__": str(news_count_ai + news_count_dom + news_count_intl),
        "__TRAIN_COUNT__": str(len(training)),
        "__EDU_COUNT__": str(len(education)),
        "__AUTO_COUNT__": str(len(videos)),
        "__NEWS_AI_COUNT__": str(news_count_ai),
        "__NEWS_DOM_COUNT__": str(news_count_dom),
        "__NEWS_INTL_COUNT__": str(news_count_intl),
        "__NEWS_HTML__": news_html,
        "__TRAIN_HTML__": training_html,
        "__EDU_HTML__": education_html,
        "__AUTO_HTML__": automation_html,
    }

    html_output = HTML_TEMPLATE
    for key, value in replacements.items():
        html_output = html_output.replace(key, value)

    # Write output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_output)

    print(f"  Written to: {OUTPUT_FILE}")
    print(f"  File size: {len(html_output)} chars")
    print()
    print("=== Done! ===")
    print(f"  AI Hot: {news_count_ai} items")
    print(f"  Training: {len(training)} items")
    print(f"  Education: {len(education)} items")
    print(f"  Videos: {len(videos)} items")

if __name__ == "__main__":
    main()
