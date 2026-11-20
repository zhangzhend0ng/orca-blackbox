# 扩样与收敛记录 2026-11-18

最新结论：b6b15eb批次847ce51f7a9e4c03950c21adba792c77已结束，3个已调试旧项SHADOW、填充30%失败、模型平移预检blocked、材料槽3未运行。acceptance_pass=false、release_eligible=false。不继续相似扩样，下一步按[主方案](../V3_PLAN.md)先修fatal停输/有限恢复，再补画布能力，然后冻结未见任务泛化。

## 最新固定批次

source_sha=`b6b15eb5b1f0c382756373f69449d4e2c70f903a`。计划与实际证据只读核对自`artifacts/zcode_pilots/847ce51f7a9e4c03950c21adba792c77/{plan,summary}.json`，每轮正式结果与trace在`artifacts/windows_mcp_harvest/<run>/`，host记录在`artifacts/windows_mcp_host/<run>/`。

| scenario | run | 本批状态 | 正式结果 |
|---|---|---|---|
| quality_a | `3de53e06a5b7448ab20a280b0598178b` | pass | SHADOW、verified_pass=true，实际112层 |
| pilot_strength | `af89824fdb4843f3856757661965851b` | pass | SHADOW、Wall loops3，实际68层 |
| pilot_transform | `79add910a5094c4c8abd8301c061eefe` | blocked | scene_numeric_range_and_canvas_edit_authority_not_ready；未启动GUI |
| pilot_material | `d301c03ab9d24d92a2487ffdc70cf032` | pass | SHADOW、逻辑slot2/对象T1，实际68层 |
| pilot_infill | `0b338e3f5925485b89d82c9200205078` | fail | NON_GREEN、execution_status=failed、verified_pass=false |
| pilot_material3 | `9ddad0b749434228bbd4cd6563011a79` | not_run | 无GUI通过证据 |

这是开发集复样与新增任务尝试，不能称3/3泛化成功。4个已启动run均cleanup_confirmed=true、双方owned Job最终0、harvest teardown确认token不存在；前三轮guest未强杀，填充轮process收据记录forced_termination=true、cancel_reason=adapter_error。不能把最终清理确认冒称过程中即时撤销已正确。

### 填充失败与必须先修的缺口

native_trace共32次工具尝试、13个拒绝。seq4 Click报`native_target_not_owned`；seq5随后仍有成功Click，window记录app_pid=8348；seq7起多次`native_foreground_not_owned`，actor继续调用到seq32。说明没有在第一次fatal身份错误后锁存撤销并停止整轮。native_worker最后报`ProtocolError:project_file_size`，host报`zcode_independent_proof_failed`；没有可验的保存重开切片闭环，填充目标仍未验证。

逐次门禁的报错反映检查点观察到不属于允许对象的目标/前台，源码校验位于原版工具派发前；但trace不是完整OS输入遥测，也不能消除检查到实际派发间的TOCTOU。因此不能仅凭这些拒绝记录断言整轮绝无实际越权输入。特别是拒绝后还有成功调用，不能说fail-closed run停止机制已经通过。最终NON_GREEN阻止了假通过，却不替代运行时及时撤销。

下一阶段必须独立验证fatal latch：首次foreign/授权/guard等fatal立即锁存并停止actor/MCP，随后不得再准许输入。只有owned且证明未派发的控件类型错误才可按新版本合同有限恢复；foreign错误不降为可恢复误点。现有严格结果不重标。

### 保持证据边界

壁环配置回显和实际挤出不代表独立数过三条物理墙线；逻辑slot2/T1不代表物理喷头映射或实印。填充纯检查器17项通过仅是内容反例验证，不填补本轮GUI失败。29f567e旧层高矩阵严格7/8保留原判定，不与本批合并，发布和飞书覆盖率均不放行。

## 旧批次与恢复历史（原失败保留）

afc2ac8后台批次ce6b388018724a65841b7f63b81f4e62已结束：quality_a / 54e4db45a2af4cb08ee8a2acce5bdcf8在3次MCP调用（含1次输入）后因ip_guard_unverified:ValueError安全停止，正式NON_GREEN、cleanup_confirmed、Job0、token删除；下一项39a45e533c524975be2e35081330d642在IPGuard启动前校验失败，未启动GUI/actor，没有正式host结果；matrix因此记录FileNotFoundError，真实根因见其协调器日志。材料a3d210998fdb4ce9b610de87ed8e44f9未执行，平移76a1ef1ec9f449af8e4cfd23b5844f8c预检blocked。保留全部原分母，不把基础设施失败算作新业务验证。

当前guard已恢复ready，PID仍22040；未修改guard/Clash或绕过门禁。坏状态仅保留ValueError，不能断言具体是过期/阻断哪项字段。源码扩样先补齐两个新目标：infill15%→30%与逻辑槽3；目前纯测试通过，真实GUI待验。画布先单独只读probe，确定PFD/class后再接限权输入。

以上“当前guard已恢复ready/真实GUI待验”是旧批次结束后的当时状态，不是本次实时guard证明；本次真实结果以上表为准。旧批次根因只保留ValueError，不能事后猜成特定guard字段失效。
