#!/bin/bash

# 远程服务器地址
remote_server="root@jparm.hubber.top"

# 远程服务器上的目标路径
remote_target_path="/root/server"

# 远程服务器上的重启脚本路径
remote_restart_script="/root/restart_server.sh"

# 使用 rsync 将本地所有 .py 文件上传到远程服务器
rm -rf ./__pycache__
rm -rf ./sdk/__pycache__
rm ./bot_session*
rm ./*.log
rsync -avz --delete  --exclude=".svn/" --include="*/" --include="*.py" --include="*.json" --exclude="*" . "$remote_server:$remote_target_path"

# 检查 rsync 命令是否成功
if [ $? -eq 0 ]; then
    echo "文件上传成功"
else
    echo "文件上传失败"
    exit 1
fi

# 在远程服务器上执行重启脚本
ssh "$remote_server" "$remote_restart_script"

# 检查 ssh 命令是否成功
if [ $? -eq 0 ]; then
    echo "重启脚本执行成功"
else
    echo "重启脚本执行失败"
    exit 1
fi
