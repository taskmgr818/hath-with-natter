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
    def __init__(self, client_id, client_key, path):
        self.client_id = client_id
        self.client_key = client_key
        self.path = path
        self._write_client_login()

    def _write_client_login(self):
        client_login_path = os.path.join(self.path, "hath", "data")
        if not os.path.exists(client_login_path):
            os.makedirs(client_login_path)
        with open(os.path.join(client_login_path, "client_login"), "w") as f:
            content = f"{self.client_id}-{self.client_key}"
            f.write(content)

    def start(
        self, log_level, force_background_scan, enable_proxy, proxy_url, inner_port
    ):
        hath_rust_name = "hath-rust" if os.name == "posix" else "hath-rust.exe"
        cmd = [
            os.path.join(self.path, hath_rust_name),
            "--cache-dir",
            os.path.join(self.path, "hath", "cache"),
            "--data-dir",
            os.path.join(self.path, "hath", "data"),
            "--download-dir",
            os.path.join(self.path, "hath", "download"),
            "--log-dir",
            os.path.join(self.path, "hath", "log"),
            "--temp-dir",
            os.path.join(self.path, "hath", "tmp"),
            "--port",
            inner_port,
        ]
        if enable_proxy:
            cmd.extend(["--proxy", proxy_url])
        if force_background_scan:
            cmd.append("--force-background-scan")
        if log_level > 0:
            cmd.append(f"-{'q' * log_level}")
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
    retries = 0
    while retries < 3:
        time.sleep(15)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((outer_ip, outer_port))
            s.close()
            retries = 0
        except:
            retries += 1


def wait_for_network():
    test_url = "https://223.5.5.5"
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

    path = os.path.dirname(os.path.realpath(__file__))

    config = load_config(os.path.join(path, "config.yaml"))

    hathrustclient = HathRustClient(
        config["access_info"]["client_id"],
        config["access_info"]["client_key"],
        path,
    )

    while True:
        inner_port, outer_ip, outer_port, upnp = natter()

        update_port(
            config["access_info"]["ipb_member_id"],
            config["access_info"]["ipb_pass_hash"],
            config["access_info"]["client_id"],
            config["proxy"]["enable"],
            config["proxy"]["url"],
            str(outer_port),
        )

        hathrustclient.start(
            config["hath-rust"]["log_level"],
            config["hath-rust"]["force_background_scan"],
            config["proxy"]["cache_download"],
            config["proxy"]["url"],
            str(inner_port),
        )

        def signal_handler(signum, frame):
            upnp.clear()
            hathrustclient.stop()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)

        time.sleep(60)
        keep_alive(outer_ip, outer_port)

        logging.error("连接断开，即将重新启动")
        wait_for_network()
        upnp.clear()
        hathrustclient.stop()


if __name__ == "__main__":
    main()
