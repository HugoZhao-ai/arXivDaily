# Quant Research Daily

个人量化研究日刊：**GitHub Pages 静态阅读站 + GitHub Actions 每日同步 + 独立研究者追踪**。

默认关注大模型量化、Agent 长程任务量化，以及 MIT 的韩松（Song Han）。长上下文与 KV Cache 单独作为延伸阅读。使用 Python 3.12+ 标准库构建，无需数据库、后端服务器或前端依赖安装。

## 结合了两个项目的哪些能力

| 参考项目 | 本项目采用的体验与思路 |
| --- | --- |
| [caopulan/arXivDaily](https://github.com/caopulan/arXivDaily) | 论文卡片、个性化方向筛选、收藏、中文与原始摘要并列阅读 |
| [Infinity4B/daily-arxiv-vla](https://github.com/Infinity4B/daily-arxiv-vla) | Actions 定时抓取、Pages 部署、独立论文页、分段中文导读、明暗主题、论文首图、目录与阅读进度 |
| 本项目新增 | 作者独立检索通道、姓名命中与身份核验分离、匹配依据、主题组合筛选、同步失败状态与独立检查点 |

这是根据上述产品思路重新实现的静态版本，没有直接复制上游源码。没有实现原 arXivDaily 的登录系统、语义推荐、多文件夹收藏或 Hugging Face 全量镜像。阅读记录采用浏览器本地保存，支持 JSON 导入与导出。

## 本地查看

```bash
python scripts/build.py
python scripts/check_site.py
python -m http.server 8000 --directory site
```

打开 [本地预览](http://localhost:8000)。不要直接双击 HTML；建议使用静态服务器。仓库包含真实 arXiv 元数据及少量基于作者摘要整理的中文阅读笔记，日期、来源与身份核验状态均保留。历史基础论文不是当天新论文。

```bash
# 抓取最近窗口并保留历史存档，作者与主题分别查询
python scripts/sync.py

# 可选：抓首图；配置模型后同时生成中文解读，每次最多 15 篇
python scripts/enrich.py --max-items 15

# 构建与检查
python scripts/build.py
python scripts/check_site.py
python -m unittest discover -s tests -v
```

## 发布到 GitHub Pages

1. 将本目录推送到你自己的 GitHub 仓库，默认分支使用 `main` 或 `master`。公开仓库可直接使用 GitHub Pages；私有仓库的 Pages 可用性取决于账户计划。
2. 在 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
3. 在 **Settings → Actions → General → Workflow permissions** 允许工作流写入仓库，因为每日任务会提交 `data/` 下的论文和检查点。若组织策略或分支保护禁止机器人直接推送，需要为此仓库调整对应策略。
4. 打开 **Actions → Daily papers & GitHub Pages → Run workflow**，保留 `Fetch new papers before building` 勾选并运行。
5. 等待 `deploy` 成功；访问工作流给出的 Pages 链接。项目站点路径通常是 `https://你的用户名.github.io/仓库名/`，全部站内链接均兼容仓库子路径。

默认计划 **每天北京时间 12:17（UTC 04:17）**。GitHub 定时任务可能延迟，不保证精确到分钟；公开仓库长期无活动时，定时工作流可能被 GitHub 停用，需在 Actions 重新启用。

普通代码推送只构建已有数据；定时任务与勾选同步的手动任务才访问 arXiv。这样修改页面不会反复调用外部 API。任务只在默认分支运行，生成的 `site/` 上传为 Pages 产物；仓库只保存源码与 `data/`。

### 中文解读（可选）

没有 API Key 时，同步和部署照常工作，阅读页展示原始英文摘要。开启自动中文解读，在 **Settings → Secrets and variables → Actions** 配置：

| 类型 | 名称 | 用途 |
| --- | --- | --- |
| Secret | `LLM_API_KEY` | OpenAI 兼容的模型服务密钥 |
| Variable | `LLM_BASE_URL` | HTTPS API 基址，需带 `/v1`（如果服务要求）；默认 `https://api-inference.modelscope.cn/v1` |
| Variable | `LLM_MODEL` | 服务支持的模型 ID；默认 `deepseek-ai/DeepSeek-V3.2`，可按账户可用模型更换 |
| Secret | `MODELSCOPE_ACCESS_TOKEN` | 兼容 ModelScope 配置；未设 `LLM_API_KEY` 时使用 |

使用 DeepSeek 官方 V4 Flash 时，将 `LLM_BASE_URL` 设为 `https://api.deepseek.com`，`LLM_MODEL` 设为 `deepseek-v4-flash`，并将官方密钥保存在 `LLM_API_KEY` Secret。脚本对 V4 使用非思考模式和 JSON 输出，确保输出预算用于中文解读。接口说明见 [DeepSeek 官方文档](https://api-docs.deepseek.com/)。

本地运行时设置同名环境变量。项目**不自动加载 `.env`**。API Key 只在构建任务中使用，不进入网页。摘要/HTML 节选将发送给你配置的模型服务；调用量受 `--max-items` 限制。

中文卡片包含一句话摘要、核心贡献、方法、实验结果、局限和研究关联。优先读取 arXiv HTML，失败则使用摘要，并明确标注信息来源。摘要未提供的实验或局限不要求模型补造；Agent 关联推测应与实际实验区分。模型生成失败会保留原始摘要、在日志与任务摘要中报告，并在后续任务重试。

首图优先取 arXiv HTML 中的第一个 figure，只保存 PNG/JPEG/WebP；没有可用原图时使用纯文字卡，不以装饰图片代替论文图。未实现上游的 Playwright 首图截图兜底。

## 调整研究方向与研究者

编辑根目录的 [config.json](config.json)。

### 研究方向

`topics` 中每条规则包括：

- `query`：arXiv API 查询，用于召回候选论文。
- `groups`：对标题和摘要进行本地匹配；**组间 AND、组内 OR**，英文短词有边界检查，`quantiz` / `quantis` / `compress` 支持词干，`language model` / `reasoning model` / `transformer` 兼容复数。
- `kind`：`direct` 表示主研究方向；`related` 表示延伸阅读。

Agent 方向要求量化词、Agent/长程推理词、大模型词同时命中；普通的 `reasoning` 或扩散模型的 `multi-step` 不足以被归入这个方向。关键词筛选仍可能有误收和漏收，页面会显示命中依据，不将规则匹配称为人工精选或语义判断。

新增、更改 `query` 后该通道自动重新扫描初始窗口。仅修改本地匹配词会在构建时立即重新分类已有论文；若要扩大历史召回范围，可使用 `python scripts/sync.py --backfill-days 180`。调整 `sync.initial_days` 只影响没有成功检查点的通道。

### 追踪更多研究者

在 `researchers` 数组新增完整对象：

```json
{
  "id": "researcher-slug",
  "name": "Full English Name",
  "name_zh": "中文名",
  "affiliation": "机构",
  "homepage": "https://example.edu/profile",
  "aliases": ["Full English Name"],
  "query": "au:\"Full English Name\"",
  "verified_arxiv_ids": [],
  "description": "关注该研究者的原因。"
}
```

作者匹配独立于主题匹配，跨研究方向的论文也会收录。`aliases` 使用完整作者名；不要用姓氏或简写，以免大量同名误匹配。

- **已核验**：作者完整姓名匹配，且论文 ID 存在于研究者官网的直接 arXiv 链接或人工维护的 `verified_arxiv_ids` 中。
- **姓名命中**：完整姓名匹配，但尚无上述核验依据。只标记候选身份，不声称其作者一定属于所关注的机构。

官网只用来补充身份依据，不作为论文更新列表的数据源。现有核验依据保存在 `data/researchers.json`；官网暂时不可用时保留历史依据，并记录警告。人工名单应按官网或论文原文核实后维护。韩松的参考主页是 [MIT HAN Lab / Song Han](https://hanlab.mit.edu/songhan)。

## 同步可靠性

- 默认首次检索最近 30 天，此后每条通道从上次成功时间往前重叠 7 天，按 `lastUpdatedDate` 分页，兼顾新论文和版本修订。
- 以无版本 arXiv ID 去重，保留最新版本和首次收录时间。新版本使旧的自动中文解读与封面失效，等待重新生成。
- 每条主题与作者通道单独记录成功时间。失败或达到分页上限时不推进该通道检查点；成功通道的数据仍会保存。
- 默认 3.2 秒请求间隔，网络错误和限流采用有限指数退避。单通道最多 30 页、每页 50 篇；触顶时显式报错，可增加 `sync.max_pages`。
- JSON 先写临时文件再原子替换。抓取失败时部署已保存存档，页面提示异常；`sync-health` 在部署后让工作流明确失败，便于收到 GitHub 的失败通知。
- 不自动删除历史论文。改小主题范围只会从构建结果中排除不再命中的论文；同步时数据库会按当前匹配规则重新筛选。
- 工作流提交无法推送（例如分支保护或并发人工推送）时直接报错，不强制推送；重跑即可从远程数据恢复。

## 文件结构

```text
config.json                 兴趣方向与研究者
data/papers.json            真实论文元数据与可选自动解读
data/state.json             各通道成功检查点和同步状态
data/researchers.json       官网发现的 arXiv 身份依据
data/reading_notes.json     随项目整理的摘要导读，绑定论文修订时间
data/images/                可选论文原图
scripts/sync.py             arXiv 采集、匹配和合并
scripts/enrich.py           可选模型解读与原图获取
scripts/build.py            静态首页、研究者页与论文页
scripts/check_site.py       站内链接和锚点检查
web/                        样式与浏览器交互
tests/                      数据管线回归测试
.github/workflows/          每日同步部署与 PR 检查
site/                       构建输出，不提交
```

阅读记录保存在按站点路径隔离的 `localStorage`，不上传 GitHub，也不自动跨设备同步。迁移浏览器前可以在论文库底部导出备份。

## 参考文档

- [arXiv API 查询、分页与版本说明](https://info.arxiv.org/help/api/user-manual.html)
- [GitHub Pages 自定义 Actions 工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions 定时事件与限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

代码采用 MIT License；论文标题、摘要、图像与其他第三方材料的权利归原作者或各自权利人所有，不因代码许可证发生变更。
