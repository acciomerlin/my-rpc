# 使用官方的 Python Alpine 镜像
FROM python:3.10-alpine

# 设置作者信息
LABEL authors="23256"

# 安装依赖包
RUN apk add --no-cache gcc musl-dev

# 设置工作目录为 /app
WORKDIR /app

# 将当前目录的所有文件复制到 /app 目录
COPY . .

# 安装 Python 依赖项（如果有 requirements.txt 文件）
# RUN pip install -r requirements.txt

# 运行 rpc_consumer.py 作为容器的入口点
ENTRYPOINT ["python", "rpc_consumer.py"]
