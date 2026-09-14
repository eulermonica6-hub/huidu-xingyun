"""Neo4j 只读客户端（可选在线层）。

Agent 的图谱真源是 CSV（:class:`~huidu_xingyun.repositories.graph.GraphRepository`）。
本类用于部署期健康检查与只读参数化查询；连接信息只从环境变量读取
（``data_paths.json`` 中 ``neo4j.connection_source = environment_only``）。
"""

from __future__ import annotations

from typing import Any


class Neo4jClient:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j") -> None:
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database

    def health_check(self) -> dict[str, Any]:
        """只读连接健康检查。不返回任何密码或连接串细节。"""
        if not self.password:
            return {"available": False, "reason": "missing_password"}
        try:
            from neo4j import GraphDatabase
        except ImportError:
            return {"available": False, "reason": "neo4j_driver_not_installed"}
        try:
            driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": type(exc).__name__}
        try:
            with driver.session(database=self.database) as session:
                record = session.run("MATCH (n) RETURN count(n) AS count").single()
                count = record["count"] if record else 0
            return {"available": True, "node_count": count}
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": type(exc).__name__}
        finally:
            driver.close()

    def run_readonly(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """执行只读参数化 Cypher，返回记录字典列表。仅供部署/运维脚本使用。"""
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
        try:
            with driver.session(database=self.database) as session:
                result = session.run(query, params or {})
                return [dict(record) for record in result]
        finally:
            driver.close()
