# runner/ — 宿主↔客机跑批基础设施（快照）

`C:\coil\vm_setup\` 里的跑批脚本**原本不受版本控制**；本目录是其参数化快照
（2026-09-02 port），行为与原机等价。`vm_setup` 仍是 live origin——两边当前
都能用；改任何一边记得同步。

## 拓扑

```
宿主 (本仓 runner/)                    Hyper-V 客机 win11-test
─────────────────────                  ─────────────────────────────
hv_go.ps1        ──PS Direct──▶        注册 INTERACTIVE 计划任务 suite
relay_run.py     ──relay_cmd.txt──▶    relay 守护读取并执行，写 relay_out.txt
zstate/zprog/…   ──PS Direct──▶        探测任务状态/进度/日志/截图清单
push_verify.py   ──relay+base64──▶     推文件 + MD5 校验（防静默丢包）
fetch_mp4.py     ◀──relay+base64──     拉取证文件（mp4/日志/gcode）
clean_guest.ps1  ──PS Direct──▶        杀孤儿 app/python
```

协议细节（RUN/DONE 标记、头部变更判定、稳定性窗口）见 `../PITFALLS_0901.md`
§15/§16/§17——这些脚本就是那些坑的实体化。

## 参数（环境变量，均有当前 live 缺省）

| 变量 | 缺省 | 说明 |
|---|---|---|
| `ORCA_BB_VM` | `win11-test` | 客机 VM 名 |
| `ORCA_BB_GUEST_USER` / `ORCA_BB_GUEST_PASS` | `test` / `123456` | 客机 autologon 凭据（一次性隔离测试 VM，非机密；换真机务必覆盖） |
| `ORCA_BB_GUEST_SANDBOX` | monorepo worktree 内 `sandboxes\vision_gui` | 客机侧套件检出路径。**迁移待办**：客机检出本仓后改指新路径 |
| `ORCA_BB_GUEST_PYTHON` | `C:\Python311\python.exe` | 客机 python |
| `ORCA_BB_GUEST_TOOLS` | `C:\coil\vm_setup_guest` | 客机侧 relay 工具目录（zraw 用） |
| `ORCA_BB_VM_SETUP`（仅 .py） | `C:\coil\vm_setup` | 宿主 relay 目录（relay_cmd/relay_out/send_to_guest.ps1） |

PowerShell 脚本共用 `runner\_common.ps1`（dot-source）；Python 脚本各自读同样的
环境变量。

## 用法（宿主提权窗口，或经 relay）

```powershell
& runner\hv_go.ps1                          # 全套 35 例（m3j..m5h）
& runner\hv_go.ps1 m5g_preset_manage        # 单例/子集
python runner\relay_run.py "Get-Date"       # 经 relay 跑任意命令
python runner\push_verify.py local.py guest\target.py
python runner\fetch_mp4.py C:\guest\x.mp4 host_x.mp4
```

## 已知边界

- `relay_cmd.txt`/`relay_out.txt` 的宿主 FIFO 与客机 relay 守护不在本仓（属
  vm_setup/vm_setup_guest 基础设施）；`send_to_guest.ps1` 同理——push_verify 依赖它。
- 客机检出 = GitHub tarball（客机无 git）：`Invoke-WebRequest
  https://codeload.github.com/zhangzhend0ng/orca-blackbox/tar.gz/refs/heads/main`
  解包到 `C:\coil\orca-blackbox`，跑 `tools/check_registry.py` 验证。
