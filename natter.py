#!/usr/bin/env python3

"""
Natter - https://github.com/MikeWang000000/Natter
Copyright (C) 2023  MikeWang000000

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
import sys
import time
import random
import socket
import struct

__version__ = "2.0.0-rc2"


class Logger(object):
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3
    rep = {DEBUG: "D", INFO: "I", WARN: "W", ERROR: "E"}
    level = INFO
    if "256color" in os.environ.get("TERM", ""):
        GREY = "\033[90;20m"
        YELLOW_BOLD = "\033[33;1m"
        RED_BOLD = "\033[31;1m"
        RESET = "\033[0m"
    else:
        GREY = YELLOW_BOLD = RED_BOLD = RESET = ""

    @staticmethod
    def set_level(level):
        Logger.level = level

    @staticmethod
    def debug(text=""):
        if Logger.level <= Logger.DEBUG:
            sys.stderr.write(
                (Logger.GREY + "%s [%s] %s\n" + Logger.RESET)
                % (time.strftime("%Y-%m-%d %H:%M:%S"), Logger.rep[Logger.DEBUG], text)
            )

    @staticmethod
    def info(text=""):
        if Logger.level <= Logger.INFO:
            sys.stderr.write(
                ("%s [%s] %s\n")
                % (time.strftime("%Y-%m-%d %H:%M:%S"), Logger.rep[Logger.INFO], text)
            )

    @staticmethod
    def warning(text=""):
        if Logger.level <= Logger.WARN:
            sys.stderr.write(
                (Logger.YELLOW_BOLD + "%s [%s] %s\n" + Logger.RESET)
                % (time.strftime("%Y-%m-%d %H:%M:%S"), Logger.rep[Logger.WARN], text)
            )

    @staticmethod
    def error(text=""):
        if Logger.level <= Logger.ERROR:
            sys.stderr.write(
                (Logger.RED_BOLD + "%s [%s] %s\n" + Logger.RESET)
                % (time.strftime("%Y-%m-%d %H:%M:%S"), Logger.rep[Logger.ERROR], text)
            )


class StunClient(object):
    class ServerUnavailable(Exception):
        pass

    def __init__(self, stun_server_list):
        if not stun_server_list:
            raise ValueError("STUN server list is empty")
        self.stun_server_list = stun_server_list
        self.source_host = "0.0.0.0"
        self.source_port = 0

    def get_mapping(self):
        first = self.stun_server_list[0]
        while True:
            try:
                return self._get_mapping()
            except StunClient.ServerUnavailable as ex:
                Logger.warning(
                    "stun: STUN server %s is unavailable: %s"
                    % (addr_to_uri(self.stun_server_list[0]), ex)
                )
                self.stun_server_list.append(self.stun_server_list.pop(0))
                if self.stun_server_list[0] == first:
                    Logger.error("stun: No STUN server is available right now")
                    # force sleep for 10 seconds, then try the next loop
                    time.sleep(10)

    def _get_mapping(self):
        # ref: https://www.rfc-editor.org/rfc/rfc5389
        socket_type = socket.SOCK_STREAM
        stun_host, stun_port = self.stun_server_list[0]
        sock = new_socket_reuse(socket.AF_INET, socket_type)
        sock.settimeout(3)
        sock.bind((self.source_host, self.source_port))
        try:
            sock.connect((stun_host, stun_port))
            inner_addr = sock.getsockname()
            self.source_host, self.source_port = inner_addr
            sock.send(
                struct.pack(
                    "!LLLLL",
                    0x00010000,
                    0x2112A442,
                    0x4E415452,
                    random.getrandbits(32),
                    random.getrandbits(32),
                )
            )
            buff = sock.recv(1500)
            ip = port = 0
            payload = buff[20:]
            while payload:
                attr_type, attr_len = struct.unpack("!HH", payload[:4])
                if attr_type in [1, 32]:
                    _, _, port, ip = struct.unpack("!BBHL", payload[4 : 4 + attr_len])
                    if attr_type == 32:
                        port ^= 0x2112
                        ip ^= 0x2112A442
                    break
                payload = payload[4 + attr_len :]
            else:
                raise ValueError("Invalid STUN response")
            outer_addr = socket.inet_ntop(socket.AF_INET, struct.pack("!L", ip)), port
            Logger.debug(
                "stun: Got address %s from %s, source %s"
                % (
                    addr_to_uri(outer_addr),
                    addr_to_uri((stun_host, stun_port)),
                    addr_to_uri(inner_addr),
                )
            )
            return inner_addr, outer_addr
        except (OSError, ValueError, struct.error, socket.error) as ex:
            raise StunClient.ServerUnavailable(ex)
        finally:
            sock.close()


def keep_alive(host, port, source_host, source_port):
    sock_type = socket.SOCK_STREAM
    sock = new_socket_reuse(socket.AF_INET, sock_type)
    sock.bind((source_host, source_port))
    sock.settimeout(3)
    sock.connect((host, port))
    Logger.debug("keep-alive: Connected to host %s" % (addr_to_uri((host, port))))
    sock.sendall(
        (
            "GET /keep-alive HTTP/1.1\r\n"
            "Host: %s\r\n"
            "User-Agent: curl/8.0.0 (Natter)\r\n"
            "Accept: */*\r\n"
            "Connection: keep-alive\r\n"
            "\r\n" % host
        ).encode()
    )
    buff = b""
    try:
        while True:
            buff = sock.recv(4096)
            if not buff:
                raise OSError("Keep-alive server closed connection")
    except socket.timeout as ex:
        if not buff:
            raise ex
    Logger.debug("keep-alive: OK")


def new_socket_reuse(family, socket_type):
    sock = socket.socket(family, socket_type)
    if hasattr(socket, "SO_REUSEADDR"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    return sock


def check_docker_network():
    if not sys.platform.startswith("linux"):
        return
    if not os.path.exists("/.dockerenv"):
        return
    if not os.path.isfile("/sys/class/net/eth0/address"):
        return
    fo = open("/sys/class/net/eth0/address", "r")
    macaddr = fo.read().strip()
    fo.close()
    fqdn = socket.getfqdn()
    ipaddr = socket.gethostbyname(fqdn)
    docker_macaddr = "02:42:" + ":".join(["%02x" % int(x) for x in ipaddr.split(".")])
    if macaddr == docker_macaddr:
        raise RuntimeError("Docker's `--net=host` option is required.")

    if not os.path.isfile("/proc/sys/kernel/osrelease"):
        return
    fo = open("/proc/sys/kernel/osrelease", "r")
    uname_r = fo.read().strip()
    fo.close()
    uname_r_sfx = uname_r.rsplit("-").pop()
    if uname_r_sfx.lower() in ["linuxkit", "wsl2"] and fqdn.lower() == "docker-desktop":
        raise RuntimeError("Network from Docker Desktop is not supported.")


def addr_to_str(addr):
    return "%s:%d" % addr


def addr_to_uri(addr):
    return "tcp://%s:%d" % addr


def natter():
    sys.tracebacklimit = 0

    stun_list = [
        "fwa.lifesizecloud.com",
        "stun.isp.net.au",
        "stun.nextcloud.com",
        "stun.freeswitch.org",
        "stun.voip.blackberry.com",
        "stunserver.stunprotocol.org",
        "stun.sipnet.com",
        "stun.radiojar.com",
        "stun.sonetel.com",
        "stun.voipgate.com",
    ]

    stun_srv_list = []
    for item in stun_list:
        l = item.split(":", 2) + ["3478"]
        stun_srv_list.append(
            (l[0], int(l[1])),
        )

    #
    #  Natter
    #
    Logger.info("Natter v%s" % __version__)

    check_docker_network()

    stun = StunClient(stun_srv_list)

    natter_addr, outer_addr = stun.get_mapping()
    inner_ip, inner_port = natter_addr
    outer_ip, outer_port = outer_addr

    keepalive_srv = "www.baidu.com"
    keepalive_port = 80
    keep_alive(keepalive_srv, keepalive_port, inner_ip, inner_port)

    return inner_port, outer_ip, outer_port
