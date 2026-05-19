# Frontend

Vue3 + Vite + TypeScript + Element Plus 前端。当前实现了文档上传测试工作台：

- 后端健康检查
- 注册 / 登录 / 保存 JWT
- PDF / Markdown / TXT 上传
- 上传进度和入库状态提示
- 文档列表和 chunk 数展示
- 当前模型配置展示

## 启动

```powershell
cd E:\rag_project\rag-agent-kb-system\frontend
npm.cmd install
npm.cmd run dev
```

默认后端地址：

```text
http://127.0.0.1:8000
```

如需修改，复制 `.env.example` 为 `.env`，设置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```
