# ChatAFL 代理 VM 端部署方案（每 fuzz 内嵌代理，默认启动，必走代理，保证增强种子合规）

> 日期：2026-10-26
> 前置文档：`ChatAFL代理层改写_实现方案.md`（代理层响应改写已实现并验证通过）
> 目标：把代理从 Windows 宿主（192.168.37.1）下沉到实验 VM（192.168.37.130）端，每个 ChatAFL fuzz 容器内嵌一个代理，随 fuzz 默认启动，ChatAFL 的每次 LLM 调用都必经代理的响应改写层，确保增强种子是合规纯 RTSP 报文。

---

## 0. 结论先行

| # | 结论 |
|---|---|
| 0.1 | **核心改造只有两件事**：① 改 ChatAFL 源码里硬编码的 LLM URL 为容器内回环 `127.0.0.1:18080`（并支持环境变量覆盖）后重编译镜像；② 容器启动时先起内嵌代理再起 afl-fuzz。 |
| 0.2 | **「必走代理」是 URL 层天然保证的**：URL 改成 `127.0.0.1` 后，ChatAFL 的 LLM 调用只能打到容器内代理，无法绕过（即使容器有外网，它也只访问回环地址）。不需要额外的网络隔离。 |
| 0.3 | **容器网络从 `--network none` 改为 `bridge`**：因为内嵌代理要转发到 DeepSeek 外网。已实测 VM 与容器均能访问 `api.deepseek.com`（VM 200/0.96s；容器 401 是没带 key 的认证错误，非网络问题，DNS 223.5.5.5 正常）。 |
| 0.4 | **合规保障复用已实现模块**：`response_rewriter.py`（28 例测试全绿）在代理内做响应改写，增强/stall 路径剥离散文、语法抽取路径透传。 |

---

## 1. 现状与问题

### 1.1 当前链路

```
ChatAFL 容器 (VM 内)
  └─ afl-fuzz --network none  ──✗──>  宿主代理 192.168.37.1:18080  ──>  DeepSeek API
```

- ChatAFL 的 LLM URL **硬编码**在 `chat-llm.c:53/57`：`http://192.168.37.1:18080/chat/completions`（宿主的 VMnet8 IP）。
- 代理当前跑在 Windows 宿主（`scripts/llm_proxy.py`，监听 `192.168.37.1:18080`）。
- RQ3 用 `--network none` 让容器无法访问宿主代理 → 启动期增强被"关闭"（LLM 调用失败返回 NULL，不写增强种子）。这是之前为隔离污染变量而做的临时手段，**代价是增强能力整个被牺牲**。

### 1.2 用户新诉求

1. 代理部署到 VM 端。
2. 每起一个 ChatAFL fuzz 容器，就配一个代理，**默认启动**。
3. 每次调大模型**必走**代理环节。
4. 确保增强后的种子**合规**（纯 RTSP 报文，无散文）。

---

## 2. 目标架构（方案 A：容器内嵌代理，推荐）

```
ChatAFL fuzz 容器 (VM 内, --network bridge)
  ├─ afl-fuzz  ──>  127.0.0.1:18080 (容器内代理)  ──>  DeepSeek API (外网, 经 VM NAT)
  │                    │
  │                    ├─ llm_proxy.py          (HTTP 转发 + 重试)
  │                    └─ response_rewriter.py  (响应改写：剥离散文→纯报文)
  └─ (代理随容器启动/销毁，默认后台常驻)
```

- **每个 fuzz 容器自包含一个代理**，监听容器内回环 `127.0.0.1:18080`。
- **ChatAFL 的 LLM URL 改为 `127.0.0.1:18080`** → 所有 LLM 调用只能进容器内代理。
- 代理转发到 DeepSeek（`https://api.deepseek.com/v1/chat/completions`），响应经改写层剥离散文后回传。

### 为什么选「容器内嵌」而不是「VM 全局一个」

| 维度 | A 容器内嵌（推荐） | B VM 全局一个 |
|---|---|---|
| 隔离性 | 每 fuzz 独立，互不影响 | 单点，一个挂全挂 |
| 「必走代理」 | URL=127.0.0.1 天然保证 | URL=VM_IP，靠配置保证 |
| 日志/排障 | 随容器隔离 | 集中但混杂 |
| 资源 | 每容器约 +1 个 python3 进程（~50MB） | 1 个进程 |
| 符合用户「每 fuzz 配一个」 | ✅ 严格一对一 | ❌ 非一对一 |

