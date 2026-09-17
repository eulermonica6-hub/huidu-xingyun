# 公开部署：Hugging Face Space（主） + 本地 Tunnel（备）

拿测试链接的零成本路线：把 `huidu_xingyun.server` 打成 Docker 镜像推到 Hugging Face Space，
几分钟拿到公开 HTTPS 链接，免费、无需备案，评委随时点开三栏交互 + 问答。
备用/答辩现场用「本地起服务 + Cloudflare Tunnel」兜底。

## 一、主路线：Hugging Face Spaces + Docker

### 1. 准备密钥（HF Secrets）

HF Space 无法访问仓库外的 `../LLM api key.txt`，密钥改由环境变量注入（`SecretLoader` 已支持）：

| 环境变量 | 对应 Provider |
|---|---|
| `DASHSCOPE_API_KEY` | ali（主） |
| `ZHIPU_API_KEY` | zhipu（兜底） |
| `DEEPSEEK_API_KEY` / `GROQ_API_KEY` / `NVIDIA_API_KEY` | 可选 |

在 Space 的 **Settings → Secrets** 里添加上述变量（值＝你的密钥）。**不要把密钥写进仓库。**

### 2. 数据范围

仓库已含**小数据**（图谱 16MB + 文章清单 9MB + 元数据 3.5MB），图谱问答/实体解析开箱即用。
**正文全文（149MB）与向量索引（79MB）不入仓、不进镜像**，故 HF 免费档上「原文出处」类
查询返回篇名 + URL 而非段落引用（`search_semantic` 无索引自动回退关键词/元数据）。
如需完整引用：把正文与 `data/derived/vector_metadata` 上传到 Space 持久目录 `/data` 并在启动时挂接（后续可加）。

### 3. 创建 Space 并推送

```bash
# 1. 新建 Space：sdk 选 Docker（Public 或 Private 均可）
# 2. 推送（或直接由 GitHub Actions 自动部署，见下）
git remote add space https://huggingface.co/spaces/<你的用户名>/<space名>
git push space main
```

HF 读取根目录 `Dockerfile` 构建镜像；应用监听 **7860**（`ENV HUIDU_PORT=7860` + `EXPOSE 7860`）。
构建完成即得 `https://<用户名>-<space名>.hf.space`。

### 4. 由 GitHub Actions 自动部署（推荐）

`.github/workflows/deploy.yml` 已配：push 到 `main` 后跑单测 + 健康检查，通过后用
`HF_TOKEN` 把 git 跟踪文件同步到 Space 仓库。

在 GitHub 仓库配置：
- **Secret** `HF_TOKEN`（HF 读写 token）；
- **Variable** `HF_SPACE`（如 `你的用户名/huidu-xingyun`）。

> 该步骤只同步 `git ls-files`（已提交文件），确保 `.env` / 正文 / 向量 / 运行产物不会被误传。

## 二、备选：本地起服务 + Cloudflare Tunnel

答辩/演示备用：本地起服务，一条隧道出公网链接，秒开。

```bash
# 1. 本地起服务
python -m huidu_xingyun.server          # 0.0.0.0:8000

# 2. 开隧道（一次性）
cloudflared tunnel --url http://localhost:8000
# 输出形如 https://xxxx.trycloudflare.com 的临时 HTTPS 链接
```

适合「临时抽风要演示最新未部署代码」的场景；端口在 FastAPI 内固定 8000（可由 `HUIDU_PORT` 调）。

## 三、验收与压测

```bash
# 健康检查
curl https://<space>.hf.space/api/v1/health

# 问一条
curl -X POST https://<space>.hf.space/api/v1/ask -H 'Content-Type: application/json' \
     -d '{"query": "星云大师在哪些文章中谈到共生？", "history": []}'

# 并发压测（对齐评审 1–3 并发）
python scripts/load_test.py --base-url https://<space>.hf.space --health 30 --asks 6 --concurrency 3
```

**验收清单**：三栏交互（对话/路径/证据）→ 预设问题问答 → 健康状态灯 → 密钥未出现在前端与日志
（前端只经 `/api/v1/*` 拿 `FinalResponse`，密钥仅在服务端进程内）。

## 四、局限性（免费档）

- CPU-only、内存有限：本项目重计算在**云端 LLM/嵌入 API**，本地只加载 ~29MB 小数据，免费档够用；
  若以后接入本地模型推理/重计算，需升配 Paid 或把重计算移云端。
- 冷启动：Space 空闲会被回收，首次请求触发重建（~15s 数据加载）。
- 无后台任务/多副本：Long-running 或更高并发需走正式服务器路线（nginx + 域名 + 备案，见 `docs/13_deployment_plan.md` 阶段 3）。