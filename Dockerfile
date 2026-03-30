FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY backend/requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend/ .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8003

# 环境变量
ENV DATABASE_URL=sqlite:///./data/openclaw_enterprise.db
ENV SECRET_KEY=change-this-in-production

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
