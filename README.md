# 小美丽 - 一人公司工作台（云端版）

每日 8:00 自动收集 4 个板块信息，生成看板 HTML，部署到 GitHub Pages。

## 数据源
- AI 热点：aihot API
- 国内/国际新闻：头条热榜 + 百度热搜
- 培训行业：热搜关键词筛选
- 教育新闻：热搜关键词筛选
- 办公自动化视频：B站搜索 API

## 自动化
- GitHub Actions 定时执行（每天 UTC 0:00 = 北京时间 8:00）
- 也支持手动触发（Actions 页面 → Run workflow）

## 启用 GitHub Pages
1. 进入仓库 Settings → Pages
2. Source 选 "Deploy from a branch"
3. Branch 选 "main" / "(root)"
4. 保存后等待几分钟，访问 https://<username>.github.io/<repo-name>/
