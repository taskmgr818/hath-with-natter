#!/usr/bin/env python3

import os
import re
import sys
import time
import socket
import signal
import logging
import subprocess
import httpx
import yaml
from natter import natter


def load_config(config_file):
    with open(config_file, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


class HathRustClient:
    def __init__(self, client_id, client_key):
        self.client_id = client_id
        self.client_key = client_key
        self._write_client_login()

    def _write_client_login(self):
        client_login_path = "/hath/data"
        if not os.path.exists(client_login_path):
            os.makedirs(client_login_path)
        with open(os.path.join(client_login_path, "client_login"), "w") as f:
            content = f"{self.client_id}-{self.client_key}"
            f.write(content)

    def start(self, enable_proxy, proxy_url, inner_port):
        cmd = ["/opt/hath-rust", "--port", inner_port]
        if enable_proxy:
            cmd.extend(["--proxy", proxy_url])
        self.process = subprocess.Popen(cmd)

    def stop(self):
        self.process.terminate()
        time.sleep(30)


def update_port(
    ipb_member_id, ipb_pass_hash, client_id, enable_proxy, proxy_url, outer_port
):
    url = f"https://e-hentai.org/hentaiathome.php?cid={client_id}&act=settings"
    headers = {
        "Cookie": f"ipb_member_id={ipb_member_id}; ipb_pass_hash={ipb_pass_hash}"
    }
    proxies = {}
    if enable_proxy:
        proxies["https://"] = proxy_url

    while True:
        try:
            html_content = httpx.get(url, headers=headers, proxies=proxies).text
        except Exception as e:
            logging.error(e)
            continue
        # 判断客户端是否关闭（能否更改端口）
        if re.search(r'name="f_port".*disabled="disabled"', html_content) is None:
            break
        time.sleep(15)

    data = {}
    # 获取原有配置
    matches1 = re.findall(r'name="([^"]*)" value="([^"]*)"', html_content)
    for match in matches1:
        data[match[0]] = match[1]
    matches2 = re.findall(r'name="([^"]*)" checked="checked"', html_content)
    for match in matches2:
        data[match] = "on"

    data["f_port"] = outer_port

    while True:
        try:
            httpx.post(url, data=data, headers=headers, proxies=proxies)
        except Exception as e:
            logging.error(e)
            continue
        break


def keep_alive(outer_ip, outer_port):
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((outer_ip, outer_port))
            s.close()
        except:
            break
        time.sleep(15)


def wait_for_network():
    test_url = "https://www.baidu.com"
    while True:
        try:
            httpx.get(test_url)
        except:
            time.sleep(15)
            continue
        break


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    inner_port, outer_ip, outer_port = natter()

    config = load_config("/etc/hath-with-natter.yaml")

    update_port(
        config["access_info"]["ipb_member_id"],
        config["access_info"]["ipb_pass_hash"],
        config["access_info"]["client_id"],
        config["proxy"]["enable"],
        config["proxy"]["url"],
        str(outer_port),
    )

    hathrustclient = HathRustClient(
        config["access_info"]["client_id"], config["access_info"]["client_key"]
    )
    hathrustclient.start(
        config["proxy"]["cache_download"], config["proxy"]["url"], str(inner_port)
    )

    def signal_handler(signum, frame):
        hathrustclient.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)

    time.sleep(60)
    keep_alive(outer_ip, outer_port)

    logging.error("连接断开，即将重新启动")
    wait_for_network()
    hathrustclient.stop()


if __name__ == "__main__":
    while True:
        main()
