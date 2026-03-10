layout = """
<!-- MathJax 3.x 支持 LaTeX 公式渲染 -->
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$', '$'], ['\\(', '\\)']],
    displayMath: [['$$', '$$'], ['\\[', '\\]']],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    skipHtmlTags: ['noscript', 'style', 'textarea', 'pre', 'code'],
    ignoreHtmlClass: 'tex2jax_ignore'
  },
  startup: {
    ready: function() {
      MathJax.startup.defaultReady();
      MathJax.startup.promise.then(function() {
        console.log('MathJax initial typeset complete');
      });
      // 监听 DOM 变化，自动渲染新添加的公式
      if (typeof MutationObserver !== 'undefined') {
        var observer = new MutationObserver(function(mutations) {
          var needsTypeset = false;
          mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length) {
              needsTypeset = true;
            }
          });
          if (needsTypeset) {
            MathJax.typesetPromise().catch(function(err) {
              console.log('MathJax typeset failed: ' + err.message);
            });
          }
        });
        observer.observe(document.body, { childList: true, subtree: true });
      }
    }
  }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>

<style>
    /* MathJax 公式样式 */
    .MathJax, mjx-container { font-size: 1.1em !important; }
    mjx-container { overflow-x: auto; overflow-y: hidden; }

    /* 隐藏Streamlit默认的聊天样式 */
    .stChatMessage {
        background-color: transparent !important;
        padding: 0 !important;
    }
    
    /* 对话容器样式 */
    .chat-container {
        display: flex;
        flex-direction: column;
        gap: 16px;
        padding: 20px 0;
        max-width: 900px;
        margin: 0 auto;
    }
    
    /* 用户消息容器 */
    .user-message-container {
        display: flex;
        justify-content: flex-end;
        align-items: flex-start;
        gap: 12px;
        margin: 8px 0;
    }
    
    /* 助手消息容器 */
    .assistant-message-container {
        display: flex;
        justify-content: flex-start;
        align-items: flex-start;
        gap: 12px;
        margin: 8px 0;
    }
    
    /* 头像样式 */
    .avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        flex-shrink: 0;
    }
    
    .user-avatar {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .assistant-avatar {
        background: linear-gradient(135deg, #4A9EFF 0%, #2E7FD9 100%);
    }
    
    /* 对话泡泡样式 */
    .message-bubble {
        max-width: 65%;
        padding: 12px 16px;
        border-radius: 12px;
        word-wrap: break-word;
        line-height: 1.6;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }
    
    .user-bubble {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: #FFFFFF;
        border-bottom-right-radius: 4px;
    }
    
    .assistant-bubble {
        background-color: #2A2E35;
        color: #FAFAFA;
        border-bottom-left-radius: 4px;
        border: 1px solid #3A3E45;
    }
    
    /* Markdown 元素在气泡内的样式优化 */
    .message-bubble h1, .message-bubble h2, .message-bubble h3,
    .message-bubble h4, .message-bubble h5, .message-bubble h6 {
        color: inherit;
        margin-top: 0.5em;
        margin-bottom: 0.5em;
    }
    
    .message-bubble p {
        margin-bottom: 0.5em;
    }
    
    .message-bubble code {
        background-color: rgba(0, 0, 0, 0.3);
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Courier New', monospace;
    }
    
    .message-bubble pre {
        background-color: rgba(0, 0, 0, 0.4);
        padding: 12px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 8px 0;
    }
    
    .message-bubble pre code {
        background-color: transparent;
        padding: 0;
    }
    
    .message-bubble ul, .message-bubble ol {
        margin-left: 1.5em;
        margin-bottom: 0.5em;
    }
    
    .message-bubble li {
        margin-bottom: 0.25em;
    }
    
    .message-bubble a {
        color: #4A9EFF;
        text-decoration: underline;
    }
    
    .message-bubble blockquote {
        border-left: 3px solid #4A9EFF;
        padding-left: 12px;
        margin: 8px 0;
        opacity: 0.9;
    }
    
    .message-bubble table {
        border-collapse: collapse;
        width: 100%;
        margin: 8px 0;
    }
    
    .message-bubble th, .message-bubble td {
        border: 1px solid #3A3E45;
        padding: 8px;
        text-align: left;
    }
    
    .message-bubble th {
        background-color: rgba(74, 158, 255, 0.2);
    }
    
    /* LaTeX 公式样式 */
    .message-bubble .katex {
        font-size: 1.1em;
    }
    
    .message-bubble .katex-display {
        margin: 12px 0;
    }
    
    /* 优化按钮样式 */
    .stButton > button {
        background-color: #4A9EFF;
        color: white;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        border: none;
        font-weight: 500;
        transition: all 0.3s ease;
        width: 100%;
    }
    
    .stButton > button:hover {
        background-color: #3A8EEF;
        box-shadow: 0 4px 12px rgba(74, 158, 255, 0.3);
    }
    
    /* 优化文件上传器样式 */
    .stFileUploader {
        background-color: #1E2127;
        border-radius: 8px;
        padding: 1rem;
        border: 1px dashed #4A9EFF;
    }
    
    .stFileUploader label {
        color: #FAFAFA !important;
    }
    
    /* 优化聊天输入框样式 */
    .stChatInput {
        border-radius: 8px;
        position: sticky;
        bottom: 0;
        background-color: #0E1117;
        padding: 10px 0;
        z-index: 999;
    }
    
    /* 优化分隔线样式 */
    hr {
        border-color: #4A9EFF;
        opacity: 0.3;
        margin: 1.5rem 0;
    }
    
    /* 优化标题样式 */
    h1 {
        color: #FAFAFA;
        font-weight: 700;
        text-align: center;
        margin-bottom: 2rem;
        font-size: 2.5rem;
    }
    
    h2, h3 {
        color: #FAFAFA;
        font-weight: 600;
    }
    
    /* 优化成功/错误消息样式 */
    .stSuccess {
        background-color: rgba(40, 167, 69, 0.2);
        border-left: 4px solid #28a745;
        border-radius: 4px;
        padding: 1rem;
    }
    
    .stError {
        background-color: rgba(220, 53, 69, 0.2);
        border-left: 4px solid #dc3545;
        border-radius: 4px;
        padding: 1rem;
    }
    
    .stWarning {
        background-color: rgba(255, 193, 7, 0.2);
        border-left: 4px solid #ffc107;
        border-radius: 4px;
        padding: 1rem;
    }
    
    /* 优化侧边栏样式 */
    section[data-testid="stSidebar"] {
        background-color: #1E2127;
        border-right: 1px solid #3A3E45;
    }
    
    section[data-testid="stSidebar"] h2 {
        color: #4A9EFF;
        font-size: 1.5rem;
        margin-bottom: 1.5rem;
    }
    
    /* 优化容器样式 */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 3rem;
    }
    
    /* 文件列表样式 */
    .file-item {
        background-color: #2A2E35;
        padding: 8px 12px;
        margin: 4px 0;
        border-radius: 6px;
        font-size: 0.9rem;
        color: #FAFAFA;
        border-left: 3px solid #4A9EFF;
    }
    
    /* 隐藏Streamlit默认的footer */
    footer {
        visibility: hidden;
    }
    
    /* 加载动画 */
    .loading-dots {
        display: inline-block;
    }
    
    .loading-dots span {
        animation: blink 1.4s infinite;
        animation-fill-mode: both;
    }
    
    .loading-dots span:nth-child(2) {
        animation-delay: 0.2s;
    }
    
    .loading-dots span:nth-child(3) {
        animation-delay: 0.4s;
    }
    
    @keyframes blink {
        0%, 80%, 100% { opacity: 0; }
        40% { opacity: 1; }
    }
    </style>
"""