用户明确要「每个 fuzz 都配一个」，故**推荐 A**。若后续想省资源，可退回 B（代理监听 VM 的 `0.0.0.0:18080`，URL 改 `192.168.37.130:18080`）。

---

## 3. 关键决策

### 3.1 改 URL 的方式：直接改 + 支持环境变量覆盖

`chat-llm.c` 第 45–60 行现状（instruct/turbo 两分支硬编码同一个 URL）：

```c
char *chat_with_llm(char *prompt, char *model, int tries, float temperature)
{
    ...
    char *url = NULL;
    if (strcmp(model, "instruct") == 0)  url = "http://192.168.37.1:18080/chat/completions";
    else                                url = "http://192.168.37.1:18080/chat/completions";
    ...
}
```

改为（统一 + 环境变量覆盖，默认容器内回环）：

```c
    char *url = getenv("CHATAFL_LLM_URL");
    if (url == NULL || url[0] == '\0')
        url = "http://127.0.0.1:18080/chat/completions";
```

- 需要确认 `chat-llm.c` 已 `#include <stdlib.h>`（getenv 声明；该文件用 malloc/strdup，几乎必然已包含）。
- **默认值 `127.0.0.1:18080`** 让「不设环境变量」时也走容器内代理。
- `DEEPSEEK_TOKEN`（`chat-llm.h:15`）**不用改**：ChatAFL 的 Authorization 头打给容器内代理，代理转发时用自己的 token，代理不校验上游 token，保持原样无害。

### 3.2 容器网络：`--network none` → `--network bridge`

- `--network none` 原本只为关增强；现在要启用增强 + 代理转发外网，改用 `bridge`（默认）。
- 已实测：容器 bridge 能访问外网、能访问 VM IP、DNS 正常（见 §1 前提）。
- 「必走代理」不依赖网络隔离，依赖 URL=127.0.0.1（见 0.2）。

### 3.3 代理配置调整

现有 `llm_proxy.py` 的 `LISTEN_HOST` 默认 `192.168.37.1`。容器内应监听回环：

- 通过环境变量覆盖：`LLM_PROXY_HOST=127.0.0.1 LLM_PROXY_PORT=18080 python3 /proxy/llm_proxy.py`
- 或在容器内放一份 `LISTEN_HOST=127.0.0.1` 的定制副本。

其余（`LLM_PROXY_MODEL=deepseek-chat`、`LLM_PROXY_REWRITE=1`、`LLM_PROXY_DEEPSEEK_KEY`、超时/重试）沿用现有环境变量，默认即可。

---

## 4. 镜像改造步骤（一次性）

1. **改源码**：`chat-llm.c:45–60` 按 §3.1 改为 `getenv("CHATAFL_LLM_URL")` + 默认 `127.0.0.1:18080`。
2. **打包代理进镜像**（在 Dockerfile 或 `docker commit` 时）：
   - `scripts/response_rewriter.py` → 镜像 `/proxy/response_rewriter.py`
   - `scripts/llm_proxy.py` → 镜像 `/proxy/llm_proxy.py`（或定制 LISTEN_HOST=127.0.0.1 副本）
3. **重编译 afl-fuzz**：镜像内 `cd /home/ubuntu/chatafl && make`（gcc/make 齐备，已实测）。
4. **验证镜像**：`docker run --rm --network bridge $IMG bash -c 'python3 --version && ls /proxy/'`，确认 python3 + 代理脚本在位。

---

## 5. 容器启动流程改造（编排脚本）

`rq3_orchestrate.sh` 的 `launch()` 里两处改动：

### 5.1 网络参数

```bash
--network none   →   --network bridge
```

### 5.2 启动命令：先起代理，再起 fuzz

```bash
docker run -d --name $name --user root --cpus=1 --memory=1.5g --network bridge \
  -v $seeds:/seeds_ro:ro -v $out:/out -v $DICT_ROOT:/dict_rw:ro \
  $IMG bash -c '
    cp -r /seeds_ro /seeds_work &&
    (LLM_PROXY_HOST=127.0.0.1 LLM_PROXY_PORT=18080 \
       python3 /proxy/llm_proxy.py > /proxy/proxy.log 2>&1 &) &&
    sleep 2 &&
    /home/ubuntu/chatafl/afl-fuzz -d -i /seeds_work -x /dict_rw/xxx.dict -o /out \
      -N tcp://127.0.0.1/$PORT_BASE -P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 1000 \
      -- ./testOnDemandRTSPServer $PORT_BASE'
```

