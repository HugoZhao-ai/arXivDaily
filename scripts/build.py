"""Render portable HTML with relative URLs; no frontend build or runtime service."""
import html
import re
import shutil
from pathlib import Path

from common import ROOT, classify, read_json, slug


def esc(value):
    return html.escape(str(value), quote=True)


def external(url, label, css=""):
    if not re.match(r"^https://", url):
        return esc(label)
    return f'<a class="{esc(css)}" href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)} ↗</a>'


def shell(title, content, prefix="./", body_attrs="", active="papers"):
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="每日追踪大模型量化、长程 Agent 与 MIT 韩松的研究论文。"><meta name="color-scheme" content="light dark">
<title>{esc(title)} · Quant Research Daily</title><link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
<script src="{prefix}assets/theme.js"></script><link rel="stylesheet" href="{prefix}assets/style.css"></head>
<body data-root="{prefix}" {body_attrs}><a class="skip-link" href="#main">跳至内容</a>
<header class="topbar"><div class="topbar-inner"><a class="brand" href="{prefix}index.html"><span class="brand-mark">q<span>.</span></span><span>Quant<span class="brand-light"> / Research Daily</span></span></a>
<nav aria-label="主导航"><a class="{'current' if active == 'papers' else ''}" href="{prefix}index.html">论文库</a><a class="{'current' if active == 'researchers' else ''}" href="{prefix}researchers/index.html">研究者</a></nav><button id="theme-toggle" class="quiet" type="button">☾ 深色</button></div></header>
{content}
<footer class="footer"><span>QUANT RESEARCH DAILY <span class="muted">/ 持续阅读，持续积累。</span></span><span>{external('https://arxiv.org', 'arXiv')} · 阅读记录保存在当前浏览器</span></footer>
<div id="toast" role="status" aria-live="polite"></div><script src="{prefix}assets/app.js" defer></script></body></html>'''


def buttons(paper):
    return f'<button class="quiet save" data-save="{esc(paper["id"])}" aria-pressed="false">☆ 收藏</button><button class="quiet" data-read="{esc(paper["id"])}" aria-pressed="false">标为已读</button>'


def topic_tags(paper, config):
    tags = []
    for topic in config["topics"]:
        if topic["id"] in paper["topics"]:
            tags.append(f'<span class="tag {"related" if topic["kind"] == "related" else ""}">{esc(topic["name"])}</span>')
    for match in paper["researchers"]:
        researcher = next(r for r in config["researchers"] if r["id"] == match["id"])
        tags.append(f'<span class="tag author-tag">{esc(researcher["name_zh"])} · {"已核验" if match["status"] == "verified" else "姓名命中"}</span>')
    return "".join(tags)


def card(paper, config):
    summary = paper.get("summary", {})
    title = summary.get("title_zh", paper["title"])
    preview = summary.get("tldr", paper["abstract"])
    search = " ".join([paper["id"], paper["title"], title, preview, paper["abstract"], *paper["authors"], *[x["label"] for x in paper["reasons"]]]).lower()
    link = f'papers/{slug(paper["id"])}/index.html'
    score = 3 * len(paper["topics"]) + 5 * len(paper["researchers"]) + (6 if 'agent-quantization' in paper['topics'] else 0)
    summary_label = '中文解读' if summary else '英文摘要'
    image = paper.get("image")
    figure = f'<a class="card-figure" href="{link}" tabindex="-1" aria-hidden="true"><img loading="lazy" src="assets/images/{esc(image["file"])}" alt="" width="640" height="320"></a>' if image else ''
    return f'''<article class="paper-card" data-id="{esc(paper['id'])}" data-date="{esc(paper['published'][:10])}" data-updated="{esc(paper['updated'])}" data-topics="{esc(' '.join(paper['topics']))}" data-researchers="{esc(' '.join(r['id'] for r in paper['researchers']))}" data-search="{esc(search)}" data-score="{score}">
{figure}<div class="card-body"><div class="card-meta"><span>{esc(paper['published'][:10])}</span><span>{summary_label} <span class="tiny-dot">·</span> v{paper['version']}</span></div>
<div class="tags">{topic_tags(paper, config)}</div><h3><a href="{link}">{esc(title)}</a></h3>
{f'<p class="english-title">{esc(paper["title"])}</p>' if summary else ''}
<p class="authors">{esc(', '.join(paper['authors'][:4]))}{' 等' if len(paper['authors']) > 4 else ''}</p>
<p class="card-preview" {'lang="en"' if not summary else ''}>{esc(preview)}</p>
<p class="match-reason"><span>↳</span> {esc('；'.join(r['evidence'] for r in paper['reasons'][:2]))}</p>
<div class="card-actions"><a class="read-link" href="{link}">阅读论文 <span>↗</span></a>{buttons(paper)}</div></div></article>'''


def index(papers, config, state):
    topics = ''.join(f'<a href="?topic={esc(t["id"])}" data-topic-link="{esc(t["id"])}"><span>{esc(t["name"])}</span><span>{sum(t["id"] in p["topics"] for p in papers)}</span></a>' for t in config['topics'])
    topic_options = ''.join(f'<option value="{esc(t["id"])}">{esc(t["name"])}</option>' for t in config['topics'])
    researcher_options = ''.join(f'<option value="{esc(r["id"])}">{esc(r["name_zh"])} / {esc(r["name"])}</option>' for r in config['researchers'])
    tracked_count = sum(bool(p['researchers']) for p in papers)
    last = state.get('last_success')
    status = f'最近成功同步 {last[:10]}' if last else '尚未完成每日同步'
    last_run = state.get('last_run') or {}
    warning = '<div class="notice">最近一次同步未完整完成，当前展示已保存的论文；失败的检索通道将在下次重试。</div>' if last_run.get('status') == 'partial' else ''
    if last_run.get('status') == 'seed':
        warning += '<div class="notice">当前为真实论文的基础阅读集，尚未完成每日检索；论文按原始发表日期展示。</div>'
    researcher = config['researchers'][0] if config['researchers'] else None
    follow = f'''<a class="researcher-mini" href="researchers/index.html"><span class="avatar">SH</span><span><strong>{esc(researcher['name_zh'])} <span class="muted">/ {esc(researcher['name'])}</span></strong><small>{esc(researcher['affiliation'])}</small></span><span>↗</span></a>''' if researcher else ''
    return shell(config['title'], f'''<main id="main" class="workspace">
