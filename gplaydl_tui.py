#!/usr/bin/env python3

import os
import sys
import json
import subprocess
import shutil
import glob
import re
import time
import urllib.request
import urllib.error

HOME          = os.path.expanduser("~")
GPLAY_DIR     = os.path.join(HOME, "GPlayDL-TUI")
BIN_DIR       = os.path.join(GPLAY_DIR, "bin")
CONFIG_DIR    = os.path.join(GPLAY_DIR, ".config", "gplaydl-tui")
CONFIG_FILE   = os.path.join(CONFIG_DIR, "config.json")
APKEDITOR_JAR = os.path.join(BIN_DIR, "APKEditor.jar")
APKSIGNER_JAR = os.path.join(BIN_DIR, "apksigner.jar")
GPLAYDL_AUTH  = os.path.join(HOME, ".config", "gplaydl", "auth-arm64.json")

ARCH_OPTIONS = {
    "0": "",
    "1": "arm64",
    "2": "armv7",
}

DEFAULT_CONFIG = {
    "prefer_split"   : "on",
    "output_dir"     : "",
    "dispenser_link" : "",
    "skip_extras"    : "on",
    "arch"           : "",
    "keystore_path"  : "",
    "keystore_alias" : "",
    "keystore_pass"  : "",
    "key_pass"       : "",
    "keystore_type"  : "",
    "sign_apk"       : "off",
    "auto_install"   : "off",
}

KEYSTORE_EXTS = (".jks", ".p12", ".pfx")
EXT_TYPE_MAP  = {
    ".jks" : "JKS",
    ".p12" : "PKCS12",
    ".pfx" : "PKCS12",
}

class C:
    RST   = "\033[0m"
    BOLD  = "\033[1m"
    DIM   = "\033[2m"

    BRED  = "\033[91m"
    BGRN  = "\033[92m"
    BYLW  = "\033[93m"
    BBLU  = "\033[94m"
    BMAG  = "\033[95m"
    BCYN  = "\033[96m"
    BWHT  = "\033[97m"

    CYN   = "\033[36m"
    MAG   = "\033[35m"
    YLW   = "\033[33m"

    BGBLK = "\033[40m"
    BGRED = "\033[41m"
    BGGRN = "\033[42m"


def col(code, text):
    return f"{code}{text}{C.RST}"


def tw():
    return shutil.get_terminal_size((80, 24)).columns


def hline(char="─", clr=C.CYN):
    print(col(clr, char * tw()))


def dline(clr=C.BCYN):
    print(col(clr, "═" * tw()))


def tag_info(msg):
    print(col(C.BGRN, f"  ✔  {msg}"))


def tag_warn(msg):
    print(col(C.BYLW, f"  ⚠  {msg}"))


def tag_err(msg):
    print(col(C.BRED, f"  ✖  {msg}"))


def tag_step(msg):
    print(col(C.BBLU, f"  ◆  {msg}"))


def ask(question, default=None, secret=False):
    hint = f" [{col(C.DIM + C.CYN, default)}]" if default else ""
    prompt = col(C.BMAG, f"\n  ➤  {question}{hint}: ")
    try:
        if secret:
            import getpass
            ans = getpass.getpass(prompt)
        else:
            ans = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default or ""
    return ans if ans else (default or "")


def pause(msg="Press Enter to continue…"):
    try:
        input(col(C.DIM + C.CYN, f"\n  ⏎  {msg}"))
    except (EOFError, KeyboardInterrupt):
        print()


def clear():
    os.system("clear" if os.name != "nt" else "cls")


def progress_bar(downloaded, total, bar_len=28):
    if total <= 0:
        return
    frac = min(downloaded / total, 1.0)
    done = int(frac * bar_len)
    rest = bar_len - done
    bar  = col(C.BGRN, "█" * done) + col(C.DIM, "░" * rest)
    pct  = col(C.BWHT + C.BOLD, f"{frac*100:5.1f}%")
    dl   = col(C.BCYN, f"{downloaded//1024:>6} KB")
    tot  = col(C.DIM + C.CYN, f"/ {total//1024} KB")
    sys.stdout.write(f"\r  [{bar}] {pct}  {dl} {tot}  ")
    sys.stdout.flush()


LOGO = [
    "   ____  ____  _                ____  _     ",
    "  / ___||  _ \\| | __ _ _   _  |  _ \\| |    ",
    " | |  _ | |_) | |/ _` | | | | | | | | |    ",
    " | |_| ||  __/| | (_| | |_| | | |_| | |___ ",
    "  \\____||_|   |_|\\__,_|\\__, | |____/|_____|",
    "                         |___/               ",
]


def banner():
    clear()
    w = tw()
    dline(C.BCYN)
    for ln in LOGO:
        print(col(C.BCYN + C.BOLD, ln.center(w)))
    dline(C.BCYN)
    print(col(C.BMAG,
              "  Google Play Downloader · Merge · Sign · Device Profile".center(w)))
    print(col(C.DIM + C.MAG, "  Created by GrayWizard".center(w)))
    dline(C.BCYN)
    print()


def section_header(title, icon="◈"):
    print()
    hline("─", C.CYN)
    print(col(C.BOLD + C.BCYN, f"  {icon}  {title}"))
    hline("─", C.CYN)
    print()


def menu_row(num, icon, label, clr=C.BBLU):
    n  = col(C.BGBLK + C.BYLW + C.BOLD, f" {num} ")
    ic = col(clr, icon)
    lb = col(C.BWHT, f"  {label}")
    print(f"  {n}  {ic}{lb}")


