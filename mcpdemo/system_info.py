#!/usr/bin/env python3
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime

import psutil


def bytes_to_human(n: int) -> str:
    symbols = ("B", "KB", "MB", "GB", "TB", "PB")
    prefix = {}
    for i, s in enumerate(symbols[1:], 1):
        prefix[s] = 1 << (i * 10)
    for s in reversed(symbols[1:]):
        if n >= prefix[s]:
            value = float(n) / prefix[s]
            return f"{value:.2f} {s}"
    return f"{n} B"


def safe_sysctl_get(key: str):
    try:
        out = subprocess.check_output(["sysctl", "-n", key], stderr=subprocess.DEVNULL).decode().strip()
        return out
    except Exception:
        return None


def cpu_info():
    info = {}
    uname = platform.uname()
    info["architecture"] = platform.machine() or uname.machine
    info["physical_cores"] = psutil.cpu_count(logical=False)
    info["total_cores"] = psutil.cpu_count(logical=True)

    # frequency
    try:
        freq = psutil.cpu_freq()
        if freq:
            info["max_frequency_mhz"] = round(freq.max, 2)
            info["min_frequency_mhz"] = round(freq.min, 2)
            info["current_frequency_mhz"] = round(freq.current, 2)
        else:
            info["max_frequency_mhz"] = info["min_frequency_mhz"] = info["current_frequency_mhz"] = None
    except Exception:
        info["max_frequency_mhz"] = info["min_frequency_mhz"] = info["current_frequency_mhz"] = None

    # utilization snapshot (short interval to avoid long wait)
    try:
        info["total_usage_percent"] = psutil.cpu_percent(interval=0.3)
        info["per_core_usage_percent"] = psutil.cpu_percent(interval=0.3, percpu=True)
    except Exception:
        info["total_usage_percent"] = None
        info["per_core_usage_percent"] = None

    # Vendor / brand (best effort)
    brand = None
    if sys.platform == "darwin":
        brand = safe_sysctl_get("machdep.cpu.brand_string")
        if brand is None:
            brand = uname.processor or platform.processor() or None
        # cache sizes (bytes)
        l1i = safe_sysctl_get("hw.l1icachesize")
        l1d = safe_sysctl_get("hw.l1dcachesize")
        l2 = safe_sysctl_get("hw.l2cachesize")
        l3 = safe_sysctl_get("hw.l3cachesize")
        info["l1i_cache"] = bytes_to_human(int(l1i)) if l1i and l1i.isdigit() else None
        info["l1d_cache"] = bytes_to_human(int(l1d)) if l1d and l1d.isdigit() else None
        info["l2_cache"] = bytes_to_human(int(l2)) if l2 and l2.isdigit() else None
        info["l3_cache"] = bytes_to_human(int(l3)) if l3 and l3.isdigit() else None
    else:
        brand = platform.processor() or uname.processor or None
        # Linux cache sizes could be read from /sys, but keep it simple and portable
        info["l1i_cache"] = info["l1d_cache"] = info["l2_cache"] = info["l3_cache"] = None

    info["brand"] = brand
    return info


def memory_info():
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    return {
        "total": bytes_to_human(vm.total),
        "available": bytes_to_human(vm.available),
        "used": bytes_to_human(vm.used),
        "free": bytes_to_human(vm.free),
        "percent": vm.percent,
        "swap_total": bytes_to_human(sm.total),
        "swap_used": bytes_to_human(sm.used),
        "swap_free": bytes_to_human(sm.free),
        "swap_percent": sm.percent,
    }


def disk_info():
    disks = []
    for part in psutil.disk_partitions(all=False):
        # Skip some virtual or inaccessible mounts gracefully
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            usage = None
        disks.append({
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
            "opts": part.opts,
            "total": bytes_to_human(usage.total) if usage else None,
            "used": bytes_to_human(usage.used) if usage else None,
            "free": bytes_to_human(usage.free) if usage else None,
            "percent": usage.percent if usage else None,
        })
    return disks


