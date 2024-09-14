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
import re
import sys
import time
import random
import socket
import struct
import logging

__version__ = "2.1.1"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class StunClient(object):
    class ServerUnavailable(Exception):
        pass

    def __init__(self, stun_server_list):
        self.stun_server_list = stun_server_list
        self.source_host = "0.0.0.0"
        self.source_port = 0

    def get_mapping(self):
        first = self.stun_server_list[0]
        while True:
            try:
                return self._get_mapping()
            except StunClient.ServerUnavailable as ex:
                logging.warning(
                    "stun: STUN server %s is unavailable: %s"
                    % (addr_to_uri(self.stun_server_list[0]), ex)
                )
                self.stun_server_list.append(self.stun_server_list.pop(0))
                if self.stun_server_list[0] == first:
                    logging.error("stun: No STUN server is available right now")
                    # force sleep for 10 seconds, then try the next loop
                    time.sleep(10)

    def _get_mapping(self):
        # ref: https://www.rfc-editor.org/rfc/rfc5389
        socket_type = socket.SOCK_STREAM
        stun_host, stun_port = self.stun_server_list[0]
        sock = socket.socket(socket.AF_INET, socket_type)
        socket_set_opt(
            sock,
            reuse=True,
            bind_addr=(self.source_host, self.source_port),
            timeout=3,
        )
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
            logging.debug(
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
    sock = socket.socket(socket.AF_INET, sock_type)
    socket_set_opt(
        sock,
        reuse=True,
        bind_addr=(source_host, source_port),
        timeout=3,
    )
    sock.connect((host, port))
    logging.debug("keep-alive: Connected to host %s" % (addr_to_uri((host, port))))
    sock.sendall(
        (
            "HEAD /natter-keep-alive HTTP/1.1\r\n"
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
    logging.debug("keep-alive: OK")


class UPnPService(object):
    def __init__(self, device):
        self.device = device
        self.service_type = None
        self.service_id = None
        self.scpd_url = None
        self.control_url = None
        self.eventsub_url = None
        self._sock_timeout = 3

    def __repr__(self):
        return "<UPnPService service_type=%s, service_id=%s>" % (
            repr(self.service_type),
            repr(self.service_id),
        )

    def is_valid(self):
        if self.service_type and self.service_id and self.control_url:
            return True
        return False

    def is_forward(self):
        if (
            self.service_type
            in (
                "urn:schemas-upnp-org:service:WANIPConnection:1",
                "urn:schemas-upnp-org:service:WANIPConnection:2",
                "urn:schemas-upnp-org:service:WANPPPConnection:1",
            )
            and self.service_id
            and self.control_url
        ):
            return True
        return False

    def forward_port(self, host, port, dest_host, dest_port, duration=0):
        if not self.is_forward():
            raise NotImplementedError(
                "Unsupported service type: %s" % self.service_type
            )

        proto = "TCP"
        ctl_hostname, ctl_port, ctl_path = split_url(self.control_url)
        descpt = "Natter"
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\r\n'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"\r\n'
            '  s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\r\n'
            "  <s:Body>\r\n"
            '    <m:AddPortMapping xmlns:m="%s">\r\n'
            "      <NewRemoteHost>%s</NewRemoteHost>\r\n"
            "      <NewExternalPort>%s</NewExternalPort>\r\n"
            "      <NewProtocol>%s</NewProtocol>\r\n"
            "      <NewInternalPort>%s</NewInternalPort>\r\n"
            "      <NewInternalClient>%s</NewInternalClient>\r\n"
            "      <NewEnabled>1</NewEnabled>\r\n"
            "      <NewPortMappingDescription>%s</NewPortMappingDescription>\r\n"
            "      <NewLeaseDuration>%d</NewLeaseDuration>\r\n"
            "    </m:AddPortMapping>\r\n"
            "  </s:Body>\r\n"
            "</s:Envelope>\r\n"
            % (
                self.service_type,
                host,
                port,
                proto,
                dest_port,
                dest_host,
                descpt,
                duration,
            )
        )
        content_len = len(content.encode())
        data = (
            "POST %s HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "User-Agent: curl/8.0.0 (Natter)\r\n"
            "Accept: */*\r\n"
            'SOAPAction: "%s#AddPortMapping"\r\n'
            "Content-Type: text/xml\r\n"
            "Content-Length: %d\r\n"
            "Connection: close\r\n"
            "\r\n"
            "%s\r\n"
            % (
                ctl_path,
                ctl_hostname,
                ctl_port,
                self.service_type,
                content_len,
                content,
            )
        ).encode()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_set_opt(
            sock,
            timeout=self._sock_timeout,
        )
        sock.connect((ctl_hostname, ctl_port))
        sock.sendall(data)
        response = b""
        while True:
            buff = sock.recv(4096)
            if not buff:
                break
            response += buff
        sock.close()
        r = response.decode("utf-8", "ignore")
        errno = errmsg = ""
        m = re.search(r"<errorCode\s*>([^<]*?)</errorCode\s*>", r)
        if m:
            errno = m.group(1).strip()
        m = re.search(r"<errorDescription\s*>([^<]*?)</errorDescription\s*>", r)
        if m:
            errmsg = m.group(1).strip()
        if errno or errmsg:
            logging.error(
                "upnp: Error from service %s of device %s: [%s] %s"
                % (self.service_type, self.device, errno, errmsg)
            )
            return False
        return True


class UPnPDevice(object):
    def __init__(self, ipaddr, xml_urls):
        self.ipaddr = ipaddr
        self.xml_urls = xml_urls
        self.services = []
        self.forward_srv = None
        self._sock_timeout = 3

    def __repr__(self):
        return "<UPnPDevice ipaddr=%s>" % (repr(self.ipaddr),)

    def _load_services(self):
        if self.services:
            return
        services_d = {}  # service_id => UPnPService()
        for url in self.xml_urls:
            sd = self._get_srv_dict(url)
            services_d.update(sd)
        self.services.extend(services_d.values())
        for srv in self.services:
            if srv.is_forward():
                self.forward_srv = srv
                break

    def _http_get(self, url):
        hostname, port, path = split_url(url)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_set_opt(
            sock,
            timeout=self._sock_timeout,
        )
        sock.connect((hostname, port))
        data = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "User-Agent: curl/8.0.0 (Natter)\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n"
            "\r\n" % (path, hostname)
        ).encode()
        sock.sendall(data)
        response = b""
        while True:
            buff = sock.recv(4096)
            if not buff:
                break
            response += buff
        sock.close()
        if not response.startswith(b"HTTP/"):
            raise ValueError("Invalid response from HTTP server")
        s = response.split(b"\r\n\r\n", 1)
        if len(s) != 2:
            raise ValueError("Invalid response from HTTP server")
        return s[1]

    def _get_srv_dict(self, url):
        try:
            xmlcontent = self._http_get(url).decode("utf-8", "ignore")
        except (OSError, socket.error, ValueError) as ex:
            logging.error("upnp: failed to load service from %s: %s" % (url, ex))
            return
        services_d = {}
        srv_str_l = re.findall(r"<service\s*>([\s\S]+?)</service\s*>", xmlcontent)
        for srv_str in srv_str_l:
            srv = UPnPService(self)
            m = re.search(r"<serviceType\s*>([^<]*?)</serviceType\s*>", srv_str)
            if m:
                srv.service_type = m.group(1).strip()
            m = re.search(r"<serviceId\s*>([^<]*?)</serviceId\s*>", srv_str)
            if m:
                srv.service_id = m.group(1).strip()
            m = re.search(r"<SCPDURL\s*>([^<]*?)</SCPDURL\s*>", srv_str)
            if m:
                srv.scpd_url = full_url(m.group(1).strip(), url)
            m = re.search(r"<controlURL\s*>([^<]*?)</controlURL\s*>", srv_str)
            if m:
                srv.control_url = full_url(m.group(1).strip(), url)
            m = re.search(r"<eventSubURL\s*>([^<]*?)</eventSubURL\s*>", srv_str)
            if m:
                srv.eventsub_url = full_url(m.group(1).strip(), url)
            if srv.is_valid():
                services_d[srv.service_id] = srv
        return services_d


class UPnPClient(object):
    def __init__(self):
        self.ssdp_addr = ("239.255.255.250", 1900)
        self.router = None
        self._sock_timeout = 1
        self._fwd_host = None
        self._fwd_port = None
        self._fwd_dest_host = None
        self._fwd_dest_port = None
        self._fwd_started = False

    def discover_router(self):
        router_l = []
        try:
            devs = self._discover()
            for dev in devs:
                if dev.forward_srv:
                    router_l.append(dev)
        except (OSError, socket.error) as ex:
            logging.error("upnp: failed to discover router: %s" % ex)
        if not router_l:
            self.router = None
        elif len(router_l) > 1:
            logging.warning("upnp: multiple routers found: %s" % (router_l,))
            self.router = router_l[0]
        else:
            self.router = router_l[0]
        return self.router

    def _discover(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        socket_set_opt(
            sock,
            reuse=True,
            timeout=self._sock_timeout,
        )
        dat01 = (
            "M-SEARCH * HTTP/1.1\r\n"
            "ST: ssdp:all\r\n"
            "MX: 2\r\n"
            'MAN: "ssdp:discover"\r\n'
            "HOST: %s:%d\r\n"
            "\r\n" % self.ssdp_addr
        ).encode()

        dat02 = (
            "M-SEARCH * HTTP/1.1\r\n"
            "ST: upnp:rootdevice\r\n"
            "MX: 2\r\n"
            'MAN: "ssdp:discover"\r\n'
            "HOST: %s:%d\r\n"
            "\r\n" % self.ssdp_addr
        ).encode()

        sock.sendto(dat01, self.ssdp_addr)
        sock.sendto(dat02, self.ssdp_addr)

        upnp_urls_d = {}
        while True:
            try:
                buff, addr = sock.recvfrom(4096)
                m = re.search(r"LOCATION: *(http://[^\[]\S+)\s+", buff.decode("utf-8"))
                if not m:
                    continue
                ipaddr = addr[0]
                location = m.group(1)
                logging.debug("upnp: Got URL %s" % location)
                if ipaddr in upnp_urls_d:
                    upnp_urls_d[ipaddr].add(location)
                else:
                    upnp_urls_d[ipaddr] = set([location])
            except socket.timeout:
                break

        devs = []
        for ipaddr, urls in upnp_urls_d.items():
            d = UPnPDevice(ipaddr, urls)
            d._load_services()
            devs.append(d)

        return devs

    def forward(self, host, port, dest_host, dest_port):
        if not self.router:
            raise RuntimeError("No router is available")
        self.router.forward_srv.forward_port(host, port, dest_host, dest_port)
        self._fwd_host = host
        self._fwd_port = port
        self._fwd_dest_host = dest_host
        self._fwd_dest_port = dest_port
        self._fwd_started = True

    def clear(self):
        if self._fwd_started:
            self.router.forward_srv.forward_port(
                self._fwd_host,
                self._fwd_port,
                self._fwd_dest_host,
                self._fwd_dest_port,
                1,
            )


def socket_set_opt(sock, reuse=False, bind_addr=None, timeout=-1):
    if reuse:
        if hasattr(socket, "SO_REUSEADDR"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    if bind_addr is not None:
        sock.bind(bind_addr)
    if timeout != -1:
        sock.settimeout(timeout)
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
    hostname = socket.gethostname()
    try:
        ipaddr = socket.gethostbyname(hostname)
    except socket.gaierror:
        logging.warning("check-docket-network: Cannot resolve hostname `%s`" % hostname)
        return
    docker_macaddr = "02:42:" + ":".join(["%02x" % int(x) for x in ipaddr.split(".")])
    if macaddr == docker_macaddr:
        raise RuntimeError("Docker's `--net=host` option is required.")

    if not os.path.isfile("/proc/sys/kernel/osrelease"):
        return
    fo = open("/proc/sys/kernel/osrelease", "r")
    uname_r = fo.read().strip()
    fo.close()
    uname_r_sfx = uname_r.rsplit("-").pop()
    if (
        uname_r_sfx.lower() in ["linuxkit", "wsl2"]
        and hostname.lower() == "docker-desktop"
    ):
        raise RuntimeError("Network from Docker Desktop is not supported.")


def split_url(url):
    m = re.match(r"^http://([^\[\]:/]+)(?:\:([0-9]+))?(/\S*)?$", url)
    if not m:
        raise ValueError("Unsupported URL: %s" % url)
    hostname, port_str, path = m.groups()
    port = 80
    if port_str:
        port = int(port_str)
    if not path:
        path = "/"
    return hostname, port, path


def full_url(u, refurl):
    if not u.startswith("/"):
        return u
    hostname, port, _ = split_url(refurl)
    return "http://%s:%d" % (hostname, port) + u


def addr_to_str(addr):
    return "%s:%d" % addr


def addr_to_uri(addr):
    return "tcp://%s:%d" % addr


def natter():
    sys.tracebacklimit = 0

    stun_list = [
        "fwa.lifesizecloud.com",
        "global.turn.twilio.com",
        "turn.cloudflare.com",
        "stun.isp.net.au",
        "stun.nextcloud.com",
        "stun.freeswitch.org",
        "stun.voip.blackberry.com",
        "stunserver.stunprotocol.org",
        "stun.sipnet.com",
        "stun.radiojar.com",
        "stun.sonetel.com",
        "stun.telnyx.com",
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
    logging.info("Natter v%s" % __version__)

    check_docker_network()

    stun = StunClient(stun_srv_list)

    natter_addr, outer_addr = stun.get_mapping()
    inner_ip, inner_port = natter_addr
    outer_ip, outer_port = outer_addr

    keepalive_srv = "www.baidu.com"
    keepalive_port = 80
    keep_alive(keepalive_srv, keepalive_port, inner_ip, inner_port)

    # UPnP
    upnp_router = None

    upnp = UPnPClient()
    logging.info("Scanning UPnP Devices...")
    try:
        upnp_router = upnp.discover_router()
    except (OSError, socket.error, ValueError) as ex:
        logging.error("upnp: failed to discover router: %s" % ex)

    if upnp_router:
        logging.info("[UPnP] Found router %s" % upnp_router.ipaddr)
        try:
            upnp.forward("", inner_port, inner_ip, inner_port)
        except (OSError, socket.error, ValueError) as ex:
            logging.error("upnp: failed to forward port: %s" % ex)

    return inner_port, outer_ip, outer_port, upnp