def badge_on_off(v):
    if v == "on":
        return col(C.BGGRN + C.BOLD, " ON  ")
    return col(C.BGRED + C.BWHT + C.BOLD, " OFF ")


def status_bar(cfg):
    sp  = (col(C.BGRN, "● SPLIT")
           if cfg["prefer_split"] == "on"
           else col(C.BRED, "○ SINGLE"))
    sk  = (col(C.BGRN, "● SKIP-EXTRAS")
           if cfg["skip_extras"] == "on"
           else col(C.BRED, "○ EXTRAS"))
    ar  = col(C.BCYN, cfg["arch"] or "arm64 (default)")
    od  = col(C.BCYN, cfg["output_dir"] or "~/gplay")
    sig = (col(C.BGRN, "● SIGN")
           if cfg.get("sign_apk") == "on"
           else col(C.BRED, "○ SIGN"))
    ins = (col(C.BGRN, "● INSTALL")
           if cfg.get("auto_install") == "on"
           else col(C.BRED, "○ INSTALL"))
    hline("─", C.DIM + C.CYN)
    print(f"  {sp}   {sk}   {sig}   {ins}   Arch: {ar}   Out: {od}")
    hline("─", C.DIM + C.CYN)


def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as fh:
                saved = json.load(fh)
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(saved)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as fh:
        json.dump(cfg, fh, indent=2)
    tag_info(f"Config saved → {CONFIG_FILE}")


def run_silent(cmd, **kw):
    return subprocess.call(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kw,
    )


def run_cmd(cmd, **kw):
    return subprocess.call(cmd, **kw)


def pip_install_gplaydl():
    section_header("Installing gplaydl", "📦")
    code = run_silent(
        [sys.executable, "-m", "pip", "install", "--upgrade", "gplaydl"]
    )
    if code == 0:
        tag_info("gplaydl installed/updated successfully.")
        return True
    tag_err("pip install failed – check your internet connection.")
    return False


def download_with_progress(url, dest, retries=3, delay=1):
    headers = {"User-Agent": "gplaydl-tui/2.0"}
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                done  = 0
                with open(dest, "wb") as fh:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        progress_bar(done, total)
            print()
            return True
        except Exception as exc:
            print()
            tag_warn(f"Attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(delay)
    return False


def fetch_apkeditor():
    section_header("Downloading APKEditor", "☕")
    os.makedirs(BIN_DIR, exist_ok=True)

    api_url = "https://api.github.com/repos/REAndroid/APKEditor/releases/latest"
    req     = urllib.request.Request(
        api_url,
        headers={
            "Accept"              : "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent"          : "gplaydl-tui/2.0",
        },
    )

    jar_url  = None
    jar_name = None

    print(col(C.BCYN, "  Querying GitHub API…"))
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.lower().endswith(".jar"):
                    jar_url  = asset["browser_download_url"]
                    jar_name = name
                    break
            if jar_url:
                break
            tag_err("No .jar asset found in latest release.")
            return False
        except urllib.error.URLError as exc:
            tag_warn(f"API attempt {attempt}/3: {exc}")
            if attempt < 3:
                time.sleep(1)
            else:
                tag_err("Could not reach GitHub API after 3 attempts.")
                return False

    tag_info(f"Found: {col(C.BYLW, jar_name)}")
    tag_step(f"Saving to {APKEDITOR_JAR}")
    ok = download_with_progress(jar_url, APKEDITOR_JAR)
    if ok:
        tag_info("APKEditor.jar downloaded successfully.")
    else:
        tag_err("Download failed after 3 attempts.")
    return ok


def java_binary():
    return shutil.which("java")


def check_java_version():
    java = java_binary()
    if not java:
        return False, ""
    try:
        result = subprocess.run(
            [java, "-version"],
            capture_output=True, text=True, timeout=10
        )
        ver_text = result.stderr or result.stdout
        m   = re.search(r'version "([^"]+)"', ver_text)
        ver = m.group(1) if m else ver_text.split("\n")[0].strip()
        return True, ver
    except Exception:
        return False, ""


def ensure_jdk():
    found, ver = check_java_version()
    if found:
        tag_info(f"Java found → {col(C.BCYN, ver)}")
        return True

    tag_warn("Java (JDK) not found.")
    print()
    print(col(C.BWHT, "  Java is required for APKEditor and apksigner."))
    print(col(C.BWHT, "  This will run:  pkg install openjdk-21"))
    print()
    go = ask("Install openjdk-21 now? [Y/n]", default="y").lower()
    if go == "n":
        tag_warn("Skipping JDK install – merge/sign features will not work.")
        return False

    section_header("Installing openjdk-21", "☕")
    code = run_silent(["pkg", "install", "-y", "openjdk-21"])
    if code == 0:
        found2, ver2 = check_java_version()
        if found2:
            tag_info(f"Java installed successfully → {col(C.BCYN, ver2)}")
            return True
        tag_err("pkg install succeeded but java still not found in PATH.")
        tag_warn("Try: export PATH=$PATH:$PREFIX/bin  or restart Termux.")
        return False
    tag_err("pkg install openjdk-21 failed.")
    tag_warn("Try manually:  pkg install openjdk-21")
    return False


def ensure_jq():
    if shutil.which("jq"):
        tag_info(f"jq found → {col(C.BCYN, shutil.which('jq'))}")
        return True

    tag_warn("jq not found.")
    print()
    print(col(C.BWHT, "  jq is required for device profile replacement."))
    print(col(C.BWHT, "  This will run:  pkg install -y jq"))
    print()
    go = ask("Install jq now? [Y/n]", default="y").lower()
    if go == "n":
        tag_warn("Skipping jq install – device profile feature will not work.")
        return False

    section_header("Installing jq", "🔧")
    code = run_silent(["pkg", "install", "-y", "jq"])
    if code == 0 and shutil.which("jq"):
        tag_info("jq installed successfully.")
        return True
    tag_err("pkg install jq failed.")
    tag_warn("Try manually:  pkg install jq")
    return False


def ensure_dependencies():
    banner()
    section_header("Dependency Check", "🔍")
    changed = False

    java_ok = ensure_jdk()
    if not java_ok:
        tag_warn("Continuing without Java – merge/sign will be unavailable.")

    ensure_jq()

    if shutil.which("gplaydl") is None:
        tag_warn("gplaydl not found.")
        if not pip_install_gplaydl():
            pause()
            sys.exit(1)
        changed = True
    else:
        tag_info(f"gplaydl  →  {col(C.BCYN, shutil.which('gplaydl'))}")

    if not os.path.exists(APKEDITOR_JAR):
        tag_warn("APKEditor.jar not found.")
        if java_ok:
            if not fetch_apkeditor():
                pause()
                sys.exit(1)
            changed = True
        else:
            tag_warn("Skipping APKEditor download (Java unavailable).")
    else:
        tag_info(f"APKEditor →  {col(C.BCYN, APKEDITOR_JAR)}")

    if os.path.exists(APKSIGNER_JAR):
        tag_info(f"apksigner →  {col(C.BCYN, APKSIGNER_JAR)}")
    else:
        tag_warn(f"apksigner.jar not found at {APKSIGNER_JAR}")
        tag_warn("Place apksigner.jar in the bin folder to enable signing.")

    if not changed:
        tag_info("All dependencies satisfied.")
    pause()


def build_common_args(cfg):
    args = []
    if cfg.get("dispenser_link", "").strip():
        args += ["--dispenser", cfg["dispenser_link"].strip()]
    return args


def build_download_args(cfg):
    args = []
    if cfg.get("prefer_split") != "on":
        args.append("--no-splits")
    if cfg.get("skip_extras") != "off":
        args.append("--no-extras")
    arch = cfg.get("arch", "").strip()
    if arch:
        args += ["--arch", arch]
    return args


_ANSI_RE   = re.compile(r'\x1b\[[0-9;]*[mKGHJA-Z]|\x1b[()][AB012]')
_PKG_RE    = re.compile(
    r'^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$'
)
_BORDER_RE = re.compile(
    r'^[\s━─│┃┏┓┗┛┣┫┳┻╋┡┩╇╈┼┬┴├┤└┘┌┐╔╗╚╝╠╣╦╩╬═╞╡╟╢╤╧╪╫\-=+|]+$'
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _is_border(line: str) -> bool:
    return bool(_BORDER_RE.match(_strip_ansi(line).strip()))


def _split_cells(line: str) -> list:
    cells = re.split(r'[│┃]', _strip_ansi(line))
    return [c.strip() for c in cells if c.strip()]


def parse_pkg_map(output: str) -> dict:
    mapping = {}
    for line in output.splitlines():
        if _is_border(line):
            continue
        cells = _split_cells(line)
        if len(cells) < 3:
            continue
        num_cell = cells[0]
        pkg_cell = cells[2]
        if not num_cell.isdigit():
            continue
        if not _PKG_RE.match(pkg_cell):
            continue
        mapping[int(num_cell)] = pkg_cell
    return mapping


def run_search_capture(cmd: list) -> tuple:
    try:
        import pty
        import select
        import termios
        import fcntl
        import struct

        cols, rows      = shutil.get_terminal_size((80, 24))
        master_fd, slave_fd = pty.openpty()
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)

        raw_bytes = b""
        while True:
            try:
                rlist, _, _ = select.select([master_fd], [], [], 0.1)
            except (ValueError, OSError):
                break
            if rlist:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                raw_bytes += chunk
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            else:
                if proc.poll() is not None:
                    try:
                        while True:
                            rlist2, _, _ = select.select(
                                [master_fd], [], [], 0.05
                            )
                            if not rlist2:
                                break
                            chunk = os.read(master_fd, 4096)
                            if not chunk:
                                break
                            raw_bytes += chunk
                            sys.stdout.buffer.write(chunk)
                            sys.stdout.buffer.flush()
                    except OSError:
                        pass
                    break

        proc.wait()
        try:
            os.close(master_fd)
        except OSError:
            pass

        text = raw_bytes.decode("utf-8", errors="replace")
        return proc.returncode, text

    except ImportError:
        pass

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        raw_bytes = b""
        while True:
            chunk = proc.stdout.read(256)
            if not chunk:
                break
            raw_bytes += chunk
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        proc.wait()
        text = raw_bytes.decode("utf-8", errors="replace")
        return proc.returncode, text

    except FileNotFoundError:
        tag_err("gplaydl not found – restart script to reinstall.")
        return 1, ""
    except Exception as exc:
        tag_err(f"Failed to run search: {exc}")
        return 1, ""


def merge_apks(apk_dir: str, pkg: str) -> str | None:
    if not os.path.exists(APKEDITOR_JAR):
        tag_err("APKEditor.jar missing – cannot merge.")
        return None
    if not java_binary():
        tag_err("java not found – install with:  pkg install openjdk-21")
        return None

    merged_path = os.path.join(GPLAY_DIR, f"{pkg}_merged.apk")
    tag_step("Merging split APKs with APKEditor…")

    code = run_cmd([
        "java", "-jar", APKEDITOR_JAR,
        "merge",
        "-i", apk_dir,
        "-o", merged_path,
        "-f",
    ])

    if code == 0 and os.path.exists(merged_path):
        sz = os.path.getsize(merged_path) // 1024
        tag_info(f"Merged APK → {merged_path}  ({sz} KB)")
        return merged_path

    tag_err("APKEditor merge failed.")
    return None


def sign_apk(apk_path: str, cfg: dict) -> str | None:
    if not os.path.exists(APKSIGNER_JAR):
        tag_err(f"apksigner.jar not found at {APKSIGNER_JAR}")
        tag_warn("Place apksigner.jar in the bin folder to enable signing.")
        return None

    if not java_binary():
        tag_err("java not found – cannot sign APK.")
        return None

    ks_path  = cfg.get("keystore_path", "").strip()
    ks_alias = cfg.get("keystore_alias", "").strip()
    ks_pass  = cfg.get("keystore_pass", "").strip()
    key_pass = cfg.get("key_pass", "").strip()
    ks_type  = cfg.get("keystore_type", "").strip()

    if not ks_path or not os.path.exists(ks_path):
        tag_err(f"Keystore not found: {ks_path}")
        return None
    if not ks_alias:
        tag_err("Keystore alias not configured.")
        return None
    if not ks_pass:
        tag_err("Keystore password not configured.")
        return None
    if not ks_type:
        ext     = os.path.splitext(ks_path)[1].lower()
        ks_type = EXT_TYPE_MAP.get(ext, "JKS")

    effective_key_pass = key_pass if key_pass else ks_pass

    base, _     = os.path.splitext(apk_path)
    signed_path = f"{base}_signed.apk"

    section_header("Signing APK", "✍")
    tag_step(f"Input  : {apk_path}")
    tag_step(f"Output : {signed_path}")
    print()

    cmd = [
        "java",
        "--enable-native-access=ALL-UNNAMED",
        "-jar", APKSIGNER_JAR,
        "sign",
        "--ks",                 ks_path,
        "--ks-pass",            f"pass:{ks_pass}",
        "--key-pass",           f"pass:{effective_key_pass}",
        "--ks-type",            ks_type,
        "--ks-key-alias",       ks_alias,
        "--v1-signing-enabled", "true",
        "--v2-signing-enabled", "true",
        "--v3-signing-enabled", "true",
        "--v4-signing-enabled", "false",
        "--out",                signed_path,
        apk_path,
    ]

    code = run_silent(cmd)
    print()

    if code == 0 and os.path.exists(signed_path):
        sz = os.path.getsize(signed_path) // 1024
        tag_info(f"Signed APK → {signed_path}  ({sz} KB)")
        return signed_path

    tag_err(f"apksigner failed (exit code {code}).")
    return None


def auto_install_apk(apk_path: str) -> None:
    if not os.path.exists(apk_path):
        tag_err(f"APK not found for install: {apk_path}")
        return

    if not shutil.which("termux-open"):
        tag_warn("termux-open not found – skipping auto-install.")
        tag_warn("Install termux-tools:  pkg install termux-tools")
        return

    section_header("Auto Install", "📲")
    tag_step("Opening APK installer…")
    code = run_cmd(["termux-open", "--view", apk_path])
    if code == 0:
        tag_info("Install prompt opened on device.")
    else:
        tag_warn(f"termux-open exited with code {code}.")


def configure_keystore(cfg: dict) -> dict:
    section_header("Keystore Configuration", "🔑")

    print(col(C.BWHT, "  Supported keystore formats:"))
    for ext, ktype in EXT_TYPE_MAP.items():
        print(col(C.DIM + C.BCYN, f"    {ext}  →  {ktype}"))
    print()

    current = cfg.get("keystore_path", "")
    raw = ask(
        "Keystore path  (or Enter to keep current)",
        default=current
    ).strip()
    raw = os.path.expanduser(raw)

    if raw:
        ext = os.path.splitext(raw)[1].lower()
        if ext not in KEYSTORE_EXTS:
            tag_err(
                f"Unsupported extension '{ext}'.  "
                f"Use one of: {', '.join(KEYSTORE_EXTS)}"
            )
            pause()
            return cfg

        if not os.path.exists(raw):
            tag_err(f"File not found: {raw}")
            pause()
            return cfg

        cfg["keystore_path"] = raw
        cfg["keystore_type"] = EXT_TYPE_MAP[ext]
        tag_info(f"Keystore : {raw}")
        tag_info(f"Type     : {cfg['keystore_type']}")

        alias = ask(
            "Key alias",
            default=cfg.get("keystore_alias", "")
        ).strip()
        if alias:
            cfg["keystore_alias"] = alias

        ks_pass = ask(
            "Keystore password",
            default="",
            secret=True
        ).strip()
        if ks_pass:
            cfg["keystore_pass"] = ks_pass
        elif not cfg.get("keystore_pass"):
            tag_warn("No keystore password entered – field left empty.")

        print(col(C.DIM + C.CYN,
                  "\n  Leave blank to use the same password as the keystore."))
        key_pass = ask(
            "Key password (Enter = same as keystore)",
            default="",
            secret=True
        ).strip()
        cfg["key_pass"] = key_pass

        tag_info("Keystore configuration saved.")
    else:
        tag_warn("No path entered – keystore config unchanged.")

    return cfg


def _validate_device_json(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
    except Exception as exc:
        tag_err(f"Cannot read file: {exc}")
        return None

    data = None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        pass

    if data is None:
        try:
            data = json.loads("{" + raw + "}")
        except json.JSONDecodeError:
            pass

    if data is None:
        try:
            cleaned = raw.rstrip().rstrip(",")
            data = json.loads("{" + cleaned + "}")
        except json.JSONDecodeError as exc:
            tag_err(f"Invalid JSON: {exc}")
            tag_warn(
                "Make sure the file contains valid JSON.\n"
                "  Accepted formats:\n"
                '    • { "deviceInfoProvider": { … } }\n'
                '    • { "authUserAgentString": …, "properties": { … } }\n'
                '    • "deviceInfoProvider": { … }   (partial snippet)'
            )
            return None

    if not isinstance(data, dict):
        tag_err("JSON root must be an object / dictionary.")
        return None

    if "deviceInfoProvider" in data:
        provider = data["deviceInfoProvider"]
    else:
        expected_keys = {
            "authUserAgentString", "userAgentString",
            "sdkVersion", "properties", "mccMnc",
        }
        if expected_keys & set(data.keys()):
            provider = data
        else:
            tag_err(
                "JSON does not contain a recognisable "
                "deviceInfoProvider block."
            )
            tag_warn(
                "Expected either a 'deviceInfoProvider' key or bare "
                "fields like authUserAgentString / properties."
            )
            return None

    if not isinstance(provider, dict) or not provider:
        tag_err("deviceInfoProvider block is empty or not an object.")
        return None

    return provider


def do_replace_device_profile():
    banner()
    section_header("Modify Device Profile", "📱")

    if not shutil.which("jq"):
        tag_err("jq is not installed.")
        tag_warn("Install it with:  pkg install jq")
        pause()
        return

    if not os.path.exists(GPLAYDL_AUTH):
        tag_err(f"Auth file not found: {GPLAYDL_AUTH}")
        tag_warn(
            "Run gplaydl auth at least once to create the auth file."
        )
        pause()
        return

    print(col(C.BWHT, "  Current auth file:"))
    print(col(C.DIM + C.BCYN, f"    {GPLAYDL_AUTH}"))
    print()

    try:
        with open(GPLAYDL_AUTH, "r", encoding="utf-8") as fh:
            current_auth = json.load(fh)
        cur_provider = current_auth.get("deviceInfoProvider", {})
        cur_model    = cur_provider.get("properties", {}).get(
            "Build.MODEL", "unknown"
        )
        cur_sdk = cur_provider.get("sdkVersion", "?")
        tag_info(
            f"Current device : {col(C.BCYN, cur_model)}  "
            f"(SDK {cur_sdk})"
        )
    except Exception:
        tag_warn("Could not read current auth file.")

    print()
    hline("─", C.CYN)
    print(col(C.BWHT,
              "  Provide a JSON file that contains a deviceInfoProvider block."))
    print(col(C.DIM + C.CYN, "  Accepted layouts:"))
    print(col(C.DIM + C.CYN, '    • { "deviceInfoProvider": { … } }'))
    print(col(C.DIM + C.CYN, '    • { "authUserAgentString": …, "properties": { … }, … }'))
    print(col(C.DIM + C.CYN, '    • "deviceInfoProvider": { … }   (partial snippet)'))
    hline("─", C.CYN)
    print()

    raw_path = ask("Path to device JSON file").strip()
    if not raw_path:
        tag_warn("No path entered – returning to main menu.")
        return

    json_path = os.path.expanduser(raw_path)

    if not os.path.exists(json_path):
        tag_err(f"File not found: {json_path}")
        pause()
        return

    provider = _validate_device_json(json_path)
    if provider is None:
        pause()
        return

    new_model = provider.get("properties", {}).get("Build.MODEL", "unknown")
    new_sdk   = provider.get("sdkVersion", "?")
    new_abi   = provider.get("properties", {}).get("Platforms", "unknown")

    print()
    hline("─", C.CYN)
    print(col(C.BOLD + C.BWHT, "  New device profile:"))
    print(col(C.BCYN, f"    Model    : {new_model}"))
    print(col(C.BCYN, f"    SDK      : {new_sdk}"))
    print(col(C.BCYN, f"    ABI      : {new_abi}"))
    hline("─", C.CYN)
    print()

    go = ask("Apply this device profile? [Y/n]", default="y").lower()
    if go == "n":
        tag_info("Cancelled – profile unchanged.")
        pause()
        return

    backup_path = GPLAYDL_AUTH + ".bak"
    try:
        shutil.copy2(GPLAYDL_AUTH, backup_path)
        tag_info(f"Backup saved → {backup_path}")
    except Exception as exc:
        tag_warn(f"Could not create backup: {exc}")

    tmp_provider = os.path.join(CONFIG_DIR, "tmp_provider.json")
    try:
        with open(tmp_provider, "w", encoding="utf-8") as fh:
            json.dump(provider, fh, indent=2)
    except Exception as exc:
        tag_err(f"Failed to write temp provider file: {exc}")
        pause()
        return

    tmp_out  = GPLAYDL_AUTH + ".tmp"
    jq_cmd   = [
        "jq",
        "--slurpfile", "new", tmp_provider,
        ".deviceInfoProvider = $new[0]",
        GPLAYDL_AUTH,
    ]

    try:
        with open(tmp_out, "w", encoding="utf-8") as out_fh:
            result = subprocess.run(
                jq_cmd,
                stdout=out_fh,
                stderr=subprocess.PIPE,
                text=True,
            )

        if result.returncode != 0:
            tag_err("jq failed to process the auth file.")
            err_text = result.stderr.strip()
            if err_text:
                tag_err(err_text)
            try:
                shutil.copy2(backup_path, GPLAYDL_AUTH)
                tag_warn("Original auth file restored from backup.")
            except Exception:
                pass
            pause()
            return

        with open(tmp_out, "r", encoding="utf-8") as fh:
            merged = json.load(fh)

        written_model = (
            merged.get("deviceInfoProvider", {})
                  .get("properties", {})
                  .get("Build.MODEL", "")
        )
        if not written_model:
            tag_err("Merged JSON does not contain deviceInfoProvider.")
            pause()
            return

        shutil.move(tmp_out, GPLAYDL_AUTH)

    except Exception as exc:
        tag_err(f"Unexpected error during merge: {exc}")
        pause()
        return
    finally:
        for f in (tmp_provider, tmp_out):
            try:
                os.remove(f)
            except OSError:
                pass

    print()
    dline(C.BGRN)
    print(col(C.BGRN + C.BOLD,
              "  ✔  Device profile replaced!".center(tw())))
    print(col(C.BCYN, f"  Model  : {new_model}"))
    print(col(C.BCYN, f"  SDK    : {new_sdk}"))
    print(col(C.BCYN, f"  ABI    : {new_abi}"))
    print(col(C.BCYN, f"  File   : {GPLAYDL_AUTH}"))
    print(col(C.DIM + C.BCYN, f"  Backup : {backup_path}"))
    dline(C.BGRN)
    pause()


def do_force_reauth(cfg):
    banner()
    section_header("Force Re-Authentication", "🔄")
    tag_warn("Clearing stored credentials…")
    run_silent(["gplaydl"] + build_common_args(cfg) + ["auth", "--clear"])
    print()
    tag_info("Credentials cleared.  Starting fresh login…")
    hline()
    run_cmd(["gplaydl"] + build_common_args(cfg) + ["auth"])
    pause()


def do_search_download(cfg):
    banner()
    section_header("Search & Download", "🔍")

    query = ask("Enter app name to search").strip()
    if not query:
        tag_warn("Empty query – returning to main menu.")
        pause()
        return

    search_cmd = ["gplaydl"] + build_common_args(cfg) + ["search", query]
    print()
    exit_code, captured = run_search_capture(search_cmd)
    print()

    if exit_code != 0:
        tag_err("Search failed (gplaydl returned non-zero).")
        tag_warn("Check your authentication / internet connection.")
        pause()
        return

    pkg_map = parse_pkg_map(captured)

    if not pkg_map:
        tag_warn("Could not parse any results from search output.")
        tag_warn("Enter the package name manually if you know it.")
        pkg = ask("Package name (or Enter to go back)").strip()
        if not pkg:
            return
        pkg_map = {1: pkg}

    max_num = max(pkg_map.keys())

    hline("─", C.CYN)
    choice = ask(
        f"Enter number [1-{max_num}]  or  press Enter to go back"
    ).strip()

    if not choice:
        tag_info("Returning to main menu.")
        time.sleep(0.4)
        return

    if not choice.isdigit() or int(choice) not in pkg_map:
        tag_warn(f"Invalid selection.  Valid range: 1-{max_num}")
        pause()
        return

    pkg = pkg_map[int(choice)]

    section_header(f"App Info  ·  {pkg}", "ℹ")
    hline("─", C.DIM + C.CYN)
    run_cmd(["gplaydl"] + build_common_args(cfg) + ["info", pkg])
    hline("─", C.DIM + C.CYN)

    print()
    hline("─", C.CYN)
    print(col(C.BOLD + C.BCYN, f"  Package : {pkg}"))
    mode = (
        col(C.BGRN, "SPLIT APKs  (will merge with APKEditor)")
        if cfg["prefer_split"] == "on"
        else col(C.BBLU, "SINGLE APK  (--no-splits)")
    )
    print(col(C.BOLD + C.BMAG, f"  Mode    : {mode}"))
    sk_str = "yes (--skip-extras)" if cfg["skip_extras"] != "off" else "no"
    print(col(C.BOLD + C.BYLW, f"  Extras  : skip = {sk_str}"))
    arch_str = cfg.get("arch") or "arm64 (gplaydl default)"
    print(col(C.BOLD + C.BCYN, f"  Arch    : {arch_str}"))

    will_sign = (
        cfg.get("sign_apk") == "on"
        and os.path.exists(APKSIGNER_JAR)
        and os.path.exists(cfg.get("keystore_path", ""))
    )
    sign_str = (
        col(C.BGRN, f"YES  (alias: {cfg.get('keystore_alias', '?')})")
        if will_sign
        else col(C.DIM, "NO  (disabled or keystore not configured)")
    )
    print(col(C.BOLD + C.BYLW, f"  Sign    : {sign_str}"))

    will_install = cfg.get("auto_install") == "on"
    install_str  = (
        col(C.BGRN, "YES  (termux-open --view)")
        if will_install
        else col(C.DIM, "NO")
    )
    print(col(C.BOLD + C.BYLW, f"  Install : {install_str}"))
    hline("─", C.CYN)
    print()

    go = ask("Start download?  [Y/n]", default="y").lower()
    if go == "n":
        tag_info("Download cancelled.")
        pause()
        return

    tmp_dir = os.path.join(GPLAY_DIR, pkg)
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)

    dl_after = build_download_args(cfg)
    dl_cmd   = (
        ["gplaydl"]
        + build_common_args(cfg)
        + ["download", "--output", tmp_dir, pkg]
        + dl_after
    )

    section_header(f"Downloading  ·  {pkg}", "⬇")
    hline("─", C.DIM + C.CYN)
    print()

    dl_code = run_cmd(dl_cmd)

    print()
    hline("─", C.DIM + C.CYN)

    if dl_code != 0:
        tag_err(f"gplaydl exited with code {dl_code}.")
        tag_warn(f"Temp files kept at: {tmp_dir}")
        pause()
        return

    all_apks = sorted(
        glob.glob(os.path.join(tmp_dir, "**", "*.apk"), recursive=True)
    )
    apk_files = [
        f for f in all_apks
        if not re.match(
            r'^(main|patch)\.\d+\.',
            os.path.basename(f).lower()
        )
    ]

    if not apk_files:
        tag_err("No APK files found after download.")
        pause()
        return

    print()
    tag_info(f"Found {len(apk_files)} APK file(s):")
    for f in apk_files:
        sz = os.path.getsize(f) // 1024
        print(col(C.DIM + C.BCYN,
                  f"    • {os.path.basename(f)}"
                  f"  {col(C.DIM + C.YLW, f'({sz} KB)')}"))

    final_apk = None

    if len(apk_files) >= 2:
        tag_info("2 or more APKs detected – merging with APKEditor…")
        merged = merge_apks(tmp_dir, pkg)
        if merged:
            final_apk = merged
        else:
            tag_warn("Merge failed – falling back to base/first APK.")

    if final_apk is None:
        base   = [f for f in apk_files
                  if os.path.basename(f).lower().startswith("base")]
        chosen = base[0] if base else apk_files[0]
        dest   = os.path.join(GPLAY_DIR, os.path.basename(chosen))
        if os.path.abspath(chosen) != os.path.abspath(dest):
            shutil.copy2(chosen, dest)
        final_apk = dest

    signed_ok = False
    if will_sign:
        signed = sign_apk(final_apk, cfg)
        if signed:
            if os.path.abspath(signed) != os.path.abspath(final_apk):
                try:
                    os.remove(final_apk)
                except OSError:
                    pass
            final_apk = signed
            signed_ok = True
        else:
            tag_warn("Signing failed – keeping unsigned APK.")

    out_dir = cfg.get("output_dir", "").strip()
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, os.path.basename(final_apk))
        shutil.move(final_apk, out_path)
        final_location = out_path
        tag_info(f"APK moved → {col(C.BYLW, out_path)}")
    else:
        final_location = final_apk
        tag_info(f"APK saved → {col(C.BYLW, final_apk)}")

    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    print()
    dline(C.BGRN)
    print(col(C.BGRN + C.BOLD, "  ✔  Download complete!".center(tw())))
    sz_f = (
        os.path.getsize(final_location) // 1024
        if os.path.exists(final_location) else 0
    )
    signed_label = (
        col(C.BGRN, "Yes (V1 + V2 + V3)")
        if signed_ok
        else col(C.DIM, "No")
    )
    print(col(C.BCYN, f"  Package : {pkg}"))
    print(col(C.BCYN, f"  File    : {final_location}"))
    print(col(C.BCYN, f"  Size    : {sz_f} KB"))
    print(col(C.BCYN, f"  Signed  : {signed_label}"))
    dline(C.BGRN)

    if will_install:
        auto_install_apk(final_location)

    pause()

