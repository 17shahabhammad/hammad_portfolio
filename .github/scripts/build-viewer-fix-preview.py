from pathlib import Path
import base64
import hashlib
import mimetypes
import re

ROOT = Path("_site")
HTML_PATH = ROOT / "index.html"
REVIEW_DIR = Path("_review")
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

if not HTML_PATH.is_file() or not (ROOT / "assets/had-logo.jpg").is_file():
    raise SystemExit("The downloaded current-site artifact is incomplete.")
pages = sorted((ROOT / "pages").rglob("page-*.webp"))
if len(pages) != 538:
    raise SystemExit(f"Expected 538 existing high-resolution WebP sheets, found {len(pages)}.")
if list((ROOT / "pages").rglob("page-*.png")):
    raise SystemExit("The current published baseline should contain WebP drawing sheets.")

# Record every non-HTML file. This test must not touch any image or other asset.
baseline = {
    p.relative_to(ROOT).as_posix(): file_sha(p)
    for p in ROOT.rglob("*")
    if p.is_file() and p != HTML_PATH
}

html = HTML_PATH.read_text(encoding="utf-8")
tick = chr(96)
dollar_open = "$" + "{"

old_css = "transform-origin:center center;user-select:none;will-change:transform}"
new_css = "transform-origin:center center;user-select:none}"
if html.count(old_css) != 1:
    raise SystemExit(f"Expected one initial transform-layer CSS rule; found {html.count(old_css)}.")
html = html.replace(old_css, new_css, 1)

# Change scale transforms to actual image dimensions so zoom samples the high-res source.
old_render = (
    " v.querySelector('.sheetplane').style.transform=" + tick + "translate("
    + dollar_open + "Number(v.dataset.x)||0}px," + dollar_open + "Number(v.dataset.y)||0}px) scale("
    + dollar_open + "z)" + tick + ";"
)
new_render = """  const plane=v.querySelector('.sheetplane'),stage=v.querySelector('.sheetstage');
  if(img.complete && img.naturalWidth>0 && img.naturalHeight>0){
    const fitScale=Math.min(Math.max(1,stage.clientWidth-32)/img.naturalWidth,Math.max(1,stage.clientHeight-32)/img.naturalHeight);
    if(z>1.001){
      img.style.setProperty('max-width','none','important');
      img.style.setProperty('max-height','none','important');
      img.style.setProperty('flex','0 0 auto','important');
      img.style.setProperty('width',String(Math.round(img.naturalWidth*fitScale*z))+'px','important');
      img.style.setProperty('height',String(Math.round(img.naturalHeight*fitScale*z))+'px','important');
      plane.style.willChange='transform';
      plane.style.transform='translate('+(Number(v.dataset.x)||0)+'px,'+(Number(v.dataset.y)||0)+'px)';
    }else{
      img.style.removeProperty('max-width');img.style.removeProperty('max-height');img.style.removeProperty('flex');
      img.style.removeProperty('width');img.style.removeProperty('height');
      plane.style.transform='none';plane.style.willChange='auto';
    }
  }else{
    plane.style.transform='none';plane.style.willChange='auto';
  }"""
if html.count(old_render) != 1:
    raise SystemExit(f"Could not find one fitted-image transform; found {html.count(old_render)}.")
html = html.replace(old_render, new_render, 1)

old_drag = (
    "v.querySelector('.sheetplane').style.transform=" + tick + "translate("
    + dollar_open + "v.dataset.x}px," + dollar_open + "v.dataset.y}px) scale("
    + dollar_open + "v.dataset.zoom)" + tick + ";"
)
new_drag = "v.querySelector('.sheetplane').style.transform='translate('+v.dataset.x+'px,'+v.dataset.y+'px)';"
if html.count(old_drag) != 1:
    raise SystemExit(f"Could not find one drag transform; found {html.count(old_drag)}.")
html = html.replace(old_drag, new_drag, 1)

old_init = "function initSheetViewer(v){\n const goPage="
new_init = "function initSheetViewer(v){\n const image=v.querySelector('.sheet-image');\n image.addEventListener('load',()=>renderSheetViewer(v));\n const goPage="
if html.count(old_init) != 1:
    raise SystemExit(f"Could not find one viewer initialization point; found {html.count(old_init)}.")
html = html.replace(old_init, new_init, 1)

old_observer = " renderSheetViewer(v,true);\n}"
new_observer = """ if('ResizeObserver' in window){
    const resizeObserver=new ResizeObserver(()=>renderSheetViewer(v));
    resizeObserver.observe(stage);
    v._sheetResizeObserver=resizeObserver;
  }
  renderSheetViewer(v,true);
}"""
if html.count(old_observer) != 1:
    raise SystemExit(f"Could not find one viewer end point; found {html.count(old_observer)}.")
html = html.replace(old_observer, new_observer, 1)

if "will-change:transform}" in html:
    raise SystemExit("Initial transform promotion is still present.")
if "scale(" in new_render or "scale(" in new_drag:
    raise SystemExit("The replacement still uses scale transforms.")
if len(re.findall(r'"n":"', html)) != 9:
    raise SystemExit("The original nine-project structure changed unexpectedly.")
