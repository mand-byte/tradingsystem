#!/bin/bash

# 关闭程序
screen -ls | grep -o 'server' | while read -r session; do
    screen -S "$session" -X quit
done

# 启动程序
screen -dmS server python3 /root/server/main.py


# 输出信息
echo "启动完成！"