要点：
- `sleep 2` 保证 afl-fuzz 启动时代理已在监听（2 秒足够 python3 起 HTTP server；可改为轮询 `curl 127.0.0.1:18080` 就绪更稳）。
- 代理日志落 `/proxy/proxy.log`（容器内），排障时 `docker exec $name tail /proxy/proxy.log`。

---

## 6. 合规保障机制

- **改写层（`response_rewriter.py`）** 已在代理内生效：增强/stall 路径剥离散文、只留纯 RTSP 报文；语法抽取路径透传；未知路径透传。
- **失败安全**：抽取不到合法报文 → 置空 content → ChatAFL 因空 content 跳过写入（不产生脏种子）。
- **验证断言**（编排脚本可加）：实验启动后 `docker exec $name grep -c '改写\[enrich\] 成功' /proxy/proxy.log` 有命中；且 `/seeds_work` 里 `enriched_*` 文件首行即合法 RTSP 请求行。

---

## 7. 风险与应对

| # | 风险 | 应对 |
|---|---|---|
| 1 | 容器外网不可达 | 已实测 bridge 可达 DeepSeek；若换网络环境，加 `--dns 223.5.5.5` 兜底 |
| 2 | DeepSeek 429 限流（多容器并发） | 代理已带 429/5xx 线性退避重试；必要时 `LLM_PROXY_RETRIES` 调大或限并发 |
| 3 | 每容器多一个代理进程的开销 | 约 +50MB 内存/容器，`--memory=1.5g` 内可承受 |
| 4 | 代理 crash 导致 LLM 调用失败 | ChatAFL 侧 LLM 失败返回 NULL → 增强跳过（降级为无增强，不污染），且代理有 `> /proxy/proxy.log` 日志可查 |
| 5 | 重编译成本 | 一次性；改 URL + make 即可，且加 getenv 后**以后无需再改源码** |
| 6 | `--network bridge` 让容器能上外网 | 无安全顾虑：ChatAFL URL=127.0.0.1 不会直连外网，代理只访问 api.deepseek.com |
| 7 | instruct 分支死代码 | 已合并为统一 getenv 读取，天然消除 |

---

## 8. 部署与测试步骤（可执行）

```bash
# 1) 改 chat-llm.c（§3.1）+ 打包代理（§4）后重编译镜像
docker exec -it <builder> bash -c 'cd /home/ubuntu/chatafl && make'
docker commit <builder> rq2-live555:proxy

# 2) 冒烟测试：单容器起代理 + 手动打增强 prompt
docker run -d --name smoke --network bridge rq2-live555:proxy bash -c \
  'python3 /proxy/llm_proxy.py > /proxy/proxy.log 2>&1 & sleep 2; sleep 999'
docker exec smoke bash -c 'curl -s -X POST http://127.0.0.1:18080/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"deepseek-chat\",\"messages\":[{\"role\":\"system\",\"content\":\"You are a helpful assistant.\"},{\"role\":\"user\",\"content\":\"The following is one sequence of client requests:\\nDESCRIBE rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0\\nCSeq: 1\\nAccept: application/sdp\\n\\nPlease add the SETUP client requests in the proper locations, and the modified sequence of client requests is:\"}]}"'
docker exec smoke tail -5 /proxy/proxy.log   # 期望看到「改写[enrich] 成功」

# 3) 全量编排：改 launch() 后重跑，加合规断言
#    （enriched_* 首行即合法请求行；proxy.log 有改写命中）

# 4) 确认宿主代理不再被使用（可停掉 Windows 侧 llm_proxy.py）
```

---

## 9. 待你确认后实施

方案到此。实施要点集中在：**改一行 URL（+getenv）→ 重编译镜像 → 容器启动命令前置起代理 → 网络改 bridge → 编排加合规断言**。

如需，我可按 §8 步骤直接落地（改源码、重编译镜像、冒烟测试、改造编排脚本）。