<aside class="sidebar"><div class="sidebar-label">YOUR RESEARCH FEED</div><a class="all-papers selected" href="index.html" data-topic-link=""><span>全部论文</span><span>{len(papers)}</span></a>
<div class="sidebar-label section-label">研究方向</div><div class="topic-nav">{topics}</div><p class="sidebar-note">长上下文与 KV Cache 为延伸阅读，不等同于 Agent 量化实验。</p>
<div class="sidebar-label section-label">正在关注 <span>{len(config['researchers']):02d}</span></div>{follow}
<div class="sidebar-bottom"><span class="status-dot"></span><span>{esc(status)}</span><p>计划每日 12:17 · 北京时间</p></div></aside>
<section class="library"><div class="page-heading"><div><p class="eyebrow">THE DAILY READING ROOM</p><h1>你的量化研究日刊<span class="title-dot">.</span></h1><p class="subtitle">从低比特大模型，到长程 Agent 的每一步。</p></div><div class="edition"><strong>{len(papers):03d}</strong><span>篇已收录 / {tracked_count} 篇作者命中</span></div></div>
{warning}<div class="searchbox"><span aria-hidden="true">⌕</span><input id="q" type="search" aria-label="搜索论文" placeholder="搜索标题、作者、摘要或 arXiv ID…"><kbd>/</kbd></div>
<div class="filters"><label>方向<select id="topic"><option value="">全部方向</option>{topic_options}</select></label><label>研究者<select id="researcher"><option value="">全部作者</option>{researcher_options}</select></label><label>发表时间<select id="period"><option value="">全部时间</option><option value="7">近 7 天</option><option value="30">近 30 天</option><option value="90">近 90 天</option></select></label><label>阅读状态<select id="reading"><option value="">全部状态</option><option value="unread">未读</option><option value="read">已读</option><option value="saved">我的收藏</option></select></label></div>
<div id="results" class="results-bar"><h2 id="result-count">{len(papers)} 篇论文</h2><label class="sort-label">排序<select id="sort"><option value="">最新发表</option><option value="updated">最近修订</option><option value="relevance">匹配优先</option></select></label></div>
<noscript><p class="notice">已展示全部静态论文；启用 JavaScript 可使用筛选、收藏与阅读记录。</p></noscript>
<div id="feed" class="paper-grid">{''.join(card(p, config) for p in papers)}</div><div id="empty" class="empty" {'hidden' if papers else ''}><span>∅</span><h3>暂时没有匹配的论文</h3><p>换一组关键词，或放宽时间和方向筛选。</p><button id="clear" class="primary">重置筛选</button></div>
<div id="pagination" class="pagination" hidden><button id="prev">← 上一页</button><span id="page-label"></span><button id="next">下一页 →</button></div>
<div class="reading-tools"><span>我的阅读记录</span><button id="export" class="quiet">导出备份 ↗</button><label class="import-label">导入备份<input id="import" type="file" accept=".json,application/json"></label></div></section></main>''')


def detail(paper, papers, config):
    summary = paper.get('summary', {})
    sections = [('overview', '一眼看懂', summary.get('tldr', '这篇论文尚未生成中文解读。可以先阅读下方作者摘要，或打开原文。'))]
    if summary:
        sections += [(key, label, summary[key]) for key, label in [('contributions', '核心贡献'), ('method', '方法拆解'), ('results', '实验与结果'), ('limitations', '局限与待验证'), ('relevance', '与你的研究有什么关系')]]
    sections += [('abstract', '原始摘要', paper['abstract'])]
    section_html = ''.join(f'<section id="{key}" class="reading-section"><div class="section-topline"><span>READING NOTE {i:02d}</span><span>{"ORIGINAL ABSTRACT" if key == "abstract" else "PAPER BRIEF"}</span></div><h2>{label}</h2><p {"lang=\"en\"" if key == "abstract" else ""}>{esc(text)}</p></section>' for i, (key, label, text) in enumerate(sections, 1))
    toc = ''.join(f'<a href="#{key}"><span>{i:02d}</span>{label}</a>' for i, (key, label, _) in enumerate(sections, 1))
    reasons = ''.join(f'<li><strong>{esc(reason["label"])}</strong><span>{esc(reason["evidence"])}</span></li>' for reason in paper['reasons'])
    source_label = {'abstract': '基于 arXiv 摘要的 AI 解读', 'html_excerpt': '基于 arXiv HTML 节选的 AI 解读', 'curated_abstract': '基于作者摘要的 AI 中文导读'}.get(summary.get('source_kind'), '作者原始摘要')
    figure = ''
    if paper.get('image'):
        figure = f'<figure class="paper-figure"><a href="../../assets/images/{esc(paper["image"]["file"])}" target="_blank"><img src="../../assets/images/{esc(paper["image"]["file"])}" alt="论文首张图；点击查看原图" width="1000" height="500"></a><figcaption>论文原图 · {external(paper["image"]["source"], "来源")}</figcaption></figure>'
    idx = next(i for i, p in enumerate(papers) if p['id'] == paper['id'])
    neighbors = ''.join(f'<a href="../{slug(papers[j]["id"])}/index.html"><small>{label}</small><strong>{esc(papers[j].get("summary", {}).get("title_zh", papers[j]["title"]))}</strong></a>' for j, label in [(idx - 1, '← 上一篇'), (idx + 1, '下一篇 →')] if 0 <= j < len(papers))
    return shell(paper['title'], f'''<main id="main" class="detail-wrap"><a class="back-link" href="../../index.html">← 返回论文库</a><header class="paper-heading"><div class="card-meta"><span>arXiv:{esc(paper['id'])} · v{paper['version']}</span><span>{esc(source_label)}</span></div><div class="tags">{topic_tags(paper, config)}</div><h1>{esc(summary.get('title_zh', paper['title']))}</h1>{f'<p class="original-title">{esc(paper["title"])}</p>' if summary else ''}<p class="detail-authors">{esc(', '.join(paper['authors']))}</p><p class="muted">发表于 {esc(paper['published'][:10])} <span class="tiny-dot">·</span> 最近修订 {esc(paper['updated'][:10])} <span class="tiny-dot">·</span> {esc(' / '.join(paper['categories']))}</p><div class="paper-links">{external(paper['url'], 'arXiv 原文', 'primary')}{external(paper['pdf_url'], 'PDF', 'button')}{external('https://arxiv.org/html/' + paper['id'] + 'v' + str(paper['version']), 'HTML 全文', 'button')}{buttons(paper)}</div><button id="resume" class="resume" hidden></button></header>
