# 使用官方的 Python Alpine 镜像
FROM python:3.10-alpine

# 设置作者信息
LABEL authors="23256"

# 安装依赖包
RUN apk add --no-cache gcc musl-dev

# 设置工作目录为 /app
WORKDIR /server

# 将当前目录的所有文件复制到 /app 目录
COPY . .

# 运行 server.py 作为容器的入口点
ENTRYPOINT ["python", "server.py"]
