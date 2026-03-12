# RAG Frontend

基于 React + TypeScript + TailwindCSS 的前端应用，实现类似 GPT 的聊天界面。

## 技术栈

- **React 18** - 前端框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具
- **TailwindCSS 4** - CSS 框架
- **Zustand** - 状态管理
- **React Router 6** - 路由
- **Axios** - HTTP 客户端
- **react-markdown** - Markdown 渲染
- **KaTeX** - 数学公式渲染
- **Lucide React** - 图标库

## 快速开始

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

访问 http://localhost:3000

### 生产构建

```bash
npm run build
```

## 项目结构

```
src/
├── api/                    # API 调用
│   ├── client.ts           # Axios 实例
│   ├── auth.ts             # 认证 API
│   ├── chat.ts             # 聊天 API (SSE)
│   ├── files.ts            # 文件管理 API
│   └── users.ts            # 用户管理 API
│
├── components/             # 通用组件
│   ├── Chat/
│   │   ├── MessageItem.tsx     # 消息组件
│   │   └── StreamingMessage.tsx # 流式消息组件
│   └── Layout/
│       └── MainLayout.tsx      # 主布局
│
├── pages/                  # 页面
│   ├── Login.tsx           # 登录页
│   ├── Chat.tsx            # 聊天页
│   ├── FileManager.tsx     # 文件管理
│   ├── UserManagement.tsx  # 用户管理 (管理员)
│   └── ChangePassword.tsx  # 修改密码
│
├── stores/                 # Zustand 状态管理
│   ├── authStore.ts        # 认证状态
│   └── chatStore.ts        # 聊天状态
│
├── types/                  # TypeScript 类型
│   ├── auth.ts
│   ├── chat.ts
│   ├── file.ts
│   └── user.ts
│
├── App.tsx                 # 应用入口
├── main.tsx                # 渲染入口
└── index.css               # 全局样式
```

## 功能特性

### 1. 用户认证
- JWT Token 认证
- 自动刷新 Token
- 角色权限控制 (admin/user)

### 2. 聊天功能
- SSE 流式响应
- 思考过程展示（可折叠）
- Markdown 渲染
- 数学公式支持 (LaTeX/KaTeX)
- 表格渲染
- 图片显示 (MinerU 输出)
- 新对话/清空历史

### 3. 文件管理
- 文件列表（分页）
- 上传文件（管理员）
- 导入文件到向量库（管理员）
- 删除文件（管理员）
- 批量操作
- 搜索和筛选

### 4. 用户管理（管理员）
- 用户列表
- 添加/删除用户
- 修改角色
- 重置密码

### 5. 其他
- 修改密码
- 响应式布局
- 暗色主题

## API 代理配置

开发模式下，Vite 会自动代理 `/api` 请求到后端 `http://localhost:8000`。

## 默认账号

- 管理员: admin / admin123