<div class="detail-layout"><article class="reading-flow">{figure}{section_html}<section id="why" class="reading-section"><div class="section-topline">WHY THIS PAPER</div><h2>为什么收录这篇论文</h2><ul class="reasons">{reasons}</ul><p class="source-note">{esc(source_label)}。{'生成内容请与原文交叉核对；量化与长程任务的联系不代表论文进行了相关实验。' if summary else '未配置中文解读时直接展示作者摘要。'} HTML 全文可能尚未由 arXiv 提供。</p></section><nav class="paper-neighbors" aria-label="相邻论文">{neighbors}</nav></article><aside class="toc"><p class="sidebar-label">本篇阅读目录</p>{toc}<a href="#why"><span>↳</span>收录依据</a><div class="progress-box"><label for="reading-progress">阅读进度 <span id="progress-label">0%</span></label><progress id="reading-progress" max="1" value="0"></progress></div></aside></div></main>''', '../../', f'data-paper-id="{esc(paper["id"])}"')


def researchers_page(papers, config):
    profiles = []
    for researcher in config['researchers']:
        matches = [p for p in papers if any(r['id'] == researcher['id'] for r in p['researchers'])]
        verified = sum(any(r['id'] == researcher['id'] and r['status'] == 'verified' for r in p['researchers']) for p in matches)
        rows = ''.join(f'<a class="researcher-paper" href="../papers/{slug(p["id"])}/index.html"><span>{esc(p["published"][:10])}</span><strong>{esc(p.get("summary", {}).get("title_zh", p["title"]))}</strong><span>↗</span></a>' for p in matches[:10])
        profiles.append(f'''<section class="researcher-profile"><div class="profile-header"><span class="avatar large">{esc(''.join(n[0] for n in researcher['name'].split()))}</span><div><p class="eyebrow">FOLLOWING / 持续追踪</p><h2>{esc(researcher['name_zh'])} <span>{esc(researcher['name'])}</span></h2><p>{esc(researcher['affiliation'])}</p></div>{external(researcher['homepage'], '个人主页', 'button')}</div><p class="profile-description">{esc(researcher['description'])}</p><div class="profile-stats"><span><strong>{len(matches)}</strong> 篇作者命中</span><span><strong>{verified}</strong> 篇链接已核验</span><span><strong>{len(matches) - verified}</strong> 篇身份待核验</span></div><p class="source-note">以完整作者名匹配；已核验表示 arXiv ID 出现在官网或人工核验名单。仅姓名命中的条目保留待核验标识，不直接认定机构归属。</p><div class="profile-list"><div class="results-bar"><h3>最近收录</h3><a href="../index.html?researcher={esc(researcher['id'])}">查看全部 →</a></div>{rows or '<p>尚未收录该作者论文，下次同步将独立检索。</p>'}</div></section>''')
    return shell('研究者', f'<main id="main" class="profiles-wrap"><p class="eyebrow">PEOPLE BEHIND THE PAPERS</p><h1>跟随研究者，读懂研究脉络<span class="title-dot">.</span></h1><p class="subtitle">作者追踪独立于研究方向；相关与跨方向的新论文都可以被看见。</p>{"".join(profiles)}</main>', '../', active='researchers')


def build(output=None):
    config = read_json(ROOT / 'config.json')
    data = read_json(ROOT / 'data/papers.json')
    state = read_json(ROOT / 'data/state.json', {})
    verified = read_json(ROOT / 'data/researchers.json', {})
    papers = [p for p in data['papers'] if classify(p, config, verified)]
    notes = read_json(ROOT / 'data/reading_notes.json', {})
    for paper in papers:
        note = notes.get(paper['id'])
        if note and note.get('paper_updated') == paper['updated'] and not paper.get('summary'):
            paper['summary'] = note
    papers.sort(key=lambda p: (p['published'], p['id']), reverse=True)
    destination = Path(output) if output else ROOT / 'site'
    destination.mkdir(parents=True, exist_ok=True)
    assets = destination / 'assets'
    assets.mkdir(exist_ok=True)
    for source in (ROOT / 'web').iterdir():
        shutil.copyfile(source, assets / source.name)
    for paper in papers:
        if paper.get('image'):
            name = paper['image']['file']
            if Path(name).name != name or not (ROOT / 'data/images' / name).exists():
                paper.pop('image')
            else:
                (assets / 'images').mkdir(exist_ok=True)
                shutil.copyfile(ROOT / 'data/images' / name, assets / 'images' / name)
    (destination / 'index.html').write_text(index(papers, config, state), encoding='utf-8')
    (destination / 'researchers').mkdir(exist_ok=True)
    (destination / 'researchers/index.html').write_text(researchers_page(papers, config), encoding='utf-8')
    for paper in papers:
        page = destination / 'papers' / slug(paper['id'])
        page.mkdir(parents=True, exist_ok=True)
        (page / 'index.html').write_text(detail(paper, papers, config), encoding='utf-8')
    (destination / '.nojekyll').touch()
    print(f'Built {len(papers)} paper pages in {destination}')
    return destination


if __name__ == '__main__':
    build()
