#!/usr/bin/env python3
"""
MCP Server wrapping get_host_info()
Run via stdio (default): python mcp_server.py
"""
from mcp.server.fastmcp import FastMCP
from system_info import get_host_info as _get_host_info

app = FastMCP("host-info")


@app.tool()
def get_host_info() -> dict:
    """获取主机信息：CPU、内存、磁盘、网络、操作系统等。以 JSON 对象返回。"""
    return _get_host_info()


if __name__ == "__main__":
    app.run(transport="stdio")