def toggle_val(v):
    return "off" if v == "on" else "on"


def do_configure(cfg):
    while True:
        banner()
        section_header("Configure", "⚙")

        def opt_row(num, icon, label, value_str):
            n = col(C.BGBLK + C.BYLW + C.BOLD, f" {num} ")
            print(f"  {n}  {icon}  {col(C.BWHT, label + ':')}  {value_str}")
            print()

        opt_row(
            "1", "📦", "Prefer Split APKs",
            badge_on_off(cfg["prefer_split"]) +
            col(C.DIM + C.CYN, "  (on = download splits + merge, default)")
        )
        opt_row(
            "2", "📁", "Output Directory ",
            col(C.BCYN, cfg["output_dir"]
                or col(C.DIM, "(not set)"))
        )
        opt_row(
            "3", "🔗", "Dispenser Link   ",
            col(C.BCYN, cfg["dispenser_link"] or col(C.DIM, "(not set)"))
        )
        opt_row(
            "4", "⏭ ", "Skip Extras      ",
            badge_on_off(cfg["skip_extras"]) +
            col(C.DIM + C.CYN, "  (on = --skip-extras, default)")
        )

        arch_label = {
            ""      : col(C.DIM,  "arm64 (gplaydl default, --arch not passed)"),
            "arm64" : col(C.BCYN, "arm64  (explicitly passed)"),
            "armv7" : col(C.BCYN, "armv7  (32-bit ARM)"),
        }.get(cfg["arch"], col(C.BCYN, cfg["arch"]))
        opt_row("5", "📱", "Architecture     ", arch_label)

        ks_set   = bool(cfg.get("keystore_path") and
                        os.path.exists(cfg.get("keystore_path", "")))
        ks_label = (
            col(C.BCYN, cfg["keystore_path"]) +
            col(C.DIM + C.CYN,
                f"  alias={cfg.get('keystore_alias', '?')}")
            if ks_set
            else col(C.DIM, "(not configured)")
        )
        opt_row("6", "🔑", "Keystore         ", ks_label)

        opt_row(
            "7", "✍ ", "Sign APKs        ",
            badge_on_off(cfg.get("sign_apk", "off")) +
            (col(C.DIM + C.CYN, "  (keystore required)")
             if not ks_set else "")
        )

        opt_row(
            "8", "📲", "Auto Install APK ",
            badge_on_off(cfg.get("auto_install", "off")) +
            col(C.DIM + C.CYN,
                "  (termux-open --view  after download/sign)")
        )

        hline("─", C.CYN)
        print(f"  {col(C.BGBLK+C.BYLW+C.BOLD,' 9 ')}  💾  "
              f"{col(C.BGRN + C.BOLD, 'Save & Return')}")
        print()
        print(f"  {col(C.BGBLK+C.BYLW+C.BOLD,' 0 ')}  ↩   "
              f"{col(C.BRED, 'Discard & Return')}")
        hline("─", C.CYN)
        print()

        choice = ask("Select option").strip()

        if choice == "1":
            cfg["prefer_split"] = toggle_val(cfg["prefer_split"])
            tag_info(f"prefer_split → {badge_on_off(cfg['prefer_split'])}")
            if cfg["prefer_split"] == "on":
                tag_warn(
                    "Split APKs will be downloaded and merged by APKEditor.")
            else:
                tag_info("Single APK mode (--no-splits).")
            time.sleep(1.0)

        elif choice == "2":
            print()
            print(col(C.DIM + C.CYN,
                      "  Leave blank to keep APKs in ~/gplay/"))
            nd = ask("Output directory path",
                     default=cfg["output_dir"]).strip()
            cfg["output_dir"] = os.path.expanduser(nd) if nd else ""
            tag_info(
                f"Output directory → "
                f"{cfg['output_dir'] or '~/gplay (default)'}"
            )
            time.sleep(0.6)

        elif choice == "3":
            print()
            print(col(C.DIM + C.CYN,
                      "  Leave blank to use default token server."))
            nd = ask("Dispenser URL",
                     default=cfg["dispenser_link"]).strip()
            cfg["dispenser_link"] = nd
            tag_info(f"Dispenser → {nd or '(cleared)'}")
            time.sleep(0.6)

        elif choice == "4":
            cfg["skip_extras"] = toggle_val(cfg["skip_extras"])
            tag_info(f"skip_extras → {badge_on_off(cfg['skip_extras'])}")
            time.sleep(0.8)

        elif choice == "5":
            print()
            hline("─", C.CYN)
            print(col(C.BOLD + C.BWHT, "  Architecture options:"))
            print()
            arch_rows = [
                ("0", "Do not pass --arch  (gplaydl uses arm64 by default)"),
                ("1", "arm64  – 64-bit ARM (most modern devices)"),
                ("2", "armv7  – 32-bit ARM (older devices)"),
            ]
            for k, lbl in arch_rows:
                cur = (col(C.BGRN, "  ◀ current")
                       if cfg["arch"] == ARCH_OPTIONS[k] else "")
                print(
                    f"  {col(C.BYLW, f'[{k}]')}  {col(C.BWHT, lbl)}{cur}")
            hline("─", C.CYN)
            print()
            ac = ask("Select [0-2]", default="0").strip()
            if ac in ARCH_OPTIONS:
                cfg["arch"] = ARCH_OPTIONS[ac]
                tag_info(
                    "Architecture → "
                    + (cfg["arch"]
                       or "arm64 (gplaydl default, --arch not passed)")
                )
            else:
                tag_warn("Invalid – keeping current architecture.")
            time.sleep(0.8)

        elif choice == "6":
            cfg = configure_keystore(cfg)

        elif choice == "7":
            if not ks_set:
                tag_err("Configure a valid keystore (option 6) first.")
                time.sleep(1.0)
            else:
                cfg["sign_apk"] = toggle_val(cfg.get("sign_apk", "off"))
                tag_info(f"Sign APKs → {badge_on_off(cfg['sign_apk'])}")
                time.sleep(0.8)

        elif choice == "8":
            cfg["auto_install"] = toggle_val(cfg.get("auto_install", "off"))
            tag_info(
                f"Auto Install → {badge_on_off(cfg['auto_install'])}")
            if cfg["auto_install"] == "on":
                tag_warn(
                    "termux-open will be called after download completes.")
            time.sleep(0.8)

        elif choice == "9":
            save_config(cfg)
            pause()
            return cfg

        elif choice == "0":
            tag_warn("Changes discarded.")
            time.sleep(0.5)
            return cfg

        else:
            tag_warn("Invalid option – choose 1-9 or 0 to discard.")
            time.sleep(0.5)

