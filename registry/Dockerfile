# 使用官方的 Python Alpine 镜像
FROM python:3.10-alpine

# 设置作者信息
LABEL authors="23256"

# 安装依赖包
RUN apk add --no-cache gcc musl-dev

# 设置工作目录为 /my_registry
WORKDIR /app
# 将当前目录的所有文件复制到 /app 目录
COPY . /app

# 设置 PYTHONPATH 环境变量
ENV PYTHONPATH=/app


EXPOSE 8081

# 运行 app.py 作为容器的入口点
ENTRYPOINT ["python", "app.py"]
