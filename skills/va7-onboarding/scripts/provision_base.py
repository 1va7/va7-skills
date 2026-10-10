#!/usr/bin/env python3
"""为一位新用户创建专属灵感库 Bitable（五表模板），并把表 ID 写回用户配置。

用法：
  python3 provision_base.py --name "某某灵感库" --config <user_config.json> [--yes]

依赖 lark-cli（bridge 模式下自动带应用身份）。创建动作用 --as bot。
link 字段在两张表都建好之后统一补建（因为互相引用）。
"""
import argparse
import json
import subprocess
import sys
import os
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "base_template.json")


def run_cli(args, check=True):
    cmd = ["lark-cli"] + list(args)
    if "--json" not in cmd:
        cmd += ["--json"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = p.stdout.strip()
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        print(f"RAW OUTPUT: {out[:500]}\nSTDERR: {p.stderr[:500]}", file=sys.stderr)
        raise
    if check and not d.get("ok"):
        raise RuntimeError(f"lark-cli failed: {json.dumps(d.get('error', {}), ensure_ascii=False)}\ncmd: {' '.join(cmd)}")
    return d


def create_base(name):
    d = run_cli(["base", "+base-create", "--as", "bot", "--name", name, "--table-name", "原始素材库",
                 "--fields", json.dumps([{"type": "text", "name": "素材标题"}], ensure_ascii=False)])
    base = d["data"].get("base") or {}
    base_token = base.get("base_token") or base.get("app_token")
    if not base_token:
        raise RuntimeError(f"no base_token in response: {json.dumps(d['data'], ensure_ascii=False)[:400]}")
    return base_token, base.get("url", "")


def create_table(base_token, table_def, is_first=False):
    fields = table_def["fields"]
    primary = fields[0]
    rest = fields[1:]
    args = ["base", "+table-create", "--as", "bot", "--base-token", base_token,
            "--name", table_def["name"], "--fields", json.dumps([primary], ensure_ascii=False)]
    d = run_cli(args)
    data = d["data"]
    table_id = None
    def find_tid(obj):
        if isinstance(obj, dict):
            for k in ("table_id", "id"):
                if isinstance(obj.get(k), str) and obj[k].startswith("tbl"):
                    return obj[k]
            for v in obj.values():
                r = find_tid(v)
                if r: return r
        elif isinstance(obj, list):
            for v in obj:
                r = find_tid(v)
                if r: return r
        return None
    table_id = find_tid(data) or (data.get("data") or {}).get("table_id")
    if not table_id:
        raise RuntimeError(f"cannot find table_id in: {json.dumps(data, ensure_ascii=False)[:400]}")
    if rest:
        run_cli(["base", "+field-create", "--as", "bot", "--base-token", base_token, "--table-id", table_id,
                 "--json", json.dumps(rest, ensure_ascii=False)])
    return table_id


def create_link_fields(base_token, tables_map, template):
    """表全部建完后补 link 字段。bidirectional 一侧即可，另一侧自动生成。"""
    for tdef in template["tables"]:
        for lf in tdef.get("link_fields", []):
            src_id = tables_map[tdef["key"]]
            dst_id = tables_map[lf["target_key"]]
            # bidirectional=true 时服务端会在对侧自动生成对应字段（默认以来源表名命名），
            # 所以模板约定：每条 link_fields 只描述自己这一侧，不做表对去重
            payload = {"type": "link", "name": lf["name"], "link_table": dst_id}
            if lf.get("bidirectional"):
                payload["bidirectional"] = True
            run_cli(["base", "+field-create", "--as", "bot", "--base-token", base_token,
                     "--table-id", src_id, "--json", json.dumps(payload, ensure_ascii=False)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="base 名称，例如 '某某灵感库'")
    ap.add_argument("--config", required=True, help="用户配置 json 路径")
    args = ap.parse_args()

    template = json.load(open(TEMPLATE, encoding="utf-8"))

    config = {}
    if os.path.exists(args.config):
        config = json.load(open(args.config, encoding="utf-8"))
    if (config.get("base") or {}).get("base_token"):
        print(f"config already has base_token {config['base']['base_token']}, skip provisioning")
        return

    base_token, base_url = create_base(args.name)
    print(f"base created: {base_token}")

    tables_map = {}
    first_key = template["tables"][0]["key"]
    tables_map[first_key] = None  # 第一张表由 create_base 建了骨架，但要补全字段
    # 第一张表（原始素材库）已随 base 创建，只有主字段；找它的 table_id 并补字段
    d = run_cli(["base", "+table-list", "--as", "bot", "--base-token", base_token])
    items = d["data"].get("tables") or d["data"].get("items") or []
    first_tid = None
    for it in items:
        if isinstance(it, dict) and it.get("name") == template["tables"][0]["name"]:
            first_tid = it.get("table_id") or it.get("id")
            break
    if not first_tid and items:
        first_tid = items[0].get("table_id") or items[0].get("id")
    if not first_tid:
        raise RuntimeError("first table id not found after base creation")
    tables_map[first_key] = first_tid
    rest_fields = template["tables"][0]["fields"][1:]
    if rest_fields:
        run_cli(["base", "+field-create", "--as", "bot", "--base-token", base_token,
                 "--table-id", first_tid, "--json", json.dumps(rest_fields, ensure_ascii=False)])

    for tdef in template["tables"][1:]:
        tables_map[tdef["key"]] = create_table(base_token, tdef)

    create_link_fields(base_token, tables_map, template)

    config["base"] = {
        "base_token": base_token,
        "tables": tables_map,
        "url": base_url or f"https://www.feishu.cn/base/{base_token}",
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.config)), exist_ok=True)
    with open(args.config, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(json.dumps(config["base"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
