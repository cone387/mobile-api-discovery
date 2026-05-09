"""环境管理模块

负责通过 adb 管理设备连接、证书安装、代理设置、mitmdump 启动和清理。
每个步骤失败时返回具体错误信息和建议。
"""

import asyncio
from typing import Optional

from .models import ConnectionResult, CertResult, ProxyResult, ProcessResult


class EnvironmentManager:
    """环境管理器

    通过 adb 管理设备连接、证书安装、代理设置，
    以及启动/停止 mitmdump 进程。
    """

    def __init__(self) -> None:
        self._mitmdump_process: Optional[asyncio.subprocess.Process] = None

    async def check_device(self, device_id: str) -> ConnectionResult:
        """验证设备连接状态

        通过 `adb -s {device_id} get-state` 检查设备是否已连接。

        Args:
            device_id: 设备标识符

        Returns:
            ConnectionResult: 包含连接状态、错误信息和建议
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "get-state",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                state = stdout.decode().strip()
                if state == "device":
                    return ConnectionResult(
                        success=True,
                        device_id=device_id,
                    )
                else:
                    return ConnectionResult(
                        success=False,
                        device_id=device_id,
                        error=f"设备状态异常: {state}",
                        suggestion="请确认设备已解锁并授权 USB 调试，然后重试。",
                    )
            else:
                error_msg = stderr.decode().strip() or "未知错误"
                return ConnectionResult(
                    success=False,
                    device_id=device_id,
                    error=f"adb 连接失败: {error_msg}",
                    suggestion="请检查: 1) 设备已通过 USB 连接 2) USB 调试已开启 3) 已授权此电脑调试。可尝试 `adb devices` 查看设备列表。",
                )
        except FileNotFoundError:
            return ConnectionResult(
                success=False,
                device_id=device_id,
                error="未找到 adb 命令",
                suggestion="请确认已安装 Android SDK Platform Tools 并将 adb 添加到 PATH 环境变量。",
            )
        except Exception as e:
            return ConnectionResult(
                success=False,
                device_id=device_id,
                error=f"检查设备时发生异常: {str(e)}",
                suggestion="请检查 adb 服务是否正常运行，可尝试 `adb kill-server && adb start-server`。",
            )

    async def install_certificate(self, device_id: str) -> CertResult:
        """安装 CA 证书到系统证书目录

        使用 tmpfs overlay 方式将 mitmproxy CA 证书安装到设备的系统证书目录。
        需要设备已 root。

        步骤:
        1. 挂载 tmpfs 到 /system/etc/security/cacerts
        2. 复制证书文件到系统证书目录

        Args:
            device_id: 设备标识符

        Returns:
            CertResult: 包含安装状态、错误信息和建议
        """
        try:
            # Step 1: 使用 tmpfs overlay 挂载系统证书目录
            mount_cmd = "su 0 mount -t tmpfs tmpfs /system/etc/security/cacerts"
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "shell", mount_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or stdout.decode().strip() or "挂载失败"
                return CertResult(
                    success=False,
                    error=f"tmpfs 挂载失败: {error_msg}",
                    suggestion="请确认设备已 root，且 su 命令可用。可尝试手动执行: adb shell su 0 mount -t tmpfs tmpfs /system/etc/security/cacerts",
                )

            # Step 2: 复制证书文件到系统证书目录
            copy_cmd = "cp /data/local/tmp/certs/* /system/etc/security/cacerts/"
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "shell", copy_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or stdout.decode().strip() or "复制失败"
                return CertResult(
                    success=False,
                    error=f"证书复制失败: {error_msg}",
                    suggestion="请确认已将 mitmproxy CA 证书推送到 /data/local/tmp/certs/ 目录。可使用: adb push ~/.mitmproxy/mitmproxy-ca-cert.cer /data/local/tmp/certs/",
                )

            return CertResult(success=True)

        except FileNotFoundError:
            return CertResult(
                success=False,
                error="未找到 adb 命令",
                suggestion="请确认已安装 Android SDK Platform Tools 并将 adb 添加到 PATH 环境变量。",
            )
        except Exception as e:
            return CertResult(
                success=False,
                error=f"安装证书时发生异常: {str(e)}",
                suggestion="请检查设备连接状态和 root 权限。",
            )

    async def set_proxy(self, device_id: str, host: str, port: int) -> ProxyResult:
        """设置设备 HTTP 代理

        通过 adb 将设备的全局 HTTP 代理设置为指定的主机和端口。

        Args:
            device_id: 设备标识符
            host: 代理主机地址
            port: 代理端口

        Returns:
            ProxyResult: 包含设置状态、错误信息和建议
        """
        try:
            proxy_value = f"{host}:{port}"
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "shell",
                "settings", "put", "global", "http_proxy", proxy_value,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or stdout.decode().strip() or "设置失败"
                return ProxyResult(
                    success=False,
                    error=f"代理设置失败: {error_msg}",
                    suggestion="请检查设备是否已连接，以及是否有权限修改系统设置。",
                )

            return ProxyResult(
                success=True,
                host=host,
                port=port,
            )

        except FileNotFoundError:
            return ProxyResult(
                success=False,
                error="未找到 adb 命令",
                suggestion="请确认已安装 Android SDK Platform Tools 并将 adb 添加到 PATH 环境变量。",
            )
        except Exception as e:
            return ProxyResult(
                success=False,
                error=f"设置代理时发生异常: {str(e)}",
                suggestion="请检查设备连接状态和网络设置权限。",
            )

    async def start_mitmdump(self, addon_path: str, port: int) -> ProcessResult:
        """启动 mitmdump 进程

        启动 mitmdump 子进程并加载指定的 addon 脚本。

        Args:
            addon_path: addon 脚本路径
            port: mitmdump 监听端口

        Returns:
            ProcessResult: 包含启动状态、进程 PID、错误信息和建议
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "mitmdump",
                "--set", "block_global=false",
                "-s", addon_path,
                "-p", str(port),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # 短暂等待以检测是否立即退出（如端口占用）
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
                # 如果进程在 1 秒内退出，说明启动失败
                stderr_output = ""
                if process.stderr:
                    stderr_data = await process.stderr.read()
                    stderr_output = stderr_data.decode().strip()
                return ProcessResult(
                    success=False,
                    error=f"mitmdump 启动后立即退出 (returncode={process.returncode}): {stderr_output}",
                    suggestion=f"请检查端口 {port} 是否被占用（`lsof -i :{port}`），以及 addon 脚本路径是否正确。",
                )
            except asyncio.TimeoutError:
                # 进程仍在运行，说明启动成功
                self._mitmdump_process = process
                return ProcessResult(
                    success=True,
                    pid=process.pid,
                )

        except FileNotFoundError:
            return ProcessResult(
                success=False,
                error="未找到 mitmdump 命令",
                suggestion="请确认已安装 mitmproxy: pip install mitmproxy",
            )
        except Exception as e:
            return ProcessResult(
                success=False,
                error=f"启动 mitmdump 时发生异常: {str(e)}",
                suggestion=f"请检查 mitmproxy 是否正确安装，以及端口 {port} 是否可用。",
            )

    async def cleanup(self, device_id: str) -> None:
        """清理代理设置

        将设备的 HTTP 代理重置为空（:0 表示清除代理）。
        同时终止 mitmdump 进程（如果正在运行）。

        Args:
            device_id: 设备标识符
        """
        # 清除设备代理设置
        try:
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "shell",
                "settings", "put", "global", "http_proxy", ":0",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
        except Exception:
            pass  # cleanup 阶段忽略错误

        # 终止 mitmdump 进程
        if self._mitmdump_process is not None:
            try:
                self._mitmdump_process.terminate()
                await self._mitmdump_process.wait()
            except Exception:
                pass  # cleanup 阶段忽略错误
            finally:
                self._mitmdump_process = None
