from flask import Flask, render_template_string, jsonify, request, Response, send_file
import os
import platform
import socket
import time
from datetime import datetime
from urllib.parse import urlparse, unquote
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
import ipaddress
import socket
import mimetypes
import re
import json
import threading
import tempfile
import shutil
import uuid
import sys
import subprocess
import importlib
import site
import glob

try:
    import yt_dlp
except Exception:
    yt_dlp = None

# Optional universal downloader engine. Some WSGI configurations omit the
# account's user-site directory from sys.path even when pip installed there.
_YTDLP_INSTALL_MESSAGE = ""

def _add_user_site_paths():
    """Expose this account's user-site folders, including pip's other Python minor versions.

    yt-dlp is pure Python. PythonAnywhere's console and WSGI app can use different
    Python versions, so pip may have installed it under (for example) python3.13
    while the web app runs under python3.10. Try the matching folder first, then
    other user-site folders as a compatibility fallback.
    """
    candidates = []
    try:
        user_site = site.getusersitepackages()
        candidates.extend(user_site if isinstance(user_site, (list, tuple)) else [user_site])
    except Exception:
        pass
    candidates.append(os.path.expanduser(
        f"~/.local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    ))
    candidates.extend(glob.glob(os.path.expanduser("~/.local/lib/python*/site-packages")))
    # Newest folders first after the exact interpreter path; duplicate paths are harmless.
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen and os.path.isdir(candidate):
            seen.add(candidate)
            if candidate not in sys.path:
                sys.path.append(candidate)

def ensure_yt_dlp():
    global yt_dlp, _YTDLP_INSTALL_MESSAGE
    if yt_dlp is not None:
        return True, "Universal downloader engine ready."
    try:
        _add_user_site_paths()
        importlib.invalidate_caches()
        yt_dlp = importlib.import_module("yt_dlp")
        return True, "Universal downloader engine ready."
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        _YTDLP_INSTALL_MESSAGE = (
            "yt-dlp is installed only if it is available to this web app's Python interpreter. "
            f"App Python: {sys.version.split()[0]} ({sys.executable}). "
            "Install with that interpreter's -m pip, then reload the web app. Import error: " + detail[:180]
        )
        return False, _YTDLP_INSTALL_MESSAGE

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

APP_NAME = "Fizzer"
APP_VERSION = "8.2.4"
MAX_LEVEL = 1200
NORMAL_LEVEL = 100

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#ffffff"><link rel="manifest" href="/manifest.json"><link rel="apple-touch-icon" href="/icon-192.svg">
<meta name="description" content="Fizzer audio and video utility">
<title>{{ app_name }}</title>
<style>
:root{--bg:#020202;--panel:#0b0b0c;--panel2:#121113;--line:#2b2528;--text:#fffaf0;--muted:#aaa1a0;--accent:#d6ad63;--accent2:#f2d39b;--danger:#ff625c}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
body{min-height:100vh}
body.light-mode{--bg:#f1f2f6;--panel:#fff;--panel2:#f7f7fa;--line:#d5d7df;--text:#17171d;--muted:#555966}
body.light-mode .top,body.light-mode .nav{background:#ffffffed;border-color:#d5d7df}
body.light-mode .card{background:linear-gradient(145deg,#fff,#f5f5fa);box-shadow:0 12px 30px #0001}
body.light-mode .nav button,body.light-mode .fileItem,body.light-mode .playerBox,body.light-mode .savedItem,body.light-mode .upload,body.light-mode select,body.light-mode .stat{background:#fff;color:#20212a;border-color:#d5d7df}
body.light-mode .btn.secondary,body.light-mode .miniBtn{background:#eceef4;color:#20212a;border-color:#c9cbd4}
.app{width:min(720px,100%);margin:auto;min-height:100vh;padding-bottom:92px}
.top{position:sticky;top:0;z-index:30;padding:15px 16px 11px;background:#050505ee;backdrop-filter:blur(18px);border-bottom:1px solid #222}
.brand{display:flex;align-items:center;justify-content:space-between}.brand h1{font-size:24px;margin:0;font-weight:900;letter-spacing:-1px}.brand small{color:#777;font-size:9px;letter-spacing:1.5px}
main{padding:16px}.page{display:none}.page.active{display:block}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(720px,100%);z-index:40;padding:9px 12px calc(9px + env(safe-area-inset-bottom));background:#050505ee;backdrop-filter:blur(18px);border-top:1px solid #222}
.navGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.nav button{border:1px solid transparent;touch-action:manipulation;-webkit-tap-highlight-color:transparent;background:#0d0d0f;color:#777;border-radius:14px;padding:9px 3px;font-size:10px}.nav button.active{background:linear-gradient(135deg,var(--accent2),var(--accent));color:#050505;border-color:var(--accent)}.navIcon{display:block;font-size:17px;margin-bottom:3px}
.hero{text-align:center;padding:4px 0 14px}.hero h2{font-size:31px;line-height:1.03;margin:7px 0;letter-spacing:-1.7px}.hero p{color:var(--muted);font-size:12px;line-height:1.55;margin:0}
.card{background:radial-gradient(circle at 85% 0%,#17152b 0%,transparent 34%),linear-gradient(145deg,#111118,#08080c);border:1px solid var(--line);border-radius:22px;padding:17px;margin:13px 0;box-shadow:0 18px 48px #0009}
.headphone{height:205px;position:relative;width:280px;margin:0 auto 2px}
.earbud{position:absolute;width:76px;height:105px;top:54px;background:linear-gradient(145deg,#f4f4fa,#8f8ca5);border:2px solid #66543a;border-radius:38px 38px 30px 30px;box-shadow:0 16px 35px #000,0 0 24px #d6ad6333}
.earbud:before{content:"";position:absolute;top:16px;left:18px;width:37px;height:45px;background:#15151c;border-radius:22px;border:2px solid #66627b}
.earbud:after{content:"";position:absolute;bottom:-30px;left:29px;width:19px;height:42px;background:linear-gradient(#b7b4c5,#77738d);border-radius:0 0 13px 13px}
.earbud.left{left:57px;transform:rotate(-8deg)}.earbud.right{right:57px;transform:rotate(8deg)}
.earbudStem{position:absolute;bottom:2px;width:20px;height:34px;background:#8d899c;border-radius:0 0 12px 12px}
.earbud.left .earbudStem{left:29px}.earbud.right .earbudStem{right:29px}

.handsfreeArt{height:215px;position:relative;width:300px;margin:0 auto 2px}
.hfWire{position:absolute;top:18px;width:76px;height:88px;border:7px solid #d6ad63;border-bottom:0;border-radius:50px 50px 0 0;opacity:.7}
.leftWire{left:65px;transform:rotate(-19deg)}.rightWire{right:65px;transform:rotate(19deg)}
.hfBud{position:absolute;top:76px;width:68px;height:88px;border-radius:27px 27px 34px 34px;background:linear-gradient(145deg,#f7fffd,#a5b7b3);border:2px solid #56635f;box-shadow:0 14px 32px #000,0 0 22px #d6ad6333}
.hfBud.leftBud{left:51px;transform:rotate(-8deg)}.hfBud.rightBud{right:51px;transform:rotate(8deg)}
.hfBud:before{content:"";position:absolute;left:16px;top:13px;width:32px;height:38px;border-radius:18px;background:#101516;border:2px solid #63706d;box-shadow:inset 0 0 12px #d6ad6322}
.hfBud i{position:absolute;width:9px;height:24px;bottom:-17px;left:28px;border-radius:0 0 8px 8px;background:#a8b7b4}.hfBud b{position:absolute;width:7px;height:7px;border-radius:50%;background:#d6ad63;right:12px;top:12px;box-shadow:0 0 10px #d6ad63}
.hfCase{position:absolute;left:112px;bottom:0;width:76px;height:42px;border-radius:15px 15px 20px 20px;background:linear-gradient(#20282a,#0d1112);border:2px solid #47514f;box-shadow:0 13px 28px #000}
.hfCaseLight{position:absolute;left:33px;top:8px;width:8px;height:4px;border-radius:4px;background:#d6ad63;box-shadow:0 0 12px #d6ad63}
.big{text-align:center;font-size:60px;font-weight:950;letter-spacing:-5px}.sub{text-align:center;color:#777;font-size:11px;margin-top:-5px}.slider{margin-top:12px}
input[type=range]{width:100%;height:7px;appearance:none;background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:99px;outline:0}input[type=range]::-webkit-slider-thumb{appearance:none;width:25px;height:25px;border-radius:50%;background:#f5f5ff;box-shadow:0 0 0 4px #fff1}
.scale{display:flex;justify-content:space-between;color:#666;font-size:10px;margin-top:8px}
.warning{display:none;margin-top:13px;padding:12px;border-radius:14px;background:#241212;border:1px solid #60302e;color:#ffaaa5;font-size:11px;line-height:1.5}.warning.show{display:block}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px}.row+.row{margin-top:17px}.label b{display:block;font-size:13px}.label small{display:block;color:#777;font-size:10px;margin-top:4px}
.switch{touch-action:manipulation;-webkit-tap-highlight-color:transparent;width:54px;height:31px;background:#29292d;border:1px solid #3d3d42;border-radius:30px;padding:3px;cursor:pointer}.switch i{display:block;width:23px;height:23px;background:#8d8d92;border-radius:50%;transition:.18s}.switch.on{background:linear-gradient(135deg,var(--accent2),var(--accent));border-color:var(--accent2);box-shadow:0 0 18px var(--accent)88}.switch.on i{transform:translateX(23px);background:#050505;box-shadow:0 0 10px #fff}
.btn{cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:transparent;transition:filter .18s,transform .12s;width:100%;border:1px solid var(--accent);background:linear-gradient(135deg,var(--accent2),var(--accent));color:#050505;border-radius:14px;padding:13px;font-weight:850;margin-top:12px}.btn.secondary{background:#151517;color:#eee}.btn.danger{background:#251313;color:#ffaaa5;border-color:#5c2927}
.status{font-size:10px;color:#777;margin-top:11px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#777;margin-right:5px}.dot.on{background:#eee;box-shadow:0 0 12px #fff}
.upload{border:1px dashed #4b4b50;background:#09090b;border-radius:19px;padding:25px 15px;text-align:center}.upload.drag{background:#151517;border-color:#eee}.uploadIcon{font-size:31px}.upload h3{margin:6px 0 4px}.upload p{margin:0;color:#777;font-size:11px}
.fileBtn{display:inline-block;margin-top:14px;padding:11px 16px;border-radius:12px;background:linear-gradient(135deg,var(--accent2),var(--accent));color:#050505;font-size:12px;font-weight:850;cursor:pointer}.hiddenInput{display:none}
.queue{display:grid;gap:8px;margin-top:13px}.fileItem{display:grid;grid-template-columns:40px 1fr auto;gap:10px;align-items:center;background:#111114;border:1px solid #28282c;border-radius:14px;padding:10px}.fileIcon{width:40px;height:40px;border-radius:11px;background:#202024;display:grid;place-items:center}.fileName{font-size:11px;font-weight:750;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.fileMeta{font-size:9px;color:#777;margin-top:3px}.remove{background:transparent;border:0;color:#888;font-size:19px;padding:6px}
.playerBox{margin-top:13px;background:#0b0b0d;border:1px solid #28282c;border-radius:17px;padding:13px}audio{width:100%;filter:invert(1) grayscale(1)}.progress{height:7px;background:#202024;border-radius:10px;overflow:hidden;margin-top:11px;position:relative;cursor:pointer;touch-action:pan-y}
.progress i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:inherit;will-change:width;transition:none}
.fizzerWordmark{font-size:clamp(58px,17vw,92px);font-weight:950;line-height:1.15;letter-spacing:0;color:var(--accent2);text-shadow:0 5px 22px color-mix(in srgb,var(--accent) 38%,transparent);margin:0 auto 8px}
body.light-mode .fizzerWordmark{color:var(--accent);text-shadow:none}
.pronounceWordmark{font-size:clamp(30px,9vw,46px);line-height:1.2;margin:2px auto 0;text-shadow:none}
.controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}select{width:100%;background:#151517;color:#eee;border:1px solid #333;border-radius:12px;padding:11px}
.statGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.stat{padding:13px;background:#101012;border:1px solid #29292d;border-radius:14px}.stat b{display:block;font-size:16px}.stat span{display:block;color:#777;font-size:9px;margin-top:4px}
.info{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #222;font-size:11px}.info:last-child{border-bottom:0}.info span{color:#777}
.note{color:#777;font-size:10px;line-height:1.55}.toast{position:fixed;z-index:99;left:50%;bottom:90px;transform:translate(-50%,20px);opacity:0;background:#eee;color:#050505;border-radius:12px;padding:10px 14px;font-size:11px;font-weight:850;transition:.2s;pointer-events:none}.toast.show{opacity:1;transform:translate(-50%,0)}
.modal{position:fixed;inset:0;z-index:80;display:none;align-items:flex-end;background:#000b}.modal.show{display:flex}.sheet{width:min(720px,100%);margin:auto 0 0;background:#111114;border:1px solid #333;border-radius:24px 24px 0 0;padding:20px 17px 28px}.sheet h3{margin:0 0 7px}.sheet p{color:#999;font-size:11px;line-height:1.55}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}

.emptySaved{padding:30px 10px;text-align:center;color:#68686d;font-size:11px}
.savedItem{display:grid;grid-template-columns:42px minmax(0,1fr) auto;gap:10px;align-items:center;background:#0d0d10;border:1px solid #25252b;border-radius:16px;padding:10px;cursor:pointer}
.savedItem:active{transform:scale(.99)}
.savedPlayIcon{width:42px;height:42px;border-radius:13px;background:linear-gradient(145deg,var(--accent2),var(--accent));color:#050505;display:grid;place-items:center;font-weight:950}
.savedActions{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}
.miniBtn{border:1px solid #38383f;background:#17171b;color:#eee;border-radius:10px;padding:8px 9px;font-size:10px;font-weight:800}
.miniBtn.primary{background:var(--accent);color:#050505;border-color:var(--accent)}
#accentSelect{border-color:var(--accent)!important;box-shadow:0 0 0 1px var(--accent2)22;background:#151517;color:#eee}
#downloadFormat{border-color:var(--accent);background:#151517;color:#eee;min-height:42px}
button:disabled,select:disabled{opacity:.45;cursor:not-allowed}

body.light-mode{--bg:#f5f7fb;--panel:#ffffff;--panel2:#f8faff;--line:#dfe4ee;--text:#171923;--muted:#626a7a;color-scheme:light}
body.light-mode,body.light-mode main,body.light-mode .page{background:#f5f7fb!important;color:#171923}
body.light-mode .top,body.light-mode .nav{background:#f8faff!important;border-color:#dfe4ee!important;color:#171923}
body.light-mode .card,body.light-mode .playerBox,body.light-mode .fileItem,body.light-mode .savedItem,body.light-mode .upload,body.light-mode .stat,body.light-mode .queue,body.light-mode .sheet,body.light-mode .warning{background:#fff!important;color:#171923!important;border-color:#dfe4ee!important;box-shadow:0 5px 20px #26334d12}
body.light-mode input,body.light-mode textarea,body.light-mode select,body.light-mode #downloadFormat,body.light-mode #accentSelect{background:#f8faff!important;color:#171923!important;border-color:#d5dbe7!important}
body.light-mode .btn.secondary,body.light-mode .miniBtn,body.light-mode .nav button{background:#eef2f8!important;color:#252b39!important;border-color:#d5dbe7!important}
body.light-mode .hero h2,body.light-mode .label,body.light-mode .fileName,body.light-mode .info,body.light-mode h1,body.light-mode h2,body.light-mode h3,body.light-mode p,body.light-mode small,body.light-mode .sub,body.light-mode .note{color:#171923}
body.light-mode .brand small,body.light-mode .muted,body.light-mode .fileMeta{color:#626773!important}


#installGate{position:fixed;inset:0;z-index:99999;background:#fff;color:#172033;display:none;flex-direction:column;align-items:center;justify-content:center;padding:28px 24px calc(28px + env(safe-area-inset-bottom));font-family:Inter,system-ui,sans-serif;text-align:center}
html.install-required #installGate{display:flex}
html.installed-pwa #installGate{display:none!important}
html.installed-pwa #fizzerApp{display:block!important}
#installGate[hidden]{display:none!important}.installLogo{width:104px;height:104px;border-radius:26px;box-shadow:0 12px 30px #17203320;margin-bottom:22px}.installTitle{font-size:30px;font-weight:800;letter-spacing:-.8px;margin:0}.installSub{font-size:14px;color:#667085;margin:9px 0 0}.installFoot{position:absolute;left:22px;right:22px;bottom:calc(22px + env(safe-area-inset-bottom));display:flex;gap:12px}.installFoot button{height:52px;border-radius:14px;border:1px solid #d0d5dd;font-weight:700;font-size:15px;flex:1;background:#fff;color:#344054}.installFoot #gateInstall{background:#111827;color:#fff;border-color:#111827}.installHint{font-size:12px;color:#98a2b3;margin-top:18px;max-width:290px;line-height:1.5}

/* Home link downloader */
.linkDownloadCard{position:relative;overflow:hidden;margin-top:28px!important}
.linkDownloadControls{display:flex;justify-content:center;margin-top:14px!important}
.linkDownloadControls #linkDownloadBtn{width:min(100%,320px);min-height:50px;text-align:center;display:flex;align-items:center;justify-content:center;margin-inline:auto}
.linkDownloadCard:before{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:2px;background:linear-gradient(90deg,transparent,var(--accent),transparent);opacity:.85}
.linkDownloadHead{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.linkDownloadIcon{width:44px;height:44px;flex:0 0 44px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(145deg,var(--accent2),var(--accent));color:#080808;font-size:21px;box-shadow:0 8px 22px color-mix(in srgb,var(--accent) 25%,transparent)}
.linkDownloadHead h3{margin:0;font-size:16px;letter-spacing:-.3px}
.linkDownloadHead p{margin:4px 0 0;color:var(--muted);font-size:10px;line-height:1.45}
.linkDownloadInput{width:100%;min-width:0;padding:14px;border-radius:13px;border:1px solid var(--line);background:var(--panel2);color:var(--text);outline:none;font:inherit;font-size:12px}
.linkDownloadInput:focus{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 16%,transparent)}
.linkDownloadProgress{display:none;margin-top:14px;padding:12px;border:1px solid var(--line);border-radius:14px;background:var(--panel2)}
.linkDownloadProgress.show{display:block}
.linkProgressTop{display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:11px;font-weight:800}
.linkProgressMeta{color:var(--muted);font-size:10px;margin-top:6px;display:flex;justify-content:space-between;gap:8px}
.linkProgressTrack{height:8px;border-radius:99px;background:color-mix(in srgb,var(--text) 10%,transparent);overflow:hidden;margin-top:10px}
.linkProgressTrack i{display:block;width:0;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--accent2),var(--accent));transition:width .15s}
.linkDownloadNote{font-size:10px;color:var(--muted);line-height:1.5;margin:10px 1px 0}.linkCheckResult{display:none;margin-top:10px;padding:11px 12px;border:1px solid var(--line);border-radius:13px;background:var(--panel2);font-size:10px;line-height:1.5;color:var(--muted)}.linkFormats{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.linkFormat{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:10px;padding:6px 8px;font-size:9px}.linkPreview{display:none;margin-top:14px;padding:12px;border:1px solid var(--line);border-radius:16px;background:var(--panel2)}.linkPreview.show{display:block}.linkPreviewHero{display:flex;gap:12px;align-items:flex-start}.linkPreviewThumb{display:none;width:124px;aspect-ratio:16/9;object-fit:cover;border-radius:10px;background:var(--panel);border:1px solid var(--line);flex:0 0 auto}.linkPreviewTitle{font-size:12px;font-weight:800;line-height:1.4;overflow-wrap:anywhere}.linkPreviewMeta{font-size:10px;color:var(--muted);margin-top:5px;line-height:1.5}.linkFormatSelect{width:100%;margin-top:12px;padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--panel);color:var(--text);font:inherit;font-size:12px}.linkPreviewActions{display:flex;gap:8px;margin-top:10px}.linkPreviewActions .btn{flex:1}
</style>
<script>
/* Decide install-gate visibility before first paint to prevent a flash on installed phones. */
(function(){
 let installed=false;
 try{installed=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true||localStorage.getItem('fizzer_app_installed_v1')==='yes';}catch(e){installed=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;}
 document.documentElement.classList.add(installed?'installed-pwa':'install-required');
})();
</script>
</head>
<body>
<div id="installGate">
 <svg class="installLogo" viewBox="0 0 512 512" role="img" aria-label="Fizzer icon"><defs><linearGradient id="fg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f7dfae"/><stop offset="1" stop-color="#c18b3f"/></linearGradient></defs><rect width="512" height="512" rx="116" fill="#070709"/><rect x="28" y="28" width="456" height="456" rx="100" fill="#111116" stroke="url(#fg)" stroke-width="12"/><path d="M174 365V147h181v48H232v42h105v46H232v82z" fill="url(#fg)"/><path d="M365 311a52 52 0 1 1-104 0 52 52 0 0 1 104 0z" fill="#070709" stroke="url(#fg)" stroke-width="13"/><path d="M282 310l20 20 42-47" fill="none" stroke="url(#fg)" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/></svg>
 <h1 class="installTitle">Fizzer</h1><p class="installSub">Your audio workspace, ready to install</p>
 <p class="installHint" id="gateHint">Install Fizzer for quick access from your home screen.</p>
 <div class="installFoot"><button id="gateCancel" type="button">Cancel</button><button id="gateInstall" type="button">Install</button></div>
</div>
<div class="app" id="fizzerApp">
<header class="top"><div class="brand"><div><h1>Fizzer</h1><small>OFFLINE AUDIO UTILITY</small></div><button id="installBtn" class="btn secondary" style="display:none;margin:0;padding:7px 10px;font-size:10px">Install App</button></div></header>
<main>

<section id="home" class="page active">
 <div class="hero"><div class="headphone handsfreeArt">
  <div class="hfWire leftWire"></div><div class="hfWire rightWire"></div>
  <div class="hfBud leftBud"><i></i><b></b></div><div class="hfBud rightBud"><i></i><b></b></div>
  <div class="hfCase"><div class="hfCaseLight"></div></div>
</div><h2>Fizzer Audio Control</h2><p>Control software gain for audio played through Fizzer.</p></div>
 <div class="card">
  <div class="big" id="levelText">100</div><div class="sub">FIZZER AUDIO LEVEL</div>
  <div class="slider"><input id="level" type="range" min="0" max="1200" step="1" value="100"></div>
  <div class="scale"><span>0</span><span>100</span><span>400</span><span>800</span><span>1200 MAX</span></div>
 </div>
 <div class="card">
  <div class="row"><div class="label"><b>Dark Mode</b><small>Switch between dark and light appearance.</small></div><button type="button" id="darkToggle" class="switch on" aria-label="Toggle dark mode"><i></i></button></div>
  <div class="row"><div class="label"><b>Accent Colour</b><small>Choose the VIP accent while keeping the interface black.</small></div><div style="display:flex;align-items:center;gap:8px"><span id="accentSwatch" style="width:18px;height:18px;border-radius:50%;border:1px solid #555;display:block"></span><select id="accentSelect" style="max-width:160px">
<option value="gold">Champagne Gold</option>
<option value="violet">Night Violet</option>
<option value="ultraviolet">Ultraviolet</option>
<option value="midnight">Midnight Blue</option>
<option value="abyss">Abyss Black</option>
<option value="obsidian">Obsidian</option>
<option value="eclipse">Eclipse Purple</option>
<option value="bloodmoon">Blood Moon</option>
<option value="darkrose">Dark Rose</option>
<option value="phantom">Phantom Blue</option>
<option value="toxic">Toxic Night</option>
<option value="cyber">Cyber Cyan</option>
<option value="emerald">Emerald Night</option>
<option value="ice">Black Ice</option>
<option value="silver">Ice Silver</option>
<option value="neonpink">Neon Pink</option>
<option value="deepblue">Deep Blue</option>
<option value="darkpurple">Dark Purple</option>
<option value="darkteal">Dark Teal</option>
<option value="ember">Dark Ember</option>
<option value="shadowred">Shadow Red</option>
<option value="nightgold">Night Gold</option>
<option value="electricviolet">Electric Violet</option>
</select></div>
  
 </div>
 <button class="btn secondary" id="boostBtn">Boost to Current Maximum</button>
 <div class="card linkDownloadCard">
  <div class="linkDownloadHead"><div class="linkDownloadIcon">⇩</div><div><h3>Download from Link</h3><p>Paste a link. Fizzer checks available formats, then downloads your selection.</p></div></div>
  <input id="linkDownloadUrl" class="linkDownloadInput" type="url" inputmode="url" autocomplete="url" placeholder="https://example.com/video.mp4" aria-label="Media download URL">
  <div class="linkDownloadControls"><button class="btn" id="linkDownloadBtn" type="button">Download</button></div><div class="linkCheckResult" id="linkCheckResult" aria-live="polite"></div><div class="linkPreview" id="linkPreview" aria-live="polite"><div class="linkPreviewHero"><img class="linkPreviewThumb" id="linkPreviewThumb" alt="Video thumbnail"><div><div class="linkPreviewTitle" id="linkPreviewTitle">Media preview</div><div class="linkPreviewMeta" id="linkPreviewMeta"></div></div></div><label class="linkFormatLabel" for="linkOutputFormat">Output format</label><select class="linkFormatSelect" id="linkOutputFormat" aria-label="Output format"><option value="mp4">MP4 video</option><option value="mp3">MP3 audio</option><option value="original">Original format</option></select><label class="linkFormatLabel" for="linkFormatSelect">Quality</label><select class="linkFormatSelect" id="linkFormatSelect" aria-label="Video quality"><option value="best">Best available quality</option></select></div>
  <div class="linkDownloadProgress" id="linkDownloadProgress" aria-live="polite">
   <div class="linkProgressTop"><span id="linkDownloadStatus">Preparing download…</span><strong id="linkDownloadPercent">0%</strong></div>
   <div class="linkProgressTrack"><i id="linkDownloadBar"></i></div>
   <div class="linkProgressMeta"><span id="linkDownloadBytes">0 B / Unknown size</span><span id="linkDownloadSpeed"></span></div>
  </div>
  <p class="linkDownloadNote">Tap Download to check the link and load formats. Choose a quality, then tap Download again. Speed depends on the source and hosting server; private or restricted content is not supported.</p>
 </div>
</section>

<section id="player" class="page">
 <div class="hero"><h2>Player</h2><p>Choose one file or select many. Audio plays in order, and video files can be saved or downloaded as audio.</p></div>
 <div class="card">
  <div class="row" style="margin-bottom:10px"><div class="label"><b>Player Volume</b><small>Fizzer software level for the selected media.</small></div><strong id="playerLevel">100</strong></div>
  <input id="playerLevelRange" type="range" min="0" max="1200" step="1" value="100">
  <div class="scale"><span>0</span><span>100</span><span>400</span><span>800</span><span>1200 MAX</span></div>
 </div>
 <div class="card">
  <div id="upload" class="upload"><div class="uploadIcon">◉</div><h3>Add your media</h3><p>Audio and browser-supported video files are accepted. MP4 download is available for MP4 source files.</p><button type="button" class="fileBtn" id="chooseFilesBtn">Choose media files</button><input id="fileInput" class="hiddenInput" type="file" multiple accept="audio/*,video/*"></div>
  <div id="queue" class="queue"></div>
  <div class="playerBox">
   <video id="videoPlayer" controls playsinline disablepictureinpicture style="display:none;width:100%;max-height:300px;border-radius:12px;background:#000"></video><audio id="audio" controls playsinline></audio>
   <div class="progress"><i id="progress"></i></div>
   <div class="controls">
    <button class="btn secondary" id="prevBtn" style="margin:0">Previous</button><button class="btn secondary" id="nextBtn" style="margin:0">Next</button>
    <button class="btn secondary" id="repeatBtn" style="margin:0">Repeat: ON</button>
    <select id="speed"><option value=".5">0.5×</option><option value=".75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="3">3×</option><option value="4">4×</option></select>
   </div>
   <div class="card" style="margin-top:12px;padding:12px;background:#0b0b0e">
    <div class="row"><div class="label"><b>Export Format</b><small>Choose an audio format, or download the original video.</small></div>
     <select id="downloadFormat" style="max-width:190px">
      <option value="wav">WAV — audio only</option>
      <option value="webm">WebM/Opus — audio only</option>
      <option value="ogg">OGG/Opus — audio only</option>
      <option value="m4a">M4A/AAC — audio only</option>
      <option value="original">Original audio (audio files)</option>
     </select>
    </div>
    <div class="controls" style="margin-top:10px">
     <button class="btn secondary" id="saveCurrentBtn" style="margin:0">Save Media</button>
     <button class="btn secondary" id="saveAudioBtn" style="margin:0">Save Audio</button>
     <button class="btn secondary" id="downloadCurrentBtn" style="margin:0">Download Audio</button>
     <button class="btn secondary" id="downloadVideoBtn" style="margin:0;display:none">Download Video</button>
    </div>
   </div>
   <button class="btn danger" id="clearBtn">Clear all files</button>
  </div>
 </div>
</section>



<section id="save" class="page">
 <div class="hero"><h2>Save</h2><p>Your saved audio and video library. Files stay here until you delete them or browser/app storage is cleared.</p></div>
 <div class="card">
  <div class="row">
   <div class="label"><b>Saved Audio &amp; Video</b><small>Saved files stay on this device until you delete them.</small></div>
   <span id="savedCount" style="font-size:10px;color:#777">0 saved</span>
  </div>
  <div id="savedList" class="queue"></div>
  <div class="card" id="trialCard"><h3>Trial Video</h3><p class="note">Use this video to test playback and sound control.</p><video id="trialVideo" controls playsinline style="width:100%;max-height:260px;border-radius:12px;background:#000"><source src="/trial-video" type="video/mp4"></video><div class="controls"><button class="btn secondary" id="editTrialBtn" type="button" style="margin:0">Edit Trial Video</button><button class="btn danger" id="removeTrialBtn" type="button" style="margin:0">Remove Trial Video</button></div></div>
  <div class="card" id="trialCard2"><h3>Trial Video 2</h3><p class="note">Second sample video for playback and sound control.</p><video id="trialVideo2" controls playsinline preload="metadata" style="width:100%;max-height:260px;border-radius:12px;background:#000"><source src="/trial-video-2?v=3" type="video/mp4"></video><div class="controls"><button class="btn secondary" id="editTrialBtn2" type="button" style="margin:0">Edit Trial Video</button><button class="btn danger" id="removeTrialBtn2" type="button" style="margin:0">Remove Trial Video</button></div></div>
  <div id="emptySaved" class="emptySaved">No saved media yet.</div>
  <button class="btn danger" id="clearSavedBtn">Delete All Saved Media</button>
 </div>
</section>

<section id="about" class="page">
 <div class="hero"><h2>About Fizzer</h2><p>A mobile-friendly audio and video player with media tools.</p></div>
 <div class="card">
  <div class="info"><span>Audio playback</span><b>Local files</b></div>
  <div class="info"><span>Video playback</span><b>Browser-supported formats</b></div>
  <div class="info"><span>Multiple files</span><b>Queue playback</b></div>
  <div class="info"><span>Playback speed</span><b>0.5×–4×</b></div>
  <div class="info"><span>Software audio level</span><b>0–1200</b></div>
  <div class="info"><span>Media controls</span><b>Play, pause, previous, next</b></div>
  <div class="info"><span>Save &amp; download</span><b>Available tools</b></div>
  <div class="info"><span>Offline interface</span><b>After first online load</b></div>
  <div class="info"><span>Appearance</span><b>Accent colours and light mode</b></div>
 </div>
 <div class="card"><h3>Pronounce</h3><div class="fizzerWordmark pronounceWordmark" lang="ur" dir="rtl">فائزر</div></div>
 <div class="card"><h3>Playback progress</h3><p class="note">The progress indicator follows the current playback time for audio and video. Its accuracy depends on the media file's duration information and the browser's playback updates.</p></div>
 <div class="card"><h3>Background playback</h3><p class="note">Fizzer supports browser media-session controls and may continue playing when sent to the background, depending on browser and Android settings. Playback is not guaranteed after the browser or app is forcibly closed.</p></div>
 <div class="card"><h3>Saving and offline use</h3><p class="note">Saved media is stored in browser/app storage on this device and can be removed by clearing it. The interface may be available offline after its first online load; local media playback does not require internet access.</p></div>
 <div class="card"><h3>Audio level safety</h3><div class="warning" style="display:block">The 0–1200 control is a software gain scale, not a physical loudness measurement. High levels can distort sound and may be uncomfortable or harmful to hearing. Keep volume at a comfortable level.</div></div>
 <div class="card"><h3>Device compatibility</h3><p class="note">Fizzer uses browser-supported media formats and features. Available formats and performance can vary by phone, browser, memory, and the size or encoding of the selected file.</p></div>
</section>
</main>
<nav class="nav"><div class="navGrid">
 <button class="active" data-page="home"><span class="navIcon">⌂</span>Home</button><button data-page="player"><span class="navIcon">♫</span>Player</button><button data-page="about"><span class="navIcon">ⓘ</span>About</button><button data-page="save"><span class="navIcon">▣</span>Save</button>
</div></nav>
</div>

<div id="toast" class="toast"></div>
<div id="mediaChoiceModal" class="modal" role="dialog" aria-modal="true" aria-labelledby="mediaChoiceTitle">
 <div class="sheet"><div style="width:42px;height:4px;border-radius:9px;background:var(--accent);margin:0 auto 18px"></div>
 <div style="font-size:28px;text-align:center;margin-bottom:8px">▣</div>
 <h3 id="mediaChoiceTitle" style="text-align:center">How would you like to open this video?</h3>
 <p style="text-align:center">Choose playback mode. You can still use the available audio tools with this video.</p>
 <div class="actions"><button class="btn secondary" id="choiceVideo" type="button" style="margin:0">▶ Play Video</button><button class="btn" id="choiceAudio" type="button" style="margin:0">♫ Play Audio</button></div>
 </div></div>

<script>
const $=id=>document.getElementById(id);
const MAX_LEVEL=1200;
let level=Number(localStorage.getItem("fizzer_level")||100);
let audioCtx=null,sourceNode=null,gainNode=null,queue=[],current=0,repeatAll=localStorage.getItem("fizzer_repeat")!=="0";
let objectUrls=[], lastVisibility=Date.now();
const audioOnlyFiles=new WeakSet();
function isVideoFile(f){return !!f && (f.type.startsWith("video/") || /\.(mp4|webm|mov|m4v|ogv)$/i.test(f.name||""));}
function chooseVideoMode(){return new Promise(resolve=>{const m=$("mediaChoiceModal");m.classList.add("show");const done=v=>{m.classList.remove("show");$("choiceVideo").onclick=null;$("choiceAudio").onclick=null;resolve(v)};$("choiceVideo").onclick=()=>done("video");$("choiceAudio").onclick=()=>done("audio")})}
let pendingFiles=null;
function setAccent(name){
 const root=document.documentElement;
 const themes={
  gold:["#d6ad63","#f2d39b"],
  violet:["#8d68ff","#c6b5ff"],
  ultraviolet:["#b14cff","#ff7cff"],
  midnight:["#3d69ff","#7ca2ff"],
  abyss:["#353542","#77778f"],
  obsidian:["#8c8c99","#c7c7d1"],
  eclipse:["#b23bff","#ff8df4"],
  bloodmoon:["#a71931","#ff5c6c"],
  darkrose:["#a72f62","#ff6fae"],
  phantom:["#6570ff","#b7bcff"],
  toxic:["#74c934","#c8ff72"],
  cyber:["#18bfe8","#70efff"],
  emerald:["#23ad7b","#6ff0be"],
  ice:["#8caac1","#dcefff"],
  silver:["#bfc8d0","#f1f6fa"],
  neonpink:["#ff2fa8","#ff86d7"],
  deepblue:["#1d4ed8","#60a5fa"],
  darkpurple:["#5b21b6","#c084fc"],
  darkteal:["#0f766e","#5eead4"],
  ember:["#c2410c","#fb923c"],
  shadowred:["#7f1d1d","#f87171"],
  nightgold:["#92723b","#f6d78d"],
  electricviolet:["#6d28d9","#d8b4fe"]
 };
 const c=themes[name]||themes.gold;
 root.style.setProperty("--accent",c[0]);
 root.style.setProperty("--accent2",c[1]);
 localStorage.setItem("fizzer_accent",name);
 const sw=$("accentSwatch");
 if(sw)sw.style.background="linear-gradient(135deg,"+c[0]+","+c[1]+")";
}



let trialRemoved=localStorage.getItem("fizzer_trial_removed")==="1";
function syncTrial(){const v=$("trialVideo"),b=$("removeTrialBtn");if(trialRemoved){v.style.display="none";b.textContent="Trial Video Removed";b.disabled=true;}else{v.style.display="block";b.textContent="Remove Trial Video";b.disabled=false;}}
$("removeTrialBtn").onclick=()=>{const v=$("trialVideo");v.pause();v.removeAttribute("src");v.querySelector("source")?.removeAttribute("src");v.load();trialRemoved=true;localStorage.setItem("fizzer_trial_removed","1");syncTrial();toast("Trial video removed from Save page");};
$("editTrialBtn").onclick=async()=>{try{const r=await fetch("/trial-video",{cache:"no-store"});if(!r.ok)throw new Error("Trial video is unavailable");const blob=await r.blob();const f=new File([blob],"Fizzer-Trial-Video.mp4",{type:"video/mp4",lastModified:Date.now()});queue=[f];current=0;renderQueue();go("player");loadCurrent(true);toast("Trial video opened in Player for editing");}catch(e){toast(e.message||"Could not open trial video")}};
let trial2Removed=localStorage.getItem("fizzer_trial2_removed_v3")==="1";
function syncTrial2(){const v=$("trialVideo2"),b=$("removeTrialBtn2"),card=$("trialCard2");if(trial2Removed){v.style.display="none";b.textContent="Trial Video Removed";b.disabled=true;}else{v.style.display="block";b.textContent="Remove Trial Video";b.disabled=false;}}
$("removeTrialBtn2").onclick=()=>{const v=$("trialVideo2");v.pause();v.removeAttribute("src");v.querySelector("source")?.removeAttribute("src");v.load();trial2Removed=true;localStorage.setItem("fizzer_trial2_removed_v3","1");syncTrial2();toast("Trial video 2 removed from Save page");};
$("editTrialBtn2").onclick=async()=>{try{const r=await fetch("/trial-video-2",{cache:"no-store"});if(!r.ok)throw new Error("Trial video 2 is unavailable");const blob=await r.blob();const f=new File([blob],"Fizzer-Trial-Video-2.mp4",{type:"video/mp4",lastModified:Date.now()});queue=[f];current=0;renderQueue();go("player");loadCurrent(true);toast("Trial video 2 opened in Player for editing");}catch(e){toast(e.message||"Could not open trial video 2")}};
function toast(t){$("toast").textContent=t;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),1700)}
function sync(){
 $("level").value=level;$("levelText").textContent=level;
 if($("playerLevel")){$("playerLevel").textContent=level;$("playerLevelRange").value=level}
  
 if(gainNode||videoGainNode)applyGain();
 localStorage.setItem("fizzer_level",level);
}
$("level").addEventListener("input",e=>{
 const v=Number(e.target.value);
 level=Math.max(0,Math.min(MAX_LEVEL,v));
 sync();
});
$("playerLevelRange").addEventListener("input",e=>{
 const v=Number(e.target.value);
 level=Math.max(0,Math.min(MAX_LEVEL,v));
 sync();
});
const darkSaved=localStorage.getItem("fizzer_dark")!=="0";
function setDark(on){document.body.classList.toggle("light-mode",!on);$("darkToggle").classList.toggle("on",on);localStorage.setItem("fizzer_dark",on?"1":"0");}
$("darkToggle").onclick=()=>{setDark(document.body.classList.contains("light-mode"));toast(document.body.classList.contains("light-mode")?"Light mode":"Dark mode")};
setDark(darkSaved);
$("boostBtn").onclick=()=>{level=MAX_LEVEL;sync();applyGain();toast("Maximum software level selected")};


function go(page){
 document.querySelectorAll(".page").forEach(x=>x.classList.remove("active"));$(page).classList.add("active");
 document.querySelectorAll(".nav button").forEach(x=>x.classList.toggle("active",x.dataset.page===page));
 if(page==="save")loadSavedAudio();scrollTo(0,0);
}
document.querySelector(".nav").addEventListener("click",e=>{
  const b=e.target.closest("button[data-page]");
  if(!b)return;
  e.preventDefault();
  go(b.dataset.page);
});

let dynamicsNode=null,videoSourceNode=null,videoGainNode=null,videoDynamicsNode=null;
async function setupAudio(){
 const C=window.AudioContext||window.webkitAudioContext;
 if(!C){return}
 try{
  if(!audioCtx)audioCtx=new C();
  if(!sourceNode){
   sourceNode=audioCtx.createMediaElementSource($("audio"));
   gainNode=audioCtx.createGain();
   dynamicsNode=audioCtx.createDynamicsCompressor();
   // Gentle compression after gain keeps boosted audio smoother while
   // allowing the level slider to make an audible difference.
   dynamicsNode.threshold.value=-8;
   dynamicsNode.knee.value=10;
   dynamicsNode.ratio.value=4;
   dynamicsNode.attack.value=0.004;
   dynamicsNode.release.value=0.18;
   sourceNode.connect(gainNode);
   gainNode.connect(dynamicsNode);
   dynamicsNode.connect(audioCtx.destination);
  }
  if(audioCtx.state==="suspended")await audioCtx.resume();
  applyGain();
 }catch(e){}
}
// Keep video on the browser's native media pipeline. Routing a video element
// through WebAudio can cause Android browsers to suspend its audio in background.
// Native media playback gives the browser the best chance to keep audio alive.
async function setupMediaElement(el){
 try{el.volume=1;el.muted=false;}catch(e){}
 // Route video audio through Web Audio so the same software booster also
 // affects videos opened from the Saved library. Keep the video element visible.
 const C=window.AudioContext||window.webkitAudioContext;
 if(!C)return;
 try{
  if(!audioCtx)audioCtx=new C();
  if(!videoSourceNode){
   videoSourceNode=audioCtx.createMediaElementSource(el);
   videoGainNode=audioCtx.createGain();
   videoDynamicsNode=audioCtx.createDynamicsCompressor();
   videoDynamicsNode.threshold.value=-8;
   videoDynamicsNode.knee.value=10;
   videoDynamicsNode.ratio.value=4;
   videoDynamicsNode.attack.value=0.004;
   videoDynamicsNode.release.value=0.18;
   videoSourceNode.connect(videoGainNode);
   videoGainNode.connect(videoDynamicsNode);
   videoDynamicsNode.connect(audioCtx.destination);
  }
  if(audioCtx.state==="suspended")await audioCtx.resume();
  applyGain();
 }catch(e){/* Native video playback remains available if Web Audio is unsupported. */}
}
function applyGain(){
 // 100 is normal; higher values increase software gain up to 12x.
 const target=level<=100 ? level/100 : Math.min(12,1+((level-100)/100));
 [gainNode,videoGainNode].forEach(node=>{
  if(!node)return;
  try{node.gain.cancelScheduledValues(audioCtx.currentTime);node.gain.setTargetAtTime(target,audioCtx.currentTime,0.06)}catch(e){node.gain.value=target}
 });
}


const SAVE_DB_NAME="FizzerSavedAudio";
const SAVE_DB_VERSION=2;
const SAVE_STORE="files";
let saveDB=null;

function openSaveDB(){
 return new Promise((resolve,reject)=>{
  if(saveDB){resolve(saveDB);return}
  if(!window.indexedDB){reject(new Error("IndexedDB unavailable"));return}
  const req=indexedDB.open(SAVE_DB_NAME,SAVE_DB_VERSION);
  req.onupgradeneeded=()=>{
   const db=req.result;
   if(!db.objectStoreNames.contains(SAVE_STORE)){
    const store=db.createObjectStore(SAVE_STORE,{keyPath:"key"});
    store.createIndex("created","created",{unique:false});
   }
  };
  req.onsuccess=()=>{saveDB=req.result;resolve(saveDB)};
  req.onerror=()=>reject(req.error||new Error("Database error"));
 });
}

async function requestPersistentStorage(){
 try{
  if(navigator.storage && navigator.storage.persist){
   await navigator.storage.persist();
  }
 }catch(e){}
}

function fileKey(file){
 return [file.name,file.size,file.lastModified||0,file.type].join("|");
}


function audioExtensionFor(type){
 if(type==="audio/wav")return ".wav";
 if(type==="audio/webm")return ".webm";
 if(type==="audio/ogg")return ".ogg";
 if(type==="audio/mp4"||type==="audio/m4a")return ".m4a";
 return ".audio";
}

function baseName(name){
 return (name||"fizzer-audio").replace(/\.[^.]+$/,"");
}

async function decodeToAudioBuffer(file){
 const C=window.AudioContext||window.webkitAudioContext;
 if(!C)throw new Error("Web Audio is unavailable");
 const ctx=new C();
 try{
  const data=await file.arrayBuffer();
  const input=await ctx.decodeAudioData(data.slice(0));
   const Offline=window.OfflineAudioContext||window.webkitOfflineAudioContext;
   if(!Offline)return input;
   const off=new Offline(input.numberOfChannels,input.length,input.sampleRate);
   const src=off.createBufferSource();src.buffer=input;
   const g=off.createGain();g.gain.value=Math.min(12,Math.max(0,level/100));
   const comp=off.createDynamicsCompressor();comp.threshold.value=-10;comp.knee.value=30;comp.ratio.value=10;comp.attack.value=.008;comp.release.value=.22;
   src.connect(g);g.connect(comp);comp.connect(off.destination);src.start();
   return await off.startRendering();
 }finally{
  try{await ctx.close()}catch(e){}
 }
}

function audioBufferToWavBlob(buffer){
 const channels=buffer.numberOfChannels;
 const sampleRate=buffer.sampleRate;
 const frames=buffer.length;
 const bytesPerSample=2;
 const blockAlign=channels*bytesPerSample;
 const dataSize=frames*blockAlign;
 const out=new ArrayBuffer(44+dataSize);
 const view=new DataView(out);
 const write=(o,str)=>{for(let i=0;i<str.length;i++)view.setUint8(o+i,str.charCodeAt(i))};
 write(0,"RIFF");view.setUint32(4,36+dataSize,true);write(8,"WAVE");
 write(12,"fmt ");view.setUint32(16,16,true);view.setUint16(20,1,true);
 view.setUint16(22,channels,true);view.setUint32(24,sampleRate,true);
 view.setUint32(28,sampleRate*blockAlign,true);view.setUint16(32,blockAlign,true);
 view.setUint16(34,16,true);write(36,"data");view.setUint32(40,dataSize,true);
 let pos=44;
 for(let i=0;i<frames;i++){
  for(let ch=0;ch<channels;ch++){
   let v=buffer.getChannelData(ch)[i];
   v=Math.max(-1,Math.min(1,v));
   view.setInt16(pos,v<0?v*0x8000:v*0x7fff,true);pos+=2;
  }
 }
 return new Blob([out],{type:"audio/wav"});
}

async function recordAudioWithMime(file,mime,extension){
 const C=window.AudioContext||window.webkitAudioContext;
 if(!C)throw new Error("Web Audio is unavailable");
 const ctx=new C();
 const el=new Audio();
 const url=URL.createObjectURL(file);
 el.src=url;el.preload="auto";
 await new Promise((resolve,reject)=>{el.onloadedmetadata=resolve;el.onerror=()=>reject(new Error("Could not read media"))});
 const source=ctx.createMediaElementSource(el);
 const gain=ctx.createGain();gain.gain.value=Math.min(16,Math.max(0,level/100));
 const comp=ctx.createDynamicsCompressor();comp.threshold.value=-10;comp.knee.value=30;comp.ratio.value=10;comp.attack.value=.008;comp.release.value=.22;
 const dest=ctx.createMediaStreamDestination();
 source.connect(gain);gain.connect(comp);comp.connect(dest);
 const rec=new MediaRecorder(dest.stream,{mimeType:mime});
 const chunks=[];
 const done=new Promise((resolve,reject)=>{
  rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
  rec.onstop=()=>resolve(new Blob(chunks,{type:mime}));
  rec.onerror=e=>reject(e.error||new Error("Recording failed"));
 });
 rec.start(1000);
 await el.play();
 await new Promise(resolve=>el.onended=resolve);
 rec.stop();
 const blob=await done;
 URL.revokeObjectURL(url);
 try{await ctx.close()}catch(e){}
 return {blob,name:baseName(file.name)+extension,type:mime};
}

async function recordVideoWithGain(file){
 const C=window.AudioContext||window.webkitAudioContext;
 if(!C||!window.MediaRecorder)throw new Error("Video editing export is not supported by this browser");
 const probe=document.createElement("video");
 const url=URL.createObjectURL(file);probe.src=url;probe.preload="auto";probe.muted=false;probe.volume=1;probe.playsInline=true;
 try{
  await new Promise((resolve,reject)=>{probe.onloadedmetadata=resolve;probe.onerror=()=>reject(new Error("Could not read video"))});
  const capture=probe.captureStream||probe.mozCaptureStream;
  if(!capture)throw new Error("This browser cannot export edited video; use Download Audio for enhanced sound");
  const videoStream=capture.call(probe);
  const videoTracks=videoStream.getVideoTracks();
  if(!videoTracks.length)throw new Error("Video track unavailable");
  const ctx=new C();
  const source=ctx.createMediaElementSource(probe),gain=ctx.createGain(),comp=ctx.createDynamicsCompressor(),dest=ctx.createMediaStreamDestination();
  gain.gain.value=Math.min(16,Math.max(0,level/100));
  comp.threshold.value=-10;comp.knee.value=30;comp.ratio.value=10;comp.attack.value=.008;comp.release.value=.22;
  source.connect(gain);gain.connect(comp);comp.connect(dest);
  const tracks=[...videoTracks,...dest.stream.getAudioTracks()];
  const stream=new MediaStream(tracks);
  const mime=["video/webm;codecs=vp9,opus","video/webm;codecs=vp8,opus","video/webm"].find(x=>MediaRecorder.isTypeSupported(x));
  if(!mime)throw new Error("Edited video export is not supported by this browser");
  const rec=new MediaRecorder(stream,{mimeType:mime, videoBitsPerSecond:450000, audioBitsPerSecond:96000});const chunks=[];
  const done=new Promise((resolve,reject)=>{rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};rec.onstop=()=>resolve(new Blob(chunks,{type:mime}));rec.onerror=e=>reject(e.error||new Error("Video export failed"))});
  await ctx.resume();rec.start(1000);await probe.play();
  await new Promise(resolve=>{probe.onended=resolve});
  if(rec.state!=="inactive")rec.stop();
  const blob=await done;
  tracks.forEach(t=>t.stop());try{await ctx.close()}catch(e){}
  return {blob,name:baseName(file.name)+"-enhanced.webm",type:mime};
 }finally{probe.pause();probe.removeAttribute("src");probe.load();URL.revokeObjectURL(url)}
}

async function makeAudioBlob(file,format){
 if(format==="mp4"){
  const isMp4=file.type==="video/mp4" || /\.mp4$/i.test(file.name||"");
  if(!isMp4)throw new Error("MP4 download is available only for an MP4 source file");
  return {blob:file,name:file.name,type:file.type||"video/mp4"};
 }
 if(format==="original" && file.type.startsWith("audio/")){
  return {blob:file,name:file.name,type:file.type};
 }
 if(format==="wav"){
  const buffer=await decodeToAudioBuffer(file);
  return {blob:audioBufferToWavBlob(buffer),name:baseName(file.name)+".wav",type:"audio/wav"};
 }
 const candidates={
  webm:[["audio/webm;codecs=opus",".webm"],["audio/webm",".webm"]],
  ogg:[["audio/ogg;codecs=opus",".ogg"],["audio/ogg",".ogg"]],
  m4a:[["audio/mp4;codecs=mp4a.40.2",".m4a"],["audio/mp4",".m4a"]]
 };
 const list=candidates[format];
 if(!list)throw new Error("Choose a supported audio format");
 if(!window.MediaRecorder)throw new Error("Audio recording is not supported by this browser");
 for(const pair of list){
  if(MediaRecorder.isTypeSupported(pair[0])){
   return await recordAudioWithMime(file,pair[0],pair[1]);
  }
 }
 throw new Error(format.toUpperCase()+" audio is not supported by this browser");
}

function triggerDownload(blob,name){
 const url=URL.createObjectURL(blob);
 const a=document.createElement("a");
 a.href=url;a.download=name;
 document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),3000);
}

async function saveAudioFile(file){
 if(!file || !(file.type.startsWith("audio/") || file.type.startsWith("video/"))) throw new Error("Choose an audio or video file");
 await requestPersistentStorage();
 const db=await openSaveDB();
 return new Promise((resolve,reject)=>{
  const tx=db.transaction(SAVE_STORE,"readwrite");
  tx.objectStore(SAVE_STORE).put({
   key:fileKey(file),
   name:file.name,
   type:file.type,
   size:file.size,
   lastModified:file.lastModified||0,
   created:Date.now(),
   blob:new Blob([file],{type:file.type||"application/octet-stream"})
  });
  tx.oncomplete=()=>resolve(true);
  tx.onerror=()=>reject(tx.error||new Error("Could not save"));
  tx.onabort=()=>reject(tx.error||new Error("Save was cancelled by browser storage"));
 });
}

async function getSavedAudio(){
 const db=await openSaveDB();
 return new Promise((resolve,reject)=>{
  const req=db.transaction(SAVE_STORE,"readonly").objectStore(SAVE_STORE).getAll();
  req.onsuccess=()=>resolve((req.result||[]).sort((a,b)=>a.created-b.created));
  req.onerror=()=>reject(req.error);
 });
}

async function loadSavedAudio(){
 const list=$("savedList");
 if(!list)return;
 try{
  const rows=await getSavedAudio();
  $("savedCount").textContent=rows.length+" saved";
  $("emptySaved").style.display=rows.length?"none":"block";
  list.innerHTML="";
  rows.forEach(row=>{
   const item=document.createElement("div");
   item.className="savedItem";
   const icon=document.createElement("div");
   icon.className="savedPlayIcon";
   icon.textContent="▶";
   const info=document.createElement("div");
   info.style.minWidth="0";
   const name=document.createElement("div");
   name.className="fileName";
   name.textContent=row.name;
   const meta=document.createElement("div");
   meta.className="fileMeta";
   meta.textContent=fmt(row.size)+" • Saved on this device";
   info.append(name,meta);

   const actions=document.createElement("div");
   actions.className="savedActions";

   const play=document.createElement("button");
   play.className="miniBtn primary";
   play.textContent="Play";
   play.onclick=(ev)=>{ev.stopPropagation();playSaved(row)};

   const download=document.createElement("button");
   download.className="miniBtn";
   download.textContent="Download";
   download.onclick=(ev)=>{ev.stopPropagation();downloadSaved(row)};

   const del=document.createElement("button");
   del.className="miniBtn";
   del.textContent="Delete";
   del.onclick=(ev)=>{ev.stopPropagation();deleteSaved(row.key)};

   actions.append(play,download,del);
   item.append(icon,info,actions);
   item.onclick=()=>playSaved(row);
   list.appendChild(item);
  });
 }catch(e){
  $("savedCount").textContent="0 saved";
  $("emptySaved").style.display="block";
 }
}

function playSaved(row){
 const file=new File([row.blob],row.name,{type:row.type,lastModified:row.lastModified||Date.now()});
 queue=[file];
 current=0;
 renderQueue();
 loadCurrent(true);
 go("player");
}

function downloadSaved(row){
 const url=URL.createObjectURL(row.blob);
 const a=document.createElement("a");
 a.href=url;
 a.download=row.name||"fizzer-audio";
 document.body.appendChild(a);
 a.click();
 a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1500);
}

async function deleteSaved(key){
 try{
  const db=await openSaveDB();
  const tx=db.transaction(SAVE_STORE,"readwrite");
  tx.objectStore(SAVE_STORE).delete(key);
  tx.oncomplete=()=>{loadSavedAudio();toast("Saved audio deleted");};
 }catch(e){}
}

async function deleteAllSaved(){
 try{
  const db=await openSaveDB();
  const tx=db.transaction(SAVE_STORE,"readwrite");
  tx.objectStore(SAVE_STORE).clear();
  tx.oncomplete=()=>{loadSavedAudio();toast("Saved audio cleared");};
 }catch(e){}
}

function fmt(n){if(n<1024)return n+" B";let u=["KB","MB","GB"],i=-1;do{n/=1024;i++}while(n>=1024&&i<u.length-1);return n.toFixed(n<10?1:0)+" "+u[i]}
function safe(s){return s.replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]))}
function renderQueue(){
 $("queue").innerHTML="";
 queue.forEach((f,i)=>{const d=document.createElement("div");d.className="fileItem";d.innerHTML='<div class="fileIcon">'+(f.type.startsWith("video")?"▣":"♪")+'</div><div><div class="fileName">'+safe(f.name)+'</div><div class="fileMeta">'+fmt(f.size)+(i===current?" • PLAYING":"")+'</div></div><button class="remove" data-i="'+i+'">×</button>';$("queue").appendChild(d)});
 document.querySelectorAll(".remove").forEach(b=>b.onclick=()=>{queue.splice(Number(b.dataset.i),1);if(current>=queue.length)current=Math.max(0,queue.length-1);renderQueue()});
}
async function addFiles(files){
 const a=[...files];if(!a.length)return;
 const videos=a.filter(isVideoFile);
 if(videos.length){const mode=await chooseVideoMode();if(mode==="audio")videos.forEach(f=>audioOnlyFiles.add(f));}
 const wasEmpty=!queue.length;queue.push(...a);renderQueue();
 if(wasEmpty){current=0;loadCurrent(true)}
 toast(a.length+" file"+(a.length>1?"s":"")+" added");
}
$("chooseFilesBtn").onclick=()=>$("fileInput").click();
$("fileInput").onchange=e=>{addFiles(e.target.files);e.target.value=""};
function updateDownloadFormatForCurrent(){
 const f=queue[current], sel=$("downloadFormat");
 if(!f||!sel){$("downloadVideoBtn").style.display="none";$("saveAudioBtn").style.display="none";return}
 const isVideo=f.type.startsWith("video/")||/\.(mp4|webm|mov|m4v|ogv)$/i.test(f.name||"");
 $("downloadVideoBtn").style.display=isVideo?"block":"none";
 $("saveAudioBtn").style.display=isVideo?"block":"none";
 const original=sel.querySelector('option[value="original"]');
 const wav=sel.querySelector('option[value="wav"]');
 if(original)original.disabled=isVideo;
 if(wav)wav.disabled=isVideo;
 if(isVideo && (sel.value==="original"||sel.value==="wav"))sel.value="webm";
 if(!isVideo && wav)wav.disabled=false;
}
function updateDownloadFormatSupport(){
 const checks={
  webm:["audio/webm;codecs=opus","audio/webm"],
  ogg:["audio/ogg;codecs=opus","audio/ogg"],
  m4a:["audio/mp4;codecs=mp4a.40.2","audio/mp4"]
 };
 Object.keys(checks).forEach(v=>{
  const opt=$("downloadFormat").querySelector('option[value="'+v+'"]');
  if(!opt)return;
  opt.disabled=!(window.MediaRecorder && checks[v].some(m=>MediaRecorder.isTypeSupported(m)));
 });
}


const up=$("upload");["dragenter","dragover"].forEach(x=>up.addEventListener(x,e=>{e.preventDefault();up.classList.add("drag")}));["dragleave","drop"].forEach(x=>up.addEventListener(x,e=>{e.preventDefault();up.classList.remove("drag")}));up.addEventListener("drop",e=>addFiles(e.dataTransfer.files));

function loadCurrent(auto){
 updateDownloadFormatForCurrent();
 const a=$("audio"),v=$("videoPlayer");
 if(!queue.length){a.pause();v.pause();a.removeAttribute("src");v.removeAttribute("src");a.load();v.load();a.style.display="block";v.style.display="none";return}
 const f=queue[current],u=URL.createObjectURL(f);objectUrls.push(u);
 $("progress").style.width="0%";
 const isVideo=isVideoFile(f) && !audioOnlyFiles.has(f);
 if(isVideo){a.pause();a.removeAttribute("src");a.load();a.style.display="none";v.style.display="block";v.src=u;v.volume=1;v.muted=false;v.playsInline=true;v.setAttribute("playsinline","");v.setAttribute("webkit-playsinline","");v.disablePictureInPicture=true;v.setAttribute("disablepictureinpicture","");v.playbackRate=Number($("speed").value);setupMediaElement(v).then(()=>{if(auto)v.play().catch(()=>{})});}
 else{v.pause();v.removeAttribute("src");v.load();v.style.display="none";a.style.display="block";a.src=u;a.playbackRate=Number($("speed").value);setupAudio().then(()=>{if(auto)a.play().catch(()=>{})});}
 renderQueue();
 if("mediaSession" in navigator){
  try{navigator.mediaSession.playbackState="none";}catch(e){}
  try{if("MediaMetadata" in window)navigator.mediaSession.metadata=new MediaMetadata({title:f.name,artist:"Fizzer",album:"Fizzer Player"});}catch(e){}
 }
}
$("audio").addEventListener("play",setupAudio);$("videoPlayer").addEventListener("play",()=>setupMediaElement($("videoPlayer")));
$("audio").addEventListener("ended",()=>{if(!queue.length)return;if(current<queue.length-1){current++;loadCurrent(true)}else if(repeatAll){current=0;loadCurrent(true)}});
$("videoPlayer").addEventListener("ended",()=>{if(!queue.length)return;if(current<queue.length-1){current++;loadCurrent(true)}else if(repeatAll){current=0;loadCurrent(true)}});
let progressFrame=0;
function activeProgressMedia(){
 const v=$("videoPlayer");
 return v.style.display!=="none"?v:$("audio");
}
function updatePlaybackProgress(){
 const m=activeProgressMedia(),bar=$("progress");
 const d=m.duration,t=m.currentTime;
 const pct=Number.isFinite(d)&&d>0&&Number.isFinite(t)?Math.max(0,Math.min(100,(t/d)*100)):0;
 bar.style.width=pct+"%";
 if(m.ended){bar.style.width="100%";return}
 if(!m.paused&&!m.ended)progressFrame=requestAnimationFrame(updatePlaybackProgress);
 else if(progressFrame){cancelAnimationFrame(progressFrame);progressFrame=0}
}
["audio","videoPlayer"].forEach(id=>{
 const m=$(id);
 ["timeupdate","loadedmetadata","durationchange","seeking","seeked","play","playing","pause","ended","ratechange","emptied"].forEach(ev=>m.addEventListener(ev,updatePlaybackProgress));
});
$("progress").addEventListener("click",e=>{
 const m=activeProgressMedia(),d=m.duration,r=e.currentTarget.getBoundingClientRect();
 if(Number.isFinite(d)&&d>0){m.currentTime=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))*d;updatePlaybackProgress()}
});
updatePlaybackProgress();
$("prevBtn").onclick=()=>{if(!queue.length)return;current=(current-1+queue.length)%queue.length;loadCurrent(true)};
$("nextBtn").onclick=()=>{if(!queue.length)return;current=(current+1)%queue.length;loadCurrent(true)};
$("repeatBtn").onclick=()=>{repeatAll=!repeatAll;$("repeatBtn").textContent="Repeat: "+(repeatAll?"ON":"OFF");localStorage.setItem("fizzer_repeat",repeatAll?"1":"0")};
$("speed").onchange=()=>{$("audio").playbackRate=Number($("speed").value);$("videoPlayer").playbackRate=Number($("speed").value)};

async function saveCurrentToLibrary(){
 if(!queue.length || !queue[current]){toast("Select an audio or video file first");return}
 const btn=$("saveCurrentBtn");btn.disabled=true;btn.textContent="Saving…";
 try{
  const f=queue[current];
  let saved;
  if(f.type.startsWith("video/") || /\.(mp4|webm|mov|m4v|ogv)$/i.test(f.name||"")){
   if(audioOnlyFiles.has(f)){
    // Audio playback mode must save an audio file, not the original video.
    const result=await recordAudioWithMime(f,"audio/webm;codecs=opus",".webm");
    saved=new File([result.blob],(f.name||"video").replace(/\.[^.]+$/,"" )+".webm",{type:"audio/webm",lastModified:Date.now()});
   }else{
    saved=new File([f],f.name,{type:f.type||"video/mp4",lastModified:f.lastModified||Date.now()});
   }
  }else{
   // Save the original audio file directly; avoid a full decode/re-encode pass.
   saved=new File([f],f.name,{type:f.type||"application/octet-stream",lastModified:f.lastModified||Date.now()});
  }
  await saveAudioFile(saved);
  await loadSavedAudio();
  toast(saved.type.startsWith("video/")?"Video saved in Save":"Audio saved in Save");
 }catch(e){toast(e.message||"Could not save this media")}
 finally{btn.disabled=false;btn.textContent="Save Media";}
}
async function saveExtractedAudio(){
 if(!queue.length || !queue[current]){toast("Select a video first");return}
 const btn=$("saveAudioBtn");btn.disabled=true;btn.textContent="Extracting…";
 try{
  const f=queue[current];
  if(!(f.type.startsWith("video/") || /\.(mp4|webm|mov|m4v|ogv)$/i.test(f.name||"")))throw new Error("Select a video to extract audio");
  const result=await recordAudioWithMime(f,"audio/webm;codecs=opus",".webm");
  const saved=new File([result.blob],result.name,{type:"audio/webm",lastModified:Date.now()});
  await saveAudioFile(saved);await loadSavedAudio();toast("Extracted audio saved in Save");
 }catch(e){toast(e.message||"Audio extraction failed")}
 finally{btn.disabled=false;btn.textContent="Save Audio";}
}
async function downloadCurrentAudio(){
 if(!queue.length || !queue[current]){toast("Select an audio or video file first");return}
 const btn=$("downloadCurrentBtn");btn.disabled=true;btn.textContent="Preparing…";
 try{
  const f=queue[current];
  const format=$("downloadFormat").value;
  const result=await makeAudioBlob(f,format);
  triggerDownload(result.blob,result.name);
  toast("Audio download started");
 }catch(e){
  toast(e.message||"Audio conversion failed");
 }finally{
  btn.disabled=false;btn.textContent="Download Audio";
 }
}

$("saveCurrentBtn").onclick=saveCurrentToLibrary;
$("saveAudioBtn").onclick=saveExtractedAudio;
$("downloadVideoBtn").onclick=async()=>{
 if(!queue.length||!queue[current]){toast("Select a video first");return}
 const f=queue[current];
 if(!(f.type.startsWith("video/")||/\.(mp4|webm|mov|m4v|ogv)$/i.test(f.name||""))){toast("Select a video first");return}
 const btn=$("downloadVideoBtn");btn.disabled=true;btn.textContent="Preparing…";
 try{const result=await recordVideoWithGain(f);triggerDownload(result.blob,result.name);toast("Enhanced video download started");}
 catch(e){toast(e.message||"Edited video export failed");}
 finally{btn.disabled=false;btn.textContent="Download Video";}
};
$("downloadCurrentBtn").onclick=downloadCurrentAudio;
$("downloadFormat").onchange=()=>{
 const f=queue[current];
 const value=$("downloadFormat").value;
 const isVideo=!!f && (f.type.startsWith("video/") || /\.(mp4|webm|mov|m4v|ogv)$/i.test(f.name||""));
 if(isVideo && (value==="original"||value==="wav")){
  $("downloadFormat").value="webm";
  toast("Video audio extraction uses WebM audio format");
 }
};

$("clearBtn").onclick=()=>{
 const a=$("audio");
 a.pause();
 a.currentTime=0;
 a.removeAttribute("src");
 a.load();
 objectUrls.forEach(u=>URL.revokeObjectURL(u)); objectUrls=[];
 queue=[]; current=0;
 $("progress").style.width="0%";
 renderQueue();
 if("mediaSession" in navigator){
  navigator.mediaSession.playbackState="none";
  navigator.mediaSession.metadata=null;
 }
 toast("All files cleared — playback stopped");
};


function activeMediaElement(){return $("videoPlayer").style.display!=="none"?$("videoPlayer"):$(("audio"));}
function setupMediaSession(){
 if(!("mediaSession" in navigator))return;
 const media=()=>activeMediaElement();
 try{navigator.mediaSession.setActionHandler("play",()=>media().play());}catch(e){}
 try{navigator.mediaSession.setActionHandler("pause",()=>media().pause());}catch(e){}
 try{navigator.mediaSession.setActionHandler("nexttrack",()=>{if(queue.length){current=(current+1)%queue.length;loadCurrent(true)}});}catch(e){}
 try{navigator.mediaSession.setActionHandler("previoustrack",()=>{if(queue.length){current=(current-1+queue.length)%queue.length;loadCurrent(true)}});}catch(e){}
 try{navigator.mediaSession.setActionHandler("seekbackward",()=>{const m=media();m.currentTime=Math.max(0,m.currentTime-10)});}catch(e){}
 try{navigator.mediaSession.setActionHandler("seekforward",()=>{const m=media();m.currentTime=Math.min(m.duration||Infinity,m.currentTime+10)});}catch(e){}
}
function updateMediaSession(){
 if(!("mediaSession" in navigator))return;
 const m=activeMediaElement();
 try{navigator.mediaSession.playbackState=m.paused?"paused":"playing";}catch(e){}
 if(queue.length&&"MediaMetadata" in window){const f=queue[current];try{navigator.mediaSession.metadata=new MediaMetadata({title:f.name,artist:"Fizzer",album:"Fizzer Player"});}catch(e){}}
 updateMediaPosition();
}
function updateMediaPosition(){
 if(!("mediaSession" in navigator)||!navigator.mediaSession.setPositionState)return;
 const m=activeMediaElement();
 if(!Number.isFinite(m.duration)||m.duration<=0)return;
 try{navigator.mediaSession.setPositionState({duration:m.duration,playbackRate:m.playbackRate||1,position:Math.min(m.currentTime||0,m.duration)});}catch(e){}
}
$("audio").addEventListener("play",updateMediaSession);$("audio").addEventListener("pause",updateMediaSession);$("audio").addEventListener("ended",updateMediaSession);
$("videoPlayer").addEventListener("play",updateMediaSession);$("videoPlayer").addEventListener("pause",updateMediaSession);$("videoPlayer").addEventListener("ended",updateMediaSession);
$("audio").addEventListener("timeupdate",updateMediaPosition);$("audio").addEventListener("durationchange",updateMediaPosition);
$("videoPlayer").addEventListener("timeupdate",updateMediaPosition);$("videoPlayer").addEventListener("durationchange",updateMediaPosition);
setupMediaSession();

document.addEventListener("visibilitychange",()=>{
 lastVisibility=Date.now();
 // Do not pause or replace the active media when the page is backgrounded.
 // Android/Chrome decides whether background video audio is permitted.
 if(document.visibilityState==="visible"){
  const m=activeMediaElement();
  if(!m.paused)updateMediaSession();
 }
});

$("clearSavedBtn").onclick=deleteAllSaved;
$("repeatBtn").textContent="Repeat: "+(repeatAll?"ON":"OFF");
$("accentSelect").value=localStorage.getItem("fizzer_accent")||"gold";
setAccent($("accentSelect").value);
requestPersistentStorage();
loadSavedAudio();
$("accentSelect").addEventListener("change",e=>{
  setAccent(e.target.value);
  toast("Accent colour changed");
});
sync();syncTrial();syncTrial2();loadSavedAudio();updateDownloadFormatSupport();
if("serviceWorker" in navigator){
  navigator.serviceWorker.register("/sw.js?v=23",{updateViaCache:"none"}).then(r=>r.update()).catch(()=>{});
}
let deferredInstall=null;
const gate=$("installGate"), gateHint=$("gateHint"), gateInstall=$("gateInstall"), gateCancel=$("gateCancel"), fizzerApp=$("fizzerApp");
const INSTALLED_MARKER="fizzer_app_installed_v1";
function isInstalled(){
 try{return window.matchMedia("(display-mode: standalone)").matches||window.navigator.standalone===true||localStorage.getItem(INSTALLED_MARKER)==="yes";}
 catch(e){return window.matchMedia("(display-mode: standalone)").matches||window.navigator.standalone===true;}
}
function showApp(){gate.hidden=true;fizzerApp.hidden=false;}
function showOpen(){
 try{localStorage.setItem(INSTALLED_MARKER,"yes");}catch(e){}
 // Once the browser confirms installation, never leave the install gate visible.
 showApp();
}
if(isInstalled())showApp();
window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();deferredInstall=e;});
window.addEventListener("appinstalled",()=>{deferredInstall=null;showOpen();});
// Cancel always means: skip installation and use the web app.
gateCancel.onclick=showApp;
gateInstall.onclick=async()=>{
 if(isInstalled()){showApp();return;}
 if(!deferredInstall){
  gateHint.textContent="To install, open your browser menu and choose ‘Install app’ or ‘Add to Home screen’. You can tap Cancel to use Fizzer on the web.";
  return;
 }
 const promptEvent=deferredInstall;deferredInstall=null;
 gateInstall.disabled=true;gateInstall.textContent="Opening…";
 try{
  await promptEvent.prompt();
  const choice=await promptEvent.userChoice;
  if(choice&&choice.outcome==="accepted"){
   gateHint.textContent="Installation is in progress. This page will show Open when your browser confirms the installation.";
   gateInstall.textContent="Installing…";
  }else{
   gateHint.textContent="Installation was not completed. You can try again from the browser menu, or tap Cancel to use Fizzer on the web.";
   gateInstall.textContent="Install";gateInstall.disabled=false;
  }
 }catch(err){
  gateHint.textContent="Your browser could not start installation. Use its menu and choose ‘Install app’ or ‘Add to Home screen’, or tap Cancel to continue on the web.";
  gateInstall.textContent="Install";gateInstall.disabled=false;
 }
};
const ib=$("installBtn");
if(ib)ib.onclick=async()=>{if(!deferredInstall){toast("Use browser menu → Install app");return;}const p=deferredInstall;deferredInstall=null;await p.prompt();await p.userChoice;ib.style.display="none";};

// Direct-link downloader: streams through Flask so the UI can show byte progress.
function formatDownloadBytes(n){
 if(!Number.isFinite(n))return "Unknown size";
 if(n<1024)return Math.round(n)+" B";
 const units=["KB","MB","GB","TB"];let i=-1;
 do{n/=1024;i++}while(n>=1024&&i<units.length-1);
 return n.toFixed(n<10?1:0)+" "+units[i];
}
function setLinkDownloadProgress(show,status,percent,loaded,total,speed){
 const box=$("linkDownloadProgress");box.classList.toggle("show",show);
 $("linkDownloadStatus").textContent=status;
 $("linkDownloadPercent").textContent=percent===null?"—":Math.round(percent)+"%";
 $("linkDownloadBar").style.width=percent===null?"100%":Math.max(0,Math.min(100,percent))+"%";
 $("linkDownloadBytes").textContent=formatDownloadBytes(loaded)+" / "+(total?formatDownloadBytes(total):"Unknown size");
 $("linkDownloadSpeed").textContent=speed||"";
}
let checkedDownloadUrl="";
let formatsLoaded=false;
const linkDownloadBtn=$("linkDownloadBtn");
function clearLinkPreview(){
 checkedDownloadUrl="";formatsLoaded=false;
 linkDownloadBtn.textContent="Download";
 const preview=$("linkPreview");preview.classList.remove("show");
 $("linkPreviewThumb").style.display="none";$("linkPreviewThumb").removeAttribute("src");
 $("linkFormatSelect").innerHTML="<option value=\"best\">Best available quality</option>";
 $("linkCheckResult").style.display="none";$("linkCheckResult").textContent="";
}
function showLinkPreview(data,url){
 checkedDownloadUrl=url;formatsLoaded=true;
 const preview=$("linkPreview"),thumb=$("linkPreviewThumb");
 $("linkPreviewTitle").textContent=data.title||"Direct media file";
 const meta=[];if(data.duration)meta.push("Duration: "+data.duration);if(data.ext)meta.push(String(data.ext).toUpperCase());
 $("linkPreviewMeta").textContent=meta.join(" • ")||"Media details found";
 if(data.thumbnail&&/^https:\/\//i.test(data.thumbnail)){thumb.src=data.thumbnail;thumb.style.display="block";thumb.onerror=()=>{thumb.style.display="none";};}
 const select=$("linkFormatSelect");select.innerHTML="";
 const best=document.createElement("option");best.value="best";best.textContent="Best available quality";select.appendChild(best);
 (data.formats||[]).forEach(f=>{if(!f.format_id)return;const o=document.createElement("option");o.value=String(f.format_id);const bits=[];if(f.height)bits.push(f.height+"p");if(f.ext)bits.push(String(f.ext).toUpperCase());if(f.filesize)bits.push(formatDownloadBytes(f.filesize));if(f.format_note&&!f.height)bits.push(f.format_note);o.textContent=bits.join(" • ")||("Format "+f.format_id);select.appendChild(o);});
 preview.classList.add("show");
 linkDownloadBtn.textContent="Download selected format";
}
$("linkDownloadUrl").addEventListener("input",clearLinkPreview);
$("linkDownloadBtn").addEventListener("click",async()=>{
 const input=$("linkDownloadUrl"),btn=$("linkDownloadBtn"),url=input.value.trim();
 if(!url){toast("Paste a media link first");input.focus();return}
 try{const parsed=new URL(url);if(!["http:","https:"].includes(parsed.protocol))throw new Error("Enter a valid HTTP/HTTPS link.");}
 catch(e){toast("Enter a valid public HTTP/HTTPS link.");return}
 btn.disabled=true;
 if(!formatsLoaded||checkedDownloadUrl!==url){
  btn.textContent="Checking…";setLinkDownloadProgress(true,"Checking link and finding formats…",null,0,0,"");
  try{
   const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),22000);
   let r;try{r=await fetch("/check-link",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url}),signal:controller.signal});}finally{clearTimeout(timer)}
   const data=await r.json();
   if(!r.ok)throw new Error(data.error||"Could not check this link.");
   if(data.supported){showLinkPreview(data,url);setLinkDownloadProgress(false,"",null,0,0,"");btn.disabled=false;toast("Formats ready. Choose a quality, then tap Download.");return;}
   const host=new URL(url).hostname.toLowerCase().replace(/^www\./,"");
   const socialHosts=["youtube.com","youtu.be","facebook.com","fb.watch","tiktok.com","twitter.com","x.com","instagram.com","threads.net","reddit.com","vimeo.com","dailymotion.com","pinterest.com","snapchat.com"];
   if(socialHosts.some(d=>host===d||host.endsWith("."+d)))throw new Error(data.message||"This platform link could not be accessed by the server.");
   // Direct-file checks may return a non-preview message; continue to the download endpoint.
   formatsLoaded=true;checkedDownloadUrl=url;
  }catch(e){setLinkDownloadProgress(true,"Link check failed",null,0,0,"");$("linkDownloadStatus").textContent=e.name==="AbortError"?"Link check timed out. The hosting server may be blocking this platform.":(e.message||"Could not check this link.");btn.disabled=false;btn.textContent="Download";return;}
 }
 const selectedFormat=$("linkFormatSelect").value||"best";
 btn.textContent="Preparing…";setLinkDownloadProgress(true,"Starting download…",null,0,0,"");
 let usedUniversal=false;
 try{
  // First try the universal public-media engine. It covers many sites through
  // yt-dlp and gives us real server-side progress. If unavailable, fall back to
  // the existing direct-file streamer.
  const prep=await fetch("/prepare-download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,quality:selectedFormat,output_format:$("linkOutputFormat").value})});
  const host=new URL(url).hostname.toLowerCase().replace(/^www\./,"");
  const socialHosts=["youtube.com","youtu.be","facebook.com","fb.watch","tiktok.com","twitter.com","x.com","instagram.com","threads.net","reddit.com","vimeo.com","dailymotion.com","pinterest.com","snapchat.com"];
  const isSocialPage=socialHosts.some(d=>host===d||host.endsWith("."+d));
  if(!prep.ok && isSocialPage){
   let message="This social-media page could not be prepared for download.";
   try{const data=await prep.json();message=data.error||message}catch(e){}
   setLinkDownloadProgress(true,"Download unavailable",null,0,0,"");
   $("linkDownloadStatus").textContent=message;
   toast(message);
   btn.disabled=false;btn.textContent="Download";
   return;
  }
  if(prep.ok){
   const pj=await prep.json();usedUniversal=true;
   let job=pj.job_id, status;const pollStarted=Date.now();
   while(job){
    if(Date.now()-pollStarted>90000)throw new Error("The server could not start the download within 90 seconds. This can happen when the hosting server blocks the media platform.");
    await new Promise(r=>setTimeout(r,650));
    const sr=await fetch("/download-job/"+encodeURIComponent(job)+"/status");
    status=await sr.json();
    if(status.status==="error")throw new Error(status.message||"Universal downloader failed");
    const sp=status.speed?formatDownloadBytes(status.speed)+"/s":"";
    setLinkDownloadProgress(true,status.message||"Preparing…",status.percent==null?null:status.percent,status.downloaded||0,status.total||0,sp);
    if(status.status==="ready"){
      const a=document.createElement("a");a.href="/download-job/"+encodeURIComponent(job);a.download="";document.body.appendChild(a);a.click();a.remove();
      setLinkDownloadProgress(true,"Download ready",100,status.downloaded||status.total||0,status.total||status.downloaded||0,"");toast("Download ready");break;
    }
   }
   if(usedUniversal)return;
  }
 }catch(e){
  if(usedUniversal)throw e;
  // If yt-dlp is unavailable or cannot handle the URL, continue to the direct-file path.
 }
 // Direct public file fallback.
 setLinkDownloadProgress(true,"Connecting…",null,0,0,"");
 const started=Date.now();
 try{
  const response=await fetch("/download-from-link",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url})});
  if(response.status===202){throw new Error("This page needs the universal downloader engine, which is not available on this server.")}
  if(!response.ok){let message="Download failed";try{const data=await response.json();message=data.error||message}catch(e){}throw new Error(message)}
  const total=Number(response.headers.get("Content-Length"))||0,disposition=response.headers.get("Content-Disposition")||"";
  let filename="fizzer-download";const utf=disposition.match(/filename\*=UTF-8''([^;]+)/i),plain=disposition.match(/filename="?([^";]+)"?/i);
  if(utf){try{filename=decodeURIComponent(utf[1])}catch(e){filename=utf[1]}}else if(plain)filename=plain[1];
  const reader=response.body.getReader(),chunks=[];let loaded=0,last=0,lastTime=started;
  while(true){const {done,value}=await reader.read();if(done)break;chunks.push(value);loaded+=value.byteLength;const now=Date.now(),elapsed=Math.max(.001,(now-lastTime)/1000),speed=(loaded-last)/elapsed;last=loaded;lastTime=now;setLinkDownloadProgress(true,"Downloading…",total?loaded/total*100:null,loaded,total,formatDownloadBytes(speed)+"/s")}
  const blob=new Blob(chunks,{type:response.headers.get("Content-Type")||"application/octet-stream"}),objectUrl=URL.createObjectURL(blob),a=document.createElement("a");a.href=objectUrl;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(objectUrl),60000);setLinkDownloadProgress(true,"Download ready",100,loaded,total,"");toast("Download ready");
 }catch(e){setLinkDownloadProgress(true,"Download failed",null,0,0,"");$("linkDownloadStatus").textContent=e.message||"Could not download this link";toast(e.message||"Download failed")}
 finally{btn.disabled=false;btn.textContent="Download"}
});
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(
        PAGE,
        app_name=APP_NAME,
        version=APP_VERSION
    )


TRIAL_VIDEO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "2e97dc2e9b5cd5b571e3758718398f88.mp4")
TRIAL_VIDEO_2_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fizzer_trial_video_2.mp4")
# Also accept the original uploaded attachment filename if the user kept it unchanged.
TRIAL_VIDEO_2_CANDIDATES = [
    TRIAL_VIDEO_2_PATH,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "17c767f61711ad6c6855c5d2ebab5789.mp4"),
]
def get_trial_video_2_path():
    return next((path for path in TRIAL_VIDEO_2_CANDIDATES if os.path.isfile(path)), None)

@app.get("/trial-video")
def trial_video():
    if not os.path.isfile(TRIAL_VIDEO_PATH):
        return jsonify({"error": "Trial video file is missing. Upload the MP4 beside app.py."}), 404
    return send_file(TRIAL_VIDEO_PATH, mimetype="video/mp4", conditional=True)

@app.get("/trial-video-2")
def trial_video_2():
    path = get_trial_video_2_path()
    if not path:
        return jsonify({"error": "Second trial video is missing. Keep the supplied MP4 beside app.py as fizzer_trial_video_2.mp4."}), 404
    return send_file(path, mimetype="video/mp4", conditional=True)



# Optional universal public-media engine. yt-dlp currently ships extractors for many
# services, including YouTube, Facebook, Instagram and other video sites. The project
# itself notes that site support can break as websites change, so Fizzer always keeps
# the direct-file fallback too.
DOWNLOAD_JOBS = {}
DOWNLOAD_JOBS_LOCK = threading.Lock()
DOWNLOAD_ROOT = os.path.join(tempfile.gettempdir(), "fizzer-downloads")
os.makedirs(DOWNLOAD_ROOT, exist_ok=True)
MAX_SOCIAL_FILE = 500 * 1024 * 1024


def _public_url_or_error(raw_url):
    parsed = urlparse(raw_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None, "Enter a valid public HTTP or HTTPS link."
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        return None, "Private or local addresses are not supported."
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
            return None, "Private or local addresses are not supported."
    except (socket.gaierror, ValueError):
        return None, "Could not resolve this public link."
    return parsed, None


def _job_update(job_id, **values):
    with DOWNLOAD_JOBS_LOCK:
        if job_id in DOWNLOAD_JOBS:
            DOWNLOAD_JOBS[job_id].update(values)


def _friendly_downloader_error(exc):
    """Return a concise user-facing message for common hosting/network failures."""
    detail = str(exc)
    lowered = detail.lower()
    if "proxyerror" in lowered or "tunnel connection failed" in lowered or "403 forbidden" in lowered and "proxy" in lowered:
        return ("The hosting server's proxy rejected the connection to this platform (HTTP 403). "
                "This is a server/network restriction, not a problem with your link. "
                "Fizzer cannot download this page from the current hosting environment. "
                "Try a permitted direct media URL or a host that allows access to the platform.")
    if "unable to download api page" in lowered or "unable to connect" in lowered:
        return ("The hosting server could not reach the media platform. Check the server's outbound "
                "network access, then try again.")
    return detail[:500] or exc.__class__.__name__


def _run_ytdlp_job(job_id, raw_url, quality, output_format="mp4"):
    """Try several extractor/network profiles in sequence (not third-party proxy servers)."""
    workdir = os.path.join(DOWNLOAD_ROOT, job_id)
    os.makedirs(workdir, exist_ok=True)
    try:
        if yt_dlp is None:
            raise RuntimeError("Universal downloader engine is not installed. Install yt-dlp on the server first.")
        outtmpl = os.path.join(workdir, "%(title).120B [%(id)s].%(ext)s")
        def hook(d):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = (done / total * 100.0) if total else None
                _job_update(job_id, status="downloading", percent=pct, downloaded=done, total=total,
                            speed=d.get("speed") or 0, eta=d.get("eta"), message="Downloading…")
            elif status == "finished":
                _job_update(job_id, status="processing", percent=100, message="Processing media…")

        if output_format not in ("mp4", "mp3", "original"):
            raise RuntimeError("Invalid output format selection.")
        if output_format == "mp3":
            fmt = "bestaudio/best"
        elif quality in ("best", "auto", ""):
            fmt = "bv*+ba/b"
        elif re.fullmatch(r"[A-Za-z0-9._-]{1,40}", quality):
            fmt = quality + "+bestaudio/best"
        else:
            raise RuntimeError("Invalid format selection. Please check the link again.")

        # These are independent yt-dlp extraction profiles, tried one by one.
        # They are not external download websites and cannot bypass host network blocks.
        profiles = [
            {"name": "Default extractor", "args": {}},
            {"name": "Alternate YouTube clients", "args": {"youtube": {"player_client": ["mweb", "tv", "web"]}}},
            {"name": "Web client fallback", "args": {"youtube": {"player_client": ["web_safari", "web_embedded"]}}},
        ]
        errors = []
        for index, profile in enumerate(profiles, 1):
            # Remove partial output from a failed attempt before trying the next profile.
            for name in os.listdir(workdir):
                path0 = os.path.join(workdir, name)
                if os.path.isfile(path0):
                    try: os.remove(path0)
                    except OSError: pass
            opts = {
                "outtmpl": outtmpl, "format": fmt,
                "merge_output_format": "mp4" if output_format == "mp4" else None,
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "restrictfilenames": True, "max_filesize": MAX_SOCIAL_FILE,
                "socket_timeout": 15, "retries": 2, "extractor_retries": 2,
                "fragment_retries": 2, "file_access_retries": 1,
                "concurrent_fragment_downloads": 4, "progress_hooks": [hook],
            }
            if profile["args"]:
                opts["extractor_args"] = profile["args"]
            if output_format == "mp3":
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            elif output_format == "original":
                opts.pop("merge_output_format", None)
            _job_update(job_id, status="trying", percent=0, message=f"Trying download route {index}/{len(profiles)}: {profile['name']}…")
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(raw_url, download=True)
                requested = info.get("requested_downloads") or []
                path = info.get("filepath") or info.get("_filename")
                if not path and requested:
                    path = requested[0].get("filepath") or requested[0].get("_filename")
                if not path or not os.path.isfile(path):
                    files = [os.path.join(workdir, f) for f in os.listdir(workdir)
                             if os.path.isfile(os.path.join(workdir, f))]
                    path = max(files, key=os.path.getmtime) if files else None
                if not path or not os.path.isfile(path):
                    raise RuntimeError("Downloader finished but no output file was created.")
                size = os.path.getsize(path)
                _job_update(job_id, status="ready", percent=100, downloaded=size, total=size,
                            speed=0, title=info.get("title") or "fizzer-download", path=path,
                            message=f"Ready (route {index}: {profile['name']})")
                return
            except Exception as exc:
                errors.append(f"{profile['name']}: {_friendly_downloader_error(exc)}")
        raise RuntimeError("All download routes failed. " + " | ".join(errors[-3:]))
    except Exception as exc:
        _job_update(job_id, status="error", message=_friendly_downloader_error(exc))


@app.get("/downloader-status")
def downloader_status():
    ready, message = ensure_yt_dlp()
    return jsonify({"yt_dlp": ready, "message": message})


@app.post("/prepare-download")
def prepare_download():
    data = request.get_json(silent=True) or {}
    raw_url = str(data.get("url", "")).strip()
    quality = str(data.get("quality", "best")).strip().lower()
    output_format = str(data.get("output_format", "mp4")).strip().lower()
    if output_format not in ("mp4", "mp3", "original"):
        return jsonify({"error": "Choose MP4, MP3, or original format."}), 400
    parsed, err = _public_url_or_error(raw_url)
    if err:
        return jsonify({"error": err}), 400
    ready, setup_message = ensure_yt_dlp()
    if not ready:
        return jsonify({"error": setup_message + " Direct public media/file links can still use the normal downloader."}), 503
    job_id = uuid.uuid4().hex
    with DOWNLOAD_JOBS_LOCK:
        DOWNLOAD_JOBS[job_id] = {"status":"queued","percent":0,"downloaded":0,"total":0,"speed":0,"message":"Preparing…"}
    threading.Thread(target=_run_ytdlp_job, args=(job_id, raw_url, quality, output_format), daemon=True).start()
    return jsonify({"job_id": job_id, "message": "Download job started."})


@app.get("/download-job/<job_id>/status")
def download_job_status(job_id):
    with DOWNLOAD_JOBS_LOCK:
        job = dict(DOWNLOAD_JOBS.get(job_id, {}))
    if not job:
        return jsonify({"error":"Download job not found."}), 404
    safe = {k:v for k,v in job.items() if k not in ("path",)}
    return jsonify(safe)


@app.get("/download-job/<job_id>")
def download_job_file(job_id):
    with DOWNLOAD_JOBS_LOCK:
        job = dict(DOWNLOAD_JOBS.get(job_id, {}))
    if not job or job.get("status") != "ready" or not job.get("path"):
        return jsonify({"error":"Download is not ready yet."}), 409
    path = job["path"]
    if not os.path.isfile(path):
        return jsonify({"error":"Downloaded file is no longer available."}), 404
    name = re.sub(r'[^A-Za-z0-9._ -]', "_", os.path.basename(path))[:140].strip(" .") or "fizzer-download.mp4"
    return send_file(path, as_attachment=True, download_name=name, max_age=0)


@app.post("/check-link")
def check_link():
    """Check whether a URL appears to be a directly downloadable public media file."""
    data = request.get_json(silent=True) or {}
    raw_url = str(data.get("url", "")).strip()
    try:
        parsed = urlparse(raw_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return jsonify({"error": "Enter a valid public HTTP or HTTPS link."}), 400
        host = parsed.hostname.lower().rstrip(".")
        # Try yt-dlp for any public page URL, not only a short hard-coded list
        # of social platforms. Its extractors cover many services; unsupported
        # URLs fall through to the direct-file checker below.
        safe_parsed, safe_error = _public_url_or_error(raw_url)
        if safe_error:
            return jsonify({"error": safe_error}), 400
        engine_ready, engine_message = ensure_yt_dlp()
        if engine_ready:
            try:
                opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "socket_timeout": 15, "extractor_retries": 1, "retries": 1}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(raw_url, download=False)
                title = info.get("title") or "Untitled media"
                duration = info.get("duration")
                formats = [f for f in (info.get("formats") or []) if f.get("vcodec") != "none" and f.get("format_id")]
                formats.sort(key=lambda f: (f.get("height") or 0, f.get("filesize") or f.get("filesize_approx") or 0), reverse=True)
                format_rows=[]; seen=set()
                for f in formats:
                    fid=str(f.get("format_id"))
                    if fid in seen: continue
                    seen.add(fid)
                    format_rows.append({"format_id":fid,"height":f.get("height"),"ext":f.get("ext"),"filesize":f.get("filesize") or f.get("filesize_approx"),"format_note":f.get("format_note"),"has_audio":f.get("acodec") != "none"})
                    if len(format_rows)>=16: break
                qualities = sorted({str(f.get("height")) + "p" for f in formats if f.get("height")}, key=lambda x:int(x[:-1]), reverse=True)[:8]
                msg = "Video found. Choose an available format below."
                if duration: msg += " Duration: " + str(int(duration)//60) + ":" + str(int(duration)%60).zfill(2)
                return jsonify({"message": msg, "supported": True, "title": title, "thumbnail": info.get("thumbnail"), "duration": (str(int(duration)//60)+":"+str(int(duration)%60).zfill(2)) if duration else "", "ext": info.get("ext"), "formats":format_rows,"qualities": qualities})
            except Exception as exc:
                # For social/page URLs, surface the extractor/network failure;
                # for other URLs, let the direct-file fallback have a chance.
                if host in ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "twitter.com", "x.com", "instagram.com", "threads.net", "reddit.com", "vimeo.com", "dailymotion.com", "pinterest.com", "snapchat.com") or not (parsed.path.lower().endswith((".mp4", ".m4v", ".mov", ".webm", ".mp3", ".m4a", ".aac", ".wav", ".ogg"))):
                    return jsonify({"message": _friendly_downloader_error(exc), "supported": False, "engine_ready": True})
        if host == "localhost" or host.endswith((".localhost", ".local")):
            return jsonify({"error": "Private or local addresses are not supported."}), 400
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
            return jsonify({"error": "Private or local addresses are not supported."}), 400
        req = URLRequest(raw_url, headers={"User-Agent": "Fizzer/8.2.0 link checker", "Range": "bytes=0-0"}, method="GET")
        with urlopen(req, timeout=12) as upstream:
            ctype = upstream.headers.get_content_type().lower()
            size = upstream.headers.get("Content-Length")
            is_media = ctype.startswith(("audio/", "video/")) or ctype == "application/octet-stream"
            if is_media:
                return jsonify({"message": "Direct media file detected. Download may work if the server permits it.", "supported": True, "title": unquote(os.path.basename(parsed.path.rstrip("/"))) or "Direct media file", "ext": mimetypes.guess_extension(ctype) or "", "formats": []})
            return jsonify({"message": "Link is reachable, but it does not appear to be a direct media/file URL (" + ctype + "). Download is not guaranteed."})
    except HTTPError as exc:
        return jsonify({"message": "The server responded with HTTP " + str(exc.code) + ". The link may be private, expired, or block automated requests."})
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return jsonify({"error": "Could not check this link. It may be blocked, private, or unreachable."}), 502


@app.post("/download-from-link")
def download_from_link():
    data = request.get_json(silent=True) or {}
    raw_url = str(data.get("url", "")).strip()
    try:
        parsed = urlparse(raw_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return jsonify({"error": "Enter a valid public HTTP or HTTPS media URL."}), 400
        host = parsed.hostname.rstrip(".").lower()
        if host in ("localhost",) or host.endswith((".localhost", ".local")):
            return jsonify({"error": "Private or local addresses are not supported."}), 400
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
            if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
                return jsonify({"error": "Private or local addresses are not supported."}), 400
        except (socket.gaierror, ValueError):
            return jsonify({"error": "Could not resolve this public link."}), 400

        platform_hosts = ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "twitter.com", "x.com", "instagram.com")
        if yt_dlp is not None and any(host == d or host.endswith("." + d) for d in platform_hosts):
            return jsonify({"use_universal": True, "message": "Use the universal downloader engine for this supported public media page."}), 202
        req = URLRequest(raw_url, headers={"User-Agent": "Fizzer/8.2.0 media downloader", "Accept": "audio/*,video/*,application/octet-stream,*/*"})
        upstream = urlopen(req, timeout=25)
        content_type = upstream.headers.get_content_type().lower()
        if not (content_type.startswith("audio/") or content_type.startswith("video/") or content_type == "application/octet-stream"):
            upstream.close()
            return jsonify({"error": "This is not a direct media/file URL. Paste a direct file link instead."}), 415
        length = upstream.headers.get("Content-Length")
        try:
            size = int(length) if length else None
        except ValueError:
            size = None
        if size is not None and size > 250 * 1024 * 1024:
            upstream.close()
            return jsonify({"error": "File is larger than the 250 MB limit."}), 413
        name = unquote(os.path.basename(parsed.path.rstrip("/"))) or "fizzer-download"
        name = re.sub(r'[^A-Za-z0-9._ -]', "_", name)[:140].strip(" .") or "fizzer-download"
        if "." not in name:
            ext = mimetypes.guess_extension(content_type) or ".bin"
            name += ext
        def stream():
            sent = 0
            try:
                while True:
                    chunk = upstream.read(64 * 1024)
                    if not chunk:
                        break
                    sent += len(chunk)
                    if sent > 250 * 1024 * 1024:
                        break
                    yield chunk
            finally:
                upstream.close()
        headers = {"Content-Disposition": "attachment; filename*=UTF-8''" + name.replace(" ", "%20"),
                   "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if size is not None:
            headers["Content-Length"] = str(size)
        return Response(stream(), headers=headers, mimetype=content_type, direct_passthrough=True)
    except HTTPError as exc:
        return jsonify({"error": "The source server returned HTTP " + str(exc.code) + "."}), 502
    except (URLError, TimeoutError, OSError) as exc:
        return jsonify({"error": "Could not fetch this link. Check that it is public and directly downloadable."}), 502

@app.get("/manifest.json")
def manifest():
    return jsonify({
        "name": "Fizzer", "short_name": "Fizzer", "start_url": "/", "scope": "/",
        "display": "standalone", "orientation": "portrait", "background_color": "#050505",
        "theme_color": "#050505", "description": "Fizzer offline-ready audio utility",
        "icons": [
            {"src": "/icon-192.svg", "sizes": "192x192", "type": "image/svg+xml", "purpose": "any maskable"},
            {"src": "/icon-512.svg", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any maskable"}
        ]
    })

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="fg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f7dfae"/><stop offset="1" stop-color="#c18b3f"/></linearGradient></defs><rect width="512" height="512" rx="116" fill="#070709"/><rect x="28" y="28" width="456" height="456" rx="100" fill="#111116" stroke="url(#fg)" stroke-width="12"/><path d="M174 365V147h181v48H232v42h105v46H232v82z" fill="url(#fg)"/><path d="M365 311a52 52 0 1 1-104 0 52 52 0 0 1 104 0z" fill="#070709" stroke="url(#fg)" stroke-width="13"/><path d="M282 310l20 20 42-47" fill="none" stroke="url(#fg)" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/></svg>'''

@app.get("/icon-192.svg")
def icon_192():
    return Response(ICON_SVG, mimetype="image/svg+xml")

@app.get("/icon-512.svg")
def icon_512():
    return Response(ICON_SVG, mimetype="image/svg+xml")

@app.get("/sw.js")
def service_worker():
    js = """const CACHE='fizzer-shell-v22';
const CORE=['/','/manifest.json','/icon-192.svg','/icon-512.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('fizzer-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
 if(e.request.method!=='GET')return;
 if(e.request.mode==='navigate'){
  e.respondWith(fetch(e.request).then(res=>{const copy=res.clone();caches.open(CACHE).then(c=>c.put('/',copy));return res;}).catch(()=>caches.match('/')));
  return;
 }
 e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request).then(res=>{
  if(new URL(e.request.url).origin===self.location.origin){const copy=res.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));}
  return res;
 }).catch(()=>caches.match('/'))));
});"""
    return Response(js, mimetype="application/javascript")

@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "backend": "Flask",
        "external_api": False,
        "server_time": datetime.utcnow().isoformat() + "Z"
    })

@app.get("/api/device")
def device():
    return jsonify({
        "server_platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "hostname": socket.gethostname()
    })

@app.post("/api/settings")
def save_settings():
    data = request.get_json(silent=True) or {}
    try:
        volume = float(data.get("volume", NORMAL_LEVEL))
    except (TypeError, ValueError):
        volume = NORMAL_LEVEL

    volume = max(0, min(MAX_LEVEL, volume))
    hands = bool(data.get("hands", False))

    return jsonify({
        "saved": True,
        "volume": int(volume),
        "hands_free": hands,
        "server_time": int(time.time())
    })

@app.get("/api/config")
def config():
    return jsonify({
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "min_level": 0,
        "normal_level": NORMAL_LEVEL,
        "max_level": MAX_LEVEL,
        "external_api_required": False,
        "in_app_audio_gain": True
    })

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Route not found"}), 404

@app.errorhandler(500)
def server_error(_):
    return jsonify({"error": "Internal server error"}), 500

# PythonAnywhere imports "app" through the WSGI file.
# Do NOT call app.run() on PythonAnywhere.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
