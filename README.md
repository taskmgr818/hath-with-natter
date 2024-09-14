# hath-with-natter
用于在NAT1（全锥型）网络运行Hentai@Home

## 使用方法
### 填写配置信息
* 下载[config.yaml.example](https://github.com/taskmgr818/hath-with-natter/raw/main/config.yaml.example)
* 删除`.example`后缀
* 填写配置信息
### 运行程序
#### 使用 Docker 运行（仅Linux）
执行
```text
docker run --net host -v /yourconfigpath.yaml:/hath/config.yaml -v /yourhathpath/:/hath/hath/ --name hath-with-natter taskmgr818/hath-with-natter
```
#### 使用 Python 运行
* 安装依赖
* 下载对应平台的[可执行文件](https://github.com/james58899/hath-rust/releases/latest)，更名为`hath-rust`（Linux）或`hath-rust.exe`（Windows），并移动至项目文件夹
* 运行`main.py`
## 注意事项
* 需自行配置代理服务器，用于与e-hentai.org通信
* 需启用Upnp或DMZ（二者不可同时开启）
## 参考项目
* [MikeWang000000/Natter](https://github.com/MikeWang000000/Natter)
* [james58899/hath-rust](https://github.com/james58899/hath-rust)