def main_menu(cfg):
    while True:
        banner()
        status_bar(cfg)
        print()

        menu_row("1", "🔍", "Search & Download",      clr=C.BGRN)
        print()
        menu_row("2", "📱", "Replace Device Profile",  clr=C.BCYN)
        print()
        menu_row("3", "⚙ ", "Configure",               clr=C.BBLU)
        print()
        menu_row("4", "🔄", "Force Re-Authenticate",   clr=C.BYLW)
        print()
        menu_row("5", "🚪", "Exit",                     clr=C.BRED)
        print()

        hline("─", C.DIM + C.CYN)
        print(col(C.DIM + C.MAG, "  Created by GrayWizard".center(tw())))
        hline("─", C.DIM + C.CYN)
        print()

        choice = ask("Select option").strip()

        if choice == "1":
            do_search_download(cfg)
        elif choice == "2":
            do_replace_device_profile()
        elif choice == "3":
            cfg = do_configure(cfg)
        elif choice == "4":
            do_force_reauth(cfg)
        elif choice == "5":
            banner()
            print()
            dline(C.BMAG)
            print(col(C.BMAG + C.BOLD,
                      "  Thanks for using GPlayDL TUI".center(tw())))
            print(col(C.MAG,
                      "  Created by GrayWizard  ★".center(tw())))
            dline(C.BMAG)
            print()
            sys.exit(0)
        else:
            tag_warn("Invalid option – choose 1 to 5.")
            time.sleep(0.5)

def main():
    for d in (GPLAY_DIR, BIN_DIR, CONFIG_DIR):
        os.makedirs(d, exist_ok=True)
    ensure_dependencies()
    cfg = load_config()
    main_menu(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(col(C.BRED, "\n\n  Interrupted – goodbye!\n"))
        sys.exit(0)
