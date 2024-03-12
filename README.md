# hath-with-natter
用于在NAT1（全锥型）网络运行Hentai@Home（HentaiAtHome）

## 使用方法（目前仅支持docker运行）
### 填写配置信息
* 下载[hath-with-natter.yaml.example](https://github.com/taskmgr818/hath-with-natter/raw/main/hath-with-natter.yaml.example)
* 删除“.example”后缀
* 填写配置信息
### 运行容器
`docker run --net=host -v /yourconfigpath.yaml:/etc/hath-with-natter.yaml -v /yourhathpath:/hath --name hath-with-natter taskmgr818/hath-with-natter`
## 注意事项
* 需自行配置代理服务器，用于与e-hentai.org通信
* 客户端需设为DMZ主机
* 如需停止容器，建议使用`-t 60`参数以保证程序正常退出
## 参考项目
* [MikeWang000000/Natter](https://github.com/MikeWang000000/Natter)
* [james58899/hath-rust](https://github.com/james58899/hath-rust)
