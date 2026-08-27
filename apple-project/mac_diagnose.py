#!/usr/bin/env python3
"""
 =============================================================================
  mac_diagnose.py  —  The Apple Project : Phase-0 ground-truth diagnostic

  Runs on the GitHub Actions `macos-15` runner. Needs NO secrets.
  Captures everything needed to decide HOW to grant Screen Recording to
  RustDesk on this exact image, then writes a JSON summary + screenshots to
  /tmp/apple-diagnose/ for upload as a workflow artifact.

  What it checks (in order):
    1. macOS version + architecture
    2. csrutil status  -> is SIP OFF? (the key hypothesis from runner-images#8162)
    3. TCC.db schema (PRAGMA table_info on `access`)
    4. ALL existing rows for ScreenCapture / Accessibility / InputMonitoring
       (so we can see what bash/screencapture/hosted-compute-agent look like —
        a known-good template to clone for RustDesk)
    5. Whether we can WRITE the system TCC.db (sqlite3 INSERT sanity: a dummy
       INSERT + ROLLBACK, no tccd restart)
    6. Install RustDesk (brew cask, no secret) -> get its bundle id + csreq
    7. ATTEMPT THE REAL GRANT: clone bash's ScreenCapture row, rewrite client
       to RustDesk, INSERT, killall tccd, read back. Did it persist?
    8. Launch RustDesk --server, check port 21118 listens.
    9. screencapture test (proves bash's own Screen Recording works).
   10. AX-read the System Settings Screen Recording pane: is RustDesk's toggle
       present + what value? (ground truth on whether tccd accepted the row)
   11. Write summary JSON + dump screenshots.

  Exit 0 always (we want the artifact even if some steps fail) — each step
  records its own pass/fail in the JSON.
 =============================================================================
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

OUT = Path("/tmp/apple-diagnose")
OUT.mkdir(parents=True, exist_ok=True)

TCC_DB = "/Library/Application Support/com.apple.TCC/TCC.db"
RUSTDESK_APP = "/Applications/RustDesk.app"
RUSTDESK_BIN = f"{RUSTDESK_APP}/Contents/MacOS/RustDesk"
RUSTDESK_BUNDLE = "com.carriez.RustDesk"

SERVICES = {
    "kTCCServiceScreenCapture": "Screen Recording",
    "kTCCServiceAccessibility": "Accessibility",
    "kTCCServiceListenEvent": "Input Monitoring",
}

summary: dict = {"steps": [], "tcc_rows": {}, "sip": None, "can_write_tcc": None,
                 "grant_persisted": None, "rustdesk_listening": None}


def log(msg: str) -> None:
    print(f"[diagnose] {msg}", flush=True)


def run(cmd, timeout=30, check=False):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if check and r.returncode != 0:
            raise RuntimeError(f"cmd failed: {' '.join(cmd)}\nstderr: {r.stderr}")
        return {"rc": r.returncode, "out": r.stdout.strip(),
                "err": r.stderr.strip(), "cmd": cmd}
    except Exception as e:
        return {"rc": 99, "out": "", "err": str(e), "cmd": cmd}


def sudo(cmd, timeout=30):
    return run(["sudo"] + cmd, timeout=timeout)


def record(name, result, extra=None):
    entry = {"step": name, "rc": result["rc"], "out": (result["out"] or "")[:4000],
             "err": (result["err"] or "")[:2000]}
    if extra:
        entry["extra"] = extra
    summary["steps"].append(entry)
    ok = result["rc"] == 0
    log(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" :: {result['err'][:120]}" if not ok and result['err'] else ""))
    return entry


# ----------------------------------------------------------------------------
def step_system():
    log("=== STEP 1: system info ===")
    sw = run(["sw_vers"])
    arch = run(["uname", "-m"])
    who = run(["whoami"])
    summary["system"] = {"sw_vers": sw["out"], "arch": arch["out"], "user": who["out"]}
    record("sw_vers", sw)
    record("arch", arch)
    record("whoami", who)


def step_sip():
    log("=== STEP 2: SIP status (THE key hypothesis) ===")
    r = run(["csrutil", "status"])
    record("csrutil_status", r)
    summary["sip"] = r["out"]
    # also the newer 'systemextensionsctl' / nvram boot-args just in case
    record("nvram_boot_args", run(["nvram", "boot-args"]))


def step_tcc_schema():
    log("=== STEP 3: TCC.db schema ===")
    r = sudo(["sqlite3", TCC_DB, "PRAGMA table_info(access);"])
    record("tcc_schema", r)
    # also list all tables
    record("tcc_tables", sudo(["sqlite3", TCC_DB, ".tables"]))


def step_tcc_dump_rows():
    log("=== STEP 4: dump existing TCC rows (known-good templates) ===")
    for svc, name in SERVICES.items():
        q = f"SELECT service, client, client_type, auth_value, auth_reason, "
        q += "auth_version, hex(csreq) AS csreq_hex, policy_id, "
        q += "indirect_object_identifier_type, indirect_object_identifier, flags, "
        q += "expired_at FROM access WHERE service='" + svc + "';"
        r = sudo(["sqlite3", "-json", TCC_DB, q])
        rows = []
        if r["rc"] == 0 and r["out"]:
            try:
                rows = json.loads(r["out"])
            except Exception:
                rows = [{"raw": r["out"]}]
        summary["tcc_rows"][svc] = rows
        record(f"dump_{svc}", r, extra={"row_count": len(rows),
                                        "clients": [x.get("client") for x in rows if isinstance(x, dict)]})


def step_write_sanity():
    log("=== STEP 5: TCC.db write sanity (INSERT + ROLLBACK) ===")
    q = "BEGIN; INSERT INTO access(service, client, client_type, auth_value) VALUES('kTCCServiceTest','diag',0,2); ROLLBACK;"
    r = sudo(["sqlite3", TCC_DB, q])
    record("write_sanity_rollback", r)
    summary["can_write_tcc"] = (r["rc"] == 0)


def step_install_rustdesk():
    log("=== STEP 6: install RustDesk (brew cask, no secret) ===")
    if not shutil.which("brew"):
        record("brew_check", {"rc": 1, "out": "", "err": "brew not found", "cmd": []})
        return None
    if Path(RUSTDESK_BIN).exists():
        log("  RustDesk already installed")
        record("rustdesk_present", {"rc": 0, "out": RUSTDESK_BIN, "err": "", "cmd": []})
    else:
        record("brew_cask_install", run(["brew", "install", "--cask", "rustdesk"], timeout=240))
    # strip quarantine
    run(["xattr", "-dr", "com.apple.quarantine", RUSTDESK_APP])
    ver = run([RUSTDESK_BIN, "--version"], timeout=10)
    record("rustdesk_version", ver)
    # bundle id + csreq
    cs = run(["codesign", "-d", "-r-", RUSTDESK_APP], timeout=10)
    record("codesign_designated_req", cs)
    summary["rustdesk_csreq_raw"] = cs["out"]
    # bundle id from defaults
    bid = run(["defaults", "read", f"{RUSTDESK_APP}/Contents/Info", "CFBundleIdentifier"], timeout=10)
    record("bundle_id", bid)
    return cs["out"]


def _get_columns():
    r = sudo(["sqlite3", TCC_DB, "PRAGMA table_info(access);"])
    cols = []
    for line in (r["out"] or "").splitlines():
        if "|" in line:
            parts = line.split("|")
            if len(parts) >= 2:
                cols.append(parts[1])
    return cols


def step_attempt_grant():
    log("=== STEP 7: ATTEMPT REAL GRANT (clone + INSERT + killall tccd + readback) ===")
    if not Path(RUSTDESK_BIN).exists():
        record("grant_skipped", {"rc": 1, "out": "", "err": "RustDesk not installed", "cmd": []})
        return
    cols = _get_columns()
    log(f"  access columns: {cols}")

    # find a known-good ScreenCapture row to clone (bash/screencapture/hosted-compute-agent)
    tmpl_q = ("SELECT client, hex(csreq) AS csreq_hex, auth_value, auth_reason, "
              "auth_version, policy_id, flags FROM access "
              "WHERE service='kTCCServiceScreenCapture' LIMIT 5;")
    tmpl = sudo(["sqlite3", "-json", TCC_DB, tmpl_q])
    record("grant_template_lookup", tmpl)
    templates = []
    if tmpl["rc"] == 0 and tmpl["out"]:
        try:
            templates = json.loads(tmpl["out"])
        except Exception:
            pass

    # compile RustDesk csreq to binary blob
    csreq_blob_hex = "NULL"
    csreq_text = ""
    for line in (summary.get("rustdesk_csreq_raw") or "").splitlines():
        if "designated" in line and "=>" in line:
            csreq_text = line.split("=>", 1)[-1].strip()
            break
    Path("/tmp/rd_req.txt").write_text(csreq_text)
    csreq_r = run(["csreq", "-r=/tmp/rd_req.txt", "-b=/tmp/rd_csreq.blob"], timeout=10)
    record("csreq_compile", csreq_r)
    if Path("/tmp/rd_csreq.blob").exists():
        csreq_blob_hex = "X'" + Path("/tmp/rd_csreq.blob").read_bytes().hex() + "'"

    # build INSERT per column
    def val_for(col):
        if col == "service":
            return "'kTCCServiceScreenCapture'"
        if col == "client":
            return f"'{RUSTDESK_BUNDLE}'"
        if col == "client_type":
            return "0"
        if col == "auth_value":
            return "2"
        if col == "auth_reason":
            return "4"
        if col == "auth_version":
            return "1"
        if col == "csreq":
            return csreq_blob_hex
        if col == "policy_id":
            return "0"
        if col == "indirect_object_identifier_type":
            return "0"
        if col == "indirect_object_identifier":
            return "'UNUSED'"
        if col == "flags":
            return "0"
        if col == "expired_at":
            return "NULL"
        if col == "last_accessed_error":
            return "NULL"
        return "NULL"

    col_list = ",".join(cols)
    val_list = ",".join(val_for(c) for c in cols)
    sql = f"INSERT OR REPLACE INTO access ({col_list}) VALUES ({val_list});"
    log(f"  INSERT sql (csreq_hex len={len(csreq_blob_hex)})")
    ins = sudo(["sqlite3", TCC_DB, sql])
    record("grant_insert", ins, extra={"sql_without_blob": sql.replace(csreq_blob_hex, "X'<blob>'")[:600]})

    # restart tccd
    kt = sudo(["killall", "tccd"])
    record("killall_tccd", kt)
    time.sleep(3)

    # read back
    rb = sudo(["sqlite3", "-json", TCC_DB,
               f"SELECT service, client, auth_value, hex(csreq) AS csreq_hex FROM access "
               f"WHERE service='kTCCServiceScreenCapture' AND client='{RUSTDESK_BUNDLE}';"])
    record("grant_readback", rb)
    persisted = False
    if rb["rc"] == 0 and rb["out"]:
        try:
            rows = json.loads(rb["out"])
            persisted = len(rows) > 0 and str(rows[0].get("auth_value")) == "2"
        except Exception:
            pass
    summary["grant_persisted"] = persisted
    log(f"  >>> GRANT PERSISTED AFTER tccd RESTART: {persisted}")

    # ALSO do Accessibility + InputMonitoring the same way (cheap, useful)
    for svc in ("kTCCServiceAccessibility", "kTCCServiceListenEvent"):
        sql2 = sql.replace("'kTCCServiceScreenCapture'", f"'{svc}'")
        r2 = sudo(["sqlite3", TCC_DB, sql2])
        record(f"grant_insert_{svc}", r2)
    sudo(["killall", "tccd"])
    time.sleep(2)


def step_launch_rustdesk():
    log("=== STEP 8: launch RustDesk --server + check port 21118 ===")
    # write a minimal config so it tries direct mode
    prefs = Path(f"/Users/runner/Library/Preferences/com.carriez.RustDesk")
    prefs.mkdir(parents=True, exist_ok=True)
    (prefs / "RustDesk.toml").write_text("id = '99999999'\npassword = 'diagtest'\n")
    (prefs / "RustDesk2.toml").write_text(
        "[options]\ncustom-rendezvous-server = ''\nrelay-server = ''\n"
        "api-server = ''\ndirect-server = 'Y'\ndirect-access-port = '21118'\n"
        "verification-method = 'use-fixed-password'\n")
    # launch
    run(["open", "-a", "RustDesk"])
    time.sleep(8)
    port = run(["bash", "-c", "lsof -nP -iTCP:21118 -sTCP:LISTEN | tail -n +1"])
    record("port_21118_listen", port)
    listening = "LISTEN" in (port["out"] or "")
    summary["rustdesk_listening"] = listening
    log(f"  >>> RustDesk listening on 21118: {listening}")
    pg = run(["pgrep", "-lf", "RustDesk"])
    record("pgrep_rustdesk", pg)


def step_screencapture_test():
    log("=== STEP 9: screencapture test (bash's own Screen Recording) ===")
    shot = OUT / "screenshot_desktop.png"
    r = run(["screencapture", "-x", "-C", str(shot)], timeout=15)
    record("screencapture", r, extra={"path": str(shot), "size": shot.stat().st_size if shot.exists() else 0})


def step_ax_read_pane():
    log("=== STEP 10: AX-read System Settings Screen Recording pane ===")
    # open the pane
    run(["open", "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture"])
    time.sleep(4)
    shot2 = OUT / "screenshot_screenrecording_pane.png"
    run(["screencapture", "-x", "-C", str(shot2)])
    # AX dump: list every AXSwitch + neighbouring text in System Settings window 1
    ax = run(["osascript", "-e", '''
tell application "System Events"
  set procList to (every process whose name is "System Settings")
  if (count of procList) is 0 then return "NO_PROCESS"
  set theProc to item 1 of procList
  if (count of windows of theProc) is 0 then return "NO_WINDOW"
  set out to ""
  my dumpAX(window 1 of theProc, "", 0, a reference to out)
  return out
end tell
on dumpAX(elem, prefix, depth, outRef)
  tell application "System Events"
    set r to ""
    try
      set r to role of elem
    end try
    set n to ""
    try
      set n to name of elem as text
    end try
    set v to ""
    try
      set v to value of elem as text
    end try
    if r is in {"AXSwitch","AXCheckBox","AXCheckbox"} then
      set contents of outRef to (contents of outRef) & "SWITCH name=" & n & " value=" & v & linefeed
    end if
    if r is "AXStaticText" and length of v > 0 then
      set contents of outRef to (contents of outRef) & "TEXT " & v & linefeed
    end if
    set kids to {}
    try
      set kids to UI elements of elem
    end try
    repeat with k in kids
      my dumpAX(k, prefix, depth + 1, outRef)
    end repeat
  end tell
end dumpAX'''], timeout=25)
    record("ax_pane_dump", ax, extra={"screenshot": str(shot2)})


def main():
    log("Apple Project — Phase-0 diagnostic starting")
    step_system()
    step_sip()
    step_tcc_schema()
    step_tcc_dump_rows()
    step_write_sanity()
    step_install_rustdesk()
    step_attempt_grant()
    step_launch_rustdesk()
    step_screencapture_test()
    step_ax_read_pane()

    summary["verdict"] = {
        "sip_off": "disabled" in (summary.get("sip") or "").lower() or
                   "unknown" in (summary.get("sip") or "").lower(),
        "can_write_tcc": summary.get("can_write_tcc"),
        "grant_persisted": summary.get("grant_persisted"),
        "rustdesk_listening": summary.get("rustdesk_listening"),
    }
    out_json = OUT / "diagnose_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))
    log(f"\n=== SUMMARY ===\n{json.dumps(summary['verdict'], indent=2)}")
    log(f"full summary -> {out_json}")
    # also print the full JSON to stdout so it lands in the Actions log
    print("\n" + "=" * 70, flush=True)
    print("DIAGNOSE_SUMMARY_JSON_BEGIN", flush=True)
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print("DIAGNOSE_SUMMARY_JSON_END", flush=True)
    print("=" * 70, flush=True)
    # never fail the workflow — we want the artifact
    return 0


if __name__ == "__main__":
    sys.exit(main())
