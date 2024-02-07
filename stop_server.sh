#!/bin/bash

screen -ls | grep -o 'server' | while read -r session; do
    screen -S "$session" -X quit
done