HTML_PATH.write_text(html, encoding="utf-8")

after = {
    p.relative_to(ROOT).as_posix(): file_sha(p)
    for p in ROOT.rglob("*")
    if p.is_file() and p != HTML_PATH
}
if baseline != after:
    changed = sorted(k for k in set(baseline) | set(after) if baseline.get(k) != after.get(k))
    raise SystemExit("Non-HTML files changed unexpectedly: " + ", ".join(changed[:20]))
print(f"PASS: patched viewer code only; all {len(pages)} drawing files and non-HTML assets are byte-identical.")

# Create a standalone local-review HTML with one full-resolution representative sheet
# from each drawing set. The full site artifact below retains all 538 sheets.
preview_html = html
asset_refs = sorted(
    set(re.findall(r"assets/[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|svg)", preview_html)),
    key=len, reverse=True
)
missing = []
for ref in asset_refs:
    asset = ROOT / ref
    if not asset.is_file():
        missing.append(ref)
        continue
    mime = mimetypes.guess_type(asset.name)[0] or "image/jpeg"
    data_uri = "data:" + mime + ";base64," + base64.b64encode(asset.read_bytes()).decode("ascii")
    preview_html = preview_html.replace(ref, data_uri)
if missing:
    raise SystemExit("Missing render assets in preview: " + ", ".join(missing))

folders = [
    "pages/01-sedra-admin", "pages/01-sedra-gate", "pages/01-sedra-guard-house",
    "pages/02-marriott", "pages/03-nad-al-hamar", "pages/04-expo-valley",
    "pages/05-park-land", "pages/06-emaar-villa", "pages/07-dubai-south",
    "pages/08-valley-emaar", "pages/09-residential-g4",
]
samples = {}
for folder in folders:
    sample = ROOT / folder / "page-001.webp"
    if not sample.is_file():
        raise SystemExit(f"Missing representative drawing: {sample}")
    samples[folder] = "data:image/webp;base64," + base64.b64encode(sample.read_bytes()).decode("ascii")

marker = "const grid=document.getElementById('projectGrid')"
if marker not in preview_html:
    raise SystemExit("Could not find project-data insertion point.")
old_markup = 'data-folder="' + dollar_open + 'part.folder}" data-pages="' + dollar_open + 'part.pages}"'
new_markup = (
    'data-folder="' + dollar_open + 'part.folder}" data-preview-src="'
    + dollar_open + "part.previewSrc||''" + '}" data-pages="' + dollar_open + 'part.pages}"'
)
if old_markup not in preview_html:
    raise SystemExit("Could not find drawing viewer markup.")
preview_html = preview_html.replace(old_markup, new_markup, 1)

old_src = (
    "function sheetSrc(v,n){return " + tick + dollar_open + "v.dataset.folder}/page-"
    + dollar_open + "String(n).padStart(3,'0')}.webp" + tick + "}"
)
new_src = "function sheetSrc(v,n){return v.dataset.previewSrc || v.dataset.folder+'/page-'+String(n).padStart(3,'0')+'.webp'}"
if old_src not in preview_html:
    raise SystemExit("Could not find WebP sheet resolver.")
preview_html = preview_html.replace(old_src, new_src, 1)

injections = []
for folder, data_uri in samples.items():
    injections.append(
        "window.HAD_PREVIEW_PAGES=window.HAD_PREVIEW_PAGES||{};window.HAD_PREVIEW_PAGES["
        + repr(folder) + "]=" + repr(data_uri) + ";"
    )
injections.append(
    "projects.forEach(p=>{if(p.parts){p.parts.forEach(part=>{part.previewSrc=window.HAD_PREVIEW_PAGES[part.folder];part.pages=1;});}else{p.previewSrc=window.HAD_PREVIEW_PAGES[p.folder];p.pages=1;}});"
)
preview_html = preview_html.replace(marker, "".join(injections) + marker, 1)
old_fallback = "folder:p.folder,pages:p.pages,desc:"
new_fallback = "folder:p.folder,pages:p.pages,previewSrc:p.previewSrc,desc:"
if old_fallback not in preview_html:
    raise SystemExit("Could not find single-set drawing fallback.")
preview_html = preview_html.replace(old_fallback, new_fallback, 1)

notice = '<div class="preview-notice">LOCAL REVIEW ONLY · Sheet viewer rendering fix · One representative high-resolution sheet per drawing set · No drawing or render assets modified</div>'
preview_html = preview_html.replace('<main class="home"', notice + "\n<main class=\"home\"", 1)
preview_html = preview_html.replace(
    "</style>",
    ".preview-notice{padding:10px 20px;background:#302f2e;color:#fff;font:11px Arial,sans-serif;letter-spacing:.04em;text-align:center}\n</style>",
    1,
)
out = REVIEW_DIR / "HAD-Architect-Viewer-Fix-Review.html"
out.write_text(preview_html, encoding="utf-8")
print(f"Created self-contained review HTML: {out.stat().st_size/1024/1024:.1f} MiB; embedded {len(samples)} sheets and {len(asset_refs)} assets.")
