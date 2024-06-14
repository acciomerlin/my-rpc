# 使用官方的 Python Alpine 镜像
FROM python:3.10-slim

# 设置工作目录为 /app
WORKDIR /app

# 将当前目录的所有文件复制到 /app 目录
COPY . /app

# default no services
CMD ["echo", "No service specified to run"]
