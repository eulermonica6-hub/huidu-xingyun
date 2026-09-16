# 部署目录

公网部署（阶段 3）所需配置模板与说明。**前提：一台可公网访问的服务器 + 域名。**

## 步骤

1. **部署机环境**：
   ```bash
   # 安装依赖
   pip install -e ".[api]"          # 或按 README 手动安装 fastapi/uvicorn + 业务依赖
   # 放置数据：小数据（图谱/元数据）随仓库；正文与向量索引另附/重建
   # 放置密钥：HUIDU_SECRET_FILE 指向外部密钥文件（不入 git）
   ```

2. **启动服务**（建议 systemd / supervisor 托管）：
   ```bash
   python -m huidu_xingyun.server          # 默认 0.0.0.0:8000
   # 或 uvicorn huidu_xingyun.server.app:app --host 127.0.0.1 --port 8000
   ```

3. **反向代理 + HTTPS**：
   - nginx：参考 `deploy/nginx.conf.example`；
   - caddy：参考 `deploy/Caddyfile`（自动申请/续期证书，最省事）。

4. **验证**：
   ```bash
   curl http://127.0.0.1:8000/api/v1/health
   curl -X POST http://127.0.0.1:8000/api/v1/ask -H 'Content-Type: application/json' \
        -d '{"query": "星云大师在哪些文章中谈到共生？", "history": []}'
   ```

5. **回填测试链接/账号**：部署成功后把可访问 URL/二维码与演示账号写入
   `docs/10_competition_description.md` 对应字段。

## 说明

- `AgentContext` 在服务启动期构建一次、单例复用；首次启动有 ~10–15s 数据加载。
- 本机到公网的网络/服务器开通不在代码仓库内，需运维侧配合。
- 系统依赖无状态（只读数据），可水平扩展；LLM 调用为同步阻塞，网关超时按需放宽到 300s。