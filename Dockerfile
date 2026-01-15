# 基于现有镜像
FROM rag:v3

# 设置工作目录
WORKDIR /app

# 删除原有的 app 目录中的所有文件
RUN rm -rf /app/*

# 复制当前项目的所有文件到容器中
COPY . /app/

# 设置命令
CMD ["streamlit", "run", "run/streamlit.py"]

