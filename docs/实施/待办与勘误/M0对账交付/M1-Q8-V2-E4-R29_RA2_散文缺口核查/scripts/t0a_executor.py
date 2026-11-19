# -*- coding: utf-8 -*-
"""T0-A 真实执行器（G1–G4）：门禁、隔离、完整链路、状态与证据。

本模块不联网运行；联网需 --execute + 环境双开关。测试一律注入 Stub。
"""
from __future__ import annotations

import hashlib, json, os, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))

from core.fused.extraction import prose_semantics as PS   # noqa: E402
from core.fused.extraction import norm as NM              # noqa: E402
from core.fused.hub import hub_entities as HE             # noqa: E402
from hub_isolated import isolated_hub                     # noqa: E402
import t0a_adapter as AC                                  # noqa: E402

MAX_CALLS, MAX_TOKENS, MAX_IN, CAP_CNY = 2, 4000, 7500, 0.15
PRICE_IN_PEAK, PRICE_OUT_PEAK = 2.0, 8.0

STATUS = ("preflight_failed", "request_failed", "request_timeout",
          "response_truncated", "response_invalid", "source_validation_failed",
          "cache_incomplete", "canonical_failed", "hub_failed", "completed")


class Guard:
    """请求前硬门禁：调用数、输入量、费用、状态、参数。"""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.calls = 0
        self.used_in = 0
        self.spent = 0.0
        self.stopped = False
        self.log: list[dict] = []
        self.last_error = ""          # 最近一次调用异常的类名
        self.billing_status = "none"  # none / billed / unknown / partial

    def before(self, est_in: int, params: dict) -> None:
        if self.stopped:
            raise RuntimeError("state_stopped")
        if self.calls >= MAX_CALLS:
            raise RuntimeError("call_limit_exceeded")
        if self.used_in + est_in > MAX_IN:
            raise RuntimeError("input_limit_exceeded")
        worst = est_in * PRICE_IN_PEAK / 1e6 + MAX_TOKENS * PRICE_OUT_PEAK / 1e6
        if self.spent + worst > CAP_CNY:
            raise RuntimeError("cost_limit_exceeded")
        AC.assert_payload_ok(params)      # 校验真实即将发送的参数，不做常量替换
        self.calls += 1
        self.log.append({"attempt": self.calls, "est_in": est_in,
                         "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        _atomic_write(self.root / "evidence" / "guard.json",
                      {"calls": self.calls, "used_in": self.used_in,
                       "spent_cny": round(self.spent, 6), "log": self.log})

    def after(self, meta: dict) -> None:
        _in = int(meta.get("input_tokens") or 0)
        _out = int(meta.get("output_tokens") or 0)
        self.used_in += _in
        self.spent += (_in * PRICE_IN_PEAK + _out * PRICE_OUT_PEAK) / 1e6
        if _in > 0 and _in > 1.5 * (self.log[-1]["est_in"] or 1):
            self.stopped = True

    def stop(self) -> None:
        self.stopped = True


class GuardedClient:
    """包住任意 client：每次真实调用前过门禁。"""
    model = ""
    def __init__(self, inner, guard: Guard):
        self.inner, self.guard, self.last_call_meta = inner, guard, None
        self.calls = 0

    def chat_json(self, *, system, user, temperature, max_tokens):
        est = max(1, len(user) // 4)
        params = {"model": AC.MODEL, "thinking": {"type": "disabled"},
                  "response_format": {"type": "json_object"},
                  "temperature": temperature, "max_tokens": max_tokens}
        self.guard.before(est, params)
        self.calls += 1
        try:
            out = self.inner.chat_json(system=system, user=user,
                                       temperature=temperature, max_tokens=max_tokens)
        except TimeoutError as exc:
            self.guard.last_error = "TimeoutError"
            self.guard.billing_status = "unknown"    # 可能已被计费
            self.guard.stop(); raise
        except Exception as exc:                   # noqa: BLE001
            self.guard.last_error = type(exc).__name__
            _meta = getattr(self.inner, "last_call_meta", None) or {}
            if _meta.get("input_tokens") is not None:
                self.guard.after(_meta)              # 已收到 usage ⇒ 必须记账
                self.guard.billing_status = "billed"
            else:
                self.guard.billing_status = "unknown"
            self.guard.stop(); raise
        self.last_call_meta = getattr(self.inner, "last_call_meta", None) or {}
        self.guard.after(self.last_call_meta)
        return out


PROTECTED = [ROOT / "derived", ROOT / "kb", ROOT / ".git", ROOT / "profiles"]


def _allowed_base() -> list[pathlib.Path]:
    import tempfile
    bases = [pathlib.Path(tempfile.gettempdir()).resolve()]
    env = os.environ.get("T0A_WORKSPACE")
    if env:
        bases.append(pathlib.Path(env).resolve())
    return bases


def _unsafe_reason(root) -> str:
    """在 resolve 之前检查原始路径；再查每一级父目录的符号链接与受保护目录。"""
    raw = pathlib.Path(root)
    if not raw.is_absolute():
        return "not_absolute"
    if ".." in raw.parts:
        return "dotdot"
    # 任一父级是符号链接即拒绝（含 root 自身）
    cur = raw
    for _ in range(60):
        if cur.is_symlink():
            return f"symlink:{cur.name}"
        if cur.parent == cur:
            break
        cur = cur.parent
    resolved = raw.resolve()
    if resolved.parent == resolved:
        return "filesystem_root"
    if resolved == ROOT.resolve():
        return "repo_root"
    if not any(b == resolved or b in resolved.parents for b in _allowed_base()):
        return "outside_workspace"
    for p in PROTECTED:
        if resolved == p or p in resolved.parents:
            return f"protected:{p.name}"
    return ""


def write_facts_by_aspect(facts, fdir: pathlib.Path) -> dict:
    """用官方 view 序列化，并按 fact_key.aspect 分文件；返回 aspect → 条数。"""
    from core.fused.hub.export import get_fact_view
    fdir.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list] = {}
    for f in facts:
        groups.setdefault(f.fact_key.aspect, []).append(get_fact_view(f))
    for aspect, rows in groups.items():
        (fdir / f"{aspect}.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
            encoding="utf-8")
    return {k: len(v) for k, v in groups.items()}


def _atomic_write(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def run(protocol: str, doc_name: str, client, root, *, on_canonical=None,
        on_hub=None) -> dict:
    """对外入口：负责隔离根校验与全局状态恢复。"""
    bad = _unsafe_reason(root)
    if bad:
        return {"status": "preflight_failed", "reason": f"unsafe_root:{bad}"}
    snap = {"cache_path": PS._cache_path, "max_tokens": PS._MAX_TOKENS,
            "no_retry": os.environ.get("PROSE_NO_RETRY"),
            "batch": os.environ.get("PROSE_BATCH_BLOCKS")}
    try:
        return _run_body(protocol, doc_name, client, root,
                         on_canonical=on_canonical, on_hub=on_hub)
    finally:
        PS._cache_path = snap["cache_path"]
        PS._MAX_TOKENS = snap["max_tokens"]
        for k, v in (("PROSE_NO_RETRY", snap["no_retry"]),
                     ("PROSE_BATCH_BLOCKS", snap["batch"])):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run_body(protocol: str, doc_name: str, client, root: pathlib.Path,
              *, on_canonical=None, on_hub=None) -> dict:
    """执行一次 T0-A；root 必须是隔离目录。"""
    root = pathlib.Path(root).resolve()

    doc = ROOT / "kb" / protocol / "spec" / doc_name
    text = doc.read_text(encoding="utf-8", errors="replace")
    src = hashlib.sha256(doc.read_bytes()).hexdigest()
    blocks = [{"doc": doc_name, "start": st, "text": bt, "src_sha256": src}
              for st, bt in PS._split_blocks(text, (len(text) // PS._MAX_BLOCK_CHARS) + 1)]

    _saved = {"cache_path": PS._cache_path, "max_tokens": PS._MAX_TOKENS,
              "no_retry": os.environ.get("PROSE_NO_RETRY"),
              "batch": os.environ.get("PROSE_BATCH_BLOCKS")}
    PS._cache_path = lambda p: root / "cache" / f"{p}.prose.json"  # type: ignore
    PS._MAX_TOKENS = MAX_TOKENS
    os.environ["PROSE_NO_RETRY"] = "1"
    os.environ["PROSE_BATCH_BLOCKS"] = "5"

    guard = Guard(root)
    gc = GuardedClient(client, guard)
    def _dump_guard():
        _atomic_write(root / "evidence" / "guard.json",
                      {"calls": guard.calls, "used_in": guard.used_in,
                       "spent_cny": round(guard.spent, 6),
                       "billing_status": guard.billing_status, "log": guard.log})

    result = {"status": "preflight_failed", "protocol": protocol, "doc": doc_name,
              "doc_sha256": src, "blocks": len(blocks), "calls": 0}
    try:
        norms, stats = PS._extract_blocks(protocol, blocks, llm=gc)
    except TimeoutError as exc:
        result.update(status="request_timeout", reason=str(exc),
                      calls=guard.calls, billing_status=guard.billing_status)
        _atomic_write(root / "evidence" / "result.json", result); _dump_guard(); return result
    except Exception as exc:                       # noqa: BLE001
        result.update(status="request_failed", reason=f"{type(exc).__name__}: {exc}",
                      calls=guard.calls, billing_status=guard.billing_status,
                      usage={"in": guard.used_in, "out": None})
        _atomic_write(root / "evidence" / "result.json", result); _dump_guard(); return result

    result.update(calls=gc.calls, norms=len(norms),
                  usage={"in": stats.get("input_tokens"), "out": stats.get("output_tokens")})

    # 任一批失败 ⇒ 整次实验失败，即使前一批已产出 Norm
    if guard.last_error:
        result["status"] = ("request_timeout" if guard.last_error == "TimeoutError"
                            else "request_failed")
        result["reason"] = guard.last_error
        result["partial_norms"] = len(norms)
        result["calls"] = guard.calls
        result["billing_status"] = guard.billing_status
        _atomic_write(root / "evidence" / "result.json", result)
        _dump_guard()
        return result

    if not norms:
        if guard.last_error:
            result["status"] = ("request_timeout" if guard.last_error == "TimeoutError"
                                else "request_failed")
            result["reason"] = guard.last_error
        else:
            result["status"] = "response_invalid" if guard.calls else "cache_incomplete"
        _atomic_write(root / "evidence" / "result.json", result); return result
    result["norm_validation_success"] = True

    facts = []
    try:
        if on_canonical:
            on_canonical()
        facts = [f for n in norms for f in NM.map_norm_to_facts(n)]
    except Exception as exc:                       # noqa: BLE001
        result.update(status="canonical_failed", reason=str(exc))
        _atomic_write(root / "evidence" / "result.json", result); return result
    if not facts:
        result["status"] = "canonical_failed"
        _atomic_write(root / "evidence" / "result.json", result); return result
    result["canonical_validation_success"] = True
    result["facts"] = len(facts)
    result["fact_ids"] = [f.fact_id for f in facts]

    # ★ 写盘之前先判完整性：任一批未完成/失败/被停/缓存不完整 ⇒ 不写 Fact、不建 Hub
    expect_batches = (len(blocks) + 4) // 5
    cache_file = root / "cache" / f"{protocol}.prose.d" / f"{doc_name}.json"
    cache_ok = False
    if cache_file.is_file():
        try:
            cache_ok = json.loads(cache_file.read_text(encoding="utf-8")).get("complete") is True
        except ValueError:
            cache_ok = False
    if (guard.calls < expect_batches or stats.get("failures")
            or guard.stopped or not cache_ok):
        result["status"] = "cache_incomplete"
        result["reason"] = {"calls": guard.calls, "expect": expect_batches,
                            "failures": stats.get("failures"),
                            "stopped": guard.stopped, "cache_complete": cache_ok}
        result["billing_status"] = "partial"
        _atomic_write(root / "evidence" / "result.json", result)
        _atomic_write(root / "evidence" / "guard.json",
                      {"calls": guard.calls, "used_in": guard.used_in,
                       "spent_cny": round(guard.spent, 6), "log": guard.log})
        return result

    try:
        if on_hub:
            on_hub()
        from core.fused.hub.export import get_fact_view
        payload = [get_fact_view(f) for f in facts]
        write_facts_by_aspect(facts, root / "per_source" / "facts")
        with isolated_hub(root):
            loaded = HE.load_facts(protocol)
            ents, _ = HE.build_entity_index(loaded)
            ep = HE.write_entity_index(protocol, ents)
            back = [json.loads(x) for x in ep.read_text(encoding="utf-8").splitlines() if x.strip()]
        if [x.get("fact_id") for x in loaded] != [x.get("fact_id") for x in payload]:
            raise RuntimeError("fact_id 读回不一致")
        result["hub_integration_success"] = True
        result["entities"] = len(back)
    except Exception as exc:                       # noqa: BLE001
        result.update(status="hub_failed", reason=str(exc))
        _atomic_write(root / "evidence" / "result.json", result); return result

    result["status"] = "completed"
    result["spent_cny"] = round(guard.spent, 6)
    result["billing_status"] = guard.billing_status if guard.billing_status != "none" else "billed"
    _atomic_write(root / "evidence" / "result.json", result)
    _atomic_write(root / "evidence" / "guard.json", {"log": guard.log,
                                                     "calls": guard.calls,
                                                     "used_in": guard.used_in})
    return result


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if not a.execute:
        print("dry-run：未联网。需要 --execute + DEEPSEEK_API_KEY + T0A_BUDGET_APPROVED=1")
        return 0
    if os.getenv("T0A_BUDGET_APPROVED") != "1" or not os.getenv("DEEPSEEK_API_KEY"):
        print("缺少预算授权或凭据，终止", file=sys.stderr); return 2
    root = pathlib.Path(a.out or os.environ.get("T0A_OUT", "/tmp/t0a_run"))
    r = run("smtp", "rfc3207.txt", AC.T0AClient(os.environ["DEEPSEEK_API_KEY"]), root)
    print(json.dumps({k: r[k] for k in ("status", "calls", "norms", "facts", "entities")
                      if k in r}, ensure_ascii=False))
    return 0 if r["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