def network_info():
    info = {"hostname": socket.gethostname()}
    # Try to get primary IP (non-loopback)
    primary_ip = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            primary_ip = s.getsockname()[0]
    except Exception:
        pass
    if not primary_ip:
        try:
            primary_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            primary_ip = None
    info["primary_ip"] = primary_ip

    # Interfaces brief
    if_addrs = psutil.net_if_addrs()
    if_stats = psutil.net_if_stats()
    brief = {}
    for name, addrs in if_addrs.items():
        ips = []
        for addr in addrs:
            if getattr(socket, "AF_LINK", object()) == addr.family:
                continue
            if addr.family == socket.AF_INET:
                ips.append(addr.address)
        st = if_stats.get(name)
        brief[name] = {
            "isup": getattr(st, "isup", None),
            "speed_mbps": getattr(st, "speed", None),
            "mtu": getattr(st, "mtu", None),
            "ipv4": ips,
        }
    info["interfaces"] = brief
    return info


def os_info():
    uname = platform.uname()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    return {
        "system": uname.system,
        "node_name": uname.node,
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "processor": uname.processor,
        "python": sys.version.split(" ")[0],
        "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def battery_info():
    try:
        batt = psutil.sensors_battery()
    except Exception:
        batt = None
    if not batt:
        return None
    return {
        "percent": batt.percent,
        "plugged": batt.power_plugged,
        "secsleft": batt.secsleft,
    }


def print_section(title: str):
    print("\n" + title)
    print("-" * len(title))


def print_kv(key: str, value):
    print(f"{key:>24}: {value}")


def get_host_info():
    return {
        "os": os_info(),
        "cpu": cpu_info(),
        "memory": memory_info(),
        "disks": disk_info(),
        "network": network_info(),
        "battery": battery_info(),
    }


def main():
    import json

    data = get_host_info()

    if "--json" in sys.argv:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    # Pretty print
    print_section("操作系统")
    for k, v in data["os"].items():
        print_kv(k, v)

    print_section("CPU 信息")
    for k in ["brand", "architecture", "physical_cores", "total_cores",
              "current_frequency_mhz", "min_frequency_mhz", "max_frequency_mhz",
              "total_usage_percent"]:
        print_kv(k, data["cpu"].get(k))
    # caches
    for k in ["l1i_cache", "l1d_cache", "l2_cache", "l3_cache"]:
        if data["cpu"].get(k) is not None:
            print_kv(k, data["cpu"][k])

    if isinstance(data["cpu"].get("per_core_usage_percent"), list):
        for idx, val in enumerate(data["cpu"]["per_core_usage_percent"], 1):
            print_kv(f"core_{idx}_usage_%", val)

    print_section("内存")
    for k in ["total", "available", "used", "free", "percent",
              "swap_total", "swap_used", "swap_free", "swap_percent"]:
        print_kv(k, data["memory"].get(k))

    print_section("磁盘")
    for d in data["disks"]:
        print_kv("device", d.get("device"))
        print_kv("mountpoint", d.get("mountpoint"))
        print_kv("fstype", d.get("fstype"))
        print_kv("total", d.get("total"))
        print_kv("used", d.get("used"))
        print_kv("free", d.get("free"))
        print_kv("percent", d.get("percent"))
        print("")

    print_section("网络")
    print_kv("hostname", data["network"].get("hostname"))
    print_kv("primary_ip", data["network"].get("primary_ip"))
    for name, brief in data["network"].get("interfaces", {}).items():
        print_kv("interface", name)
        print_kv("  isup", brief.get("isup"))
        print_kv("  speed_mbps", brief.get("speed_mbps"))
        print_kv("  mtu", brief.get("mtu"))
        if brief.get("ipv4"):
            print_kv("  ipv4", ", ".join(brief["ipv4"]))
        print("")

    if data["battery"]:
        print_section("电池")
        for k, v in data["battery"].items():
            print_kv(k, v)


if __name__ == "__main__":
    main()