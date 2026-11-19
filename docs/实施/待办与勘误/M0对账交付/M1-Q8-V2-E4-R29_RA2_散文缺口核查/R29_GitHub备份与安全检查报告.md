# R29 GitHub 备份与安全检查报告

## 一、备份

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/sssxzl/ProtoKG |
| 分支 | `backup/r29-pre-stage-audit` |
| 分支 URL | https://github.com/sssxzl/ProtoKG/tree/backup/r29-pre-stage-audit |
| 固定 commit | `e4dd16824290fb715ce4443e75de31a06fdfc9d9` |
| 提交链接 | https://github.com/sssxzl/ProtoKG/commit/e4dd16824290fb715ce4443e75de31a06fdfc9d9 |
| 推送方式 | 新建分支，非 force，未改写历史 |

## 二、main 对照

| 项 | 值 |
|---|---|
| 推送前 main | `0f99da8445ea093246824e62d1244b88732e009e` |
| 推送后 main | 同（远端 `ls-remote` 复核） |

## 三、安全检查

| 检查 | 结果 |
|---|---|
| 跟踪文件含 `sk-<32hex>` / `ghp_` / 私钥头 | **未发现** |
| `.env` 是否入库 | 否（仅 `.env.example`，全是占位注释） |
| 最近 80 个提交的历史扫描 | 未命中真实密钥格式 |
| 大文件 | 最大 5 MB（`packets.ndjson`），无异常巨型文件 |

**未改写任何历史提交**；如后续发现历史泄漏，需单独评估，不在本轮处理。

## 四、完整性

| 项 | 值 |
|---|---|
| 跟踪文件 | 8 210 |
| 源码 `core/**/*.py` | 82 |
| 测试 `tests/**` | 157 |
| 文档 `docs/**/*.md` | 572 |
| 远端 HEAD 与本地 HEAD 一致 | 是（`e4dd168`） |

## 五、GitHub Actions

推送可能触发 CI；本轮只记录，不启动 CI 调试。

## 六、说明

- 本次推送是用户批准的备份网络操作，与离线实验的"零网络"记录分开统计；
- 未修改 main、未合并分支、未改业务代码。
