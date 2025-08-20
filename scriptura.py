#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scriptura (single-file) — modular report CLI
Komutlar: init, lint, build, serve
Bağımlılıklar: click, pyyaml, (opsiyonel) beautifulsoup4, playwright
"""
from dataclasses import dataclass, replace
import click
import sys, os, re, json, pathlib, shutil, http.server, socketserver, subprocess
from typing import List, Dict, Optional

# ---------------------------
# Helper
# ---------------------------
CWD = pathlib.Path.cwd()

def read_text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")

def write_text(p: pathlib.Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def discover_sections(sec_dir: pathlib.Path) -> List[str]:
    files = [p for p in sec_dir.glob("*.html")]
    def key(p: pathlib.Path):
        m = re.match(r"^(\d+)[-_]", p.name)
        return (int(m.group(1)) if m else 1_000_000, p.name.lower())
    return [f"sections/{p.name}" for p in sorted(files, key=key)]

# ---------------------------
# Config
# ---------------------------
try:
    import yaml
except ImportError:
    yaml = None

@dataclass
class Config:
    title: str = ""
    subtitle: str = ""
    prepared: str = ""
    kicker: str = ""
    sections: Optional[List[str]] = None
    theme: Optional[Dict[str, str]] = None

def load_config(path: str | pathlib.Path) -> Config:
    if not yaml:
        click.echo("HATA: PyYAML gerekli. `pip install pyyaml`", err=True)
        raise SystemExit(1)
    data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8")) or {}
    return Config(
        title=data.get("title", ""),
        subtitle=data.get("subtitle", ""),
        prepared=data.get("prepared", ""),
        kicker=data.get("kicker", ""),
        sections=data.get("sections"),
        theme=data.get("theme"),
    )

# ---------------------------
# HTML Birleştirme (report.html şablonuna __CONFIG__ enjekte)
# ---------------------------
PLACEHOLDERS = {"[TITLE]":"title","[SUBTITLE]":"subtitle","[PREPARED]":"prepared","[KICKER]":"kicker"}

def apply_placeholders(html: str, cfg: Config) -> str:
    for token, key in PLACEHOLDERS.items():
        html = html.replace(token, getattr(cfg, key) or "")
    return html

def inject_boot_config(html: str, cfg: Config) -> str:
    boot = f"""
<script>
window.__CONFIG__ = {{
  title: {json.dumps(cfg.title)},
  subtitle: {json.dumps(cfg.subtitle)},
  prepared: {json.dumps(cfg.prepared)},
  kicker: {json.dumps(cfg.kicker)},
  sections: {json.dumps(cfg.sections or [])}
}};
</script>
"""
    return html.replace("</head>", boot + "\n</head>")

def override_theme_links(html: str, theme: Dict[str, str]) -> str:
    mapping = {
        'style/general.css': theme.get('general'),
        'style/numbering.css': theme.get('numbering'),
        'style/footer.css': theme.get('footer'),
        'style/cover.css': theme.get('cover'),
        'style/last-page.css': theme.get('last') or theme.get('last-page'),
    }
    for local, remote in mapping.items():
        if remote:
            html = html.replace(f'href="{local}"', f'href="{remote}"')
    return html

def assemble_html(cfg: Config, wrapper_path: pathlib.Path) -> str:
    html = read_text(wrapper_path)
    html = apply_placeholders(html, cfg)
    html = inject_boot_config(html, cfg)
    if cfg.theme:
        html = override_theme_links(html, cfg.theme)
    return html

# ---------------------------
# PDF (Playwright varsa)
# ---------------------------
def export_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        click.echo("⚠️  Playwright yok: `pip install playwright` ve `python -m playwright install chromium`", err=True)
        click.echo("   Yine de HTML üretildi; PDF için tarayıcıdan Yazdır→PDF kaydedebilirsiniz.", err=True)
        return

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.absolute().as_uri(), wait_until="load")
        page.wait_for_timeout(1500)  # Paged.js sayfalamayı bitirsin
        page.pdf(path=str(pdf_path), format="A4", print_background=True)
        browser.close()

# ---------------------------
# Scaffold içerikleri
# ---------------------------
SCAFFOLD_REPORT_HTML = """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <title>[TITLE]</title>

  <link rel="stylesheet" href="style/general.css" />
  <link rel="stylesheet" href="style/numbering.css" />
  <link rel="stylesheet" href="style/footer.css" />
  <link rel="stylesheet" href="style/cover.css" />
  <link rel="stylesheet" href="style/last-page.css" />

  <script>
    // Paged.js başlamadan önce sections/*.html dosyalarını gövdeye ekle
    window.PagedConfig = {
      before: async () => {
        const cfg = window.__CONFIG__ || {};
        const t = document.getElementById("title"); if (t) t.textContent = cfg.title || "";
        const s = document.querySelector(".subtitle"); if (s) s.textContent = cfg.subtitle || "";
        const p = document.querySelector(".prepared"); if (p) p.textContent = cfg.prepared || "";
        const k = document.querySelector(".kicker"); if (k) k.textContent = cfg.kicker || "";
        for (const file of (cfg.sections || [])) {
          try {
            const res = await fetch(file);
            if (!res.ok) { console.warn("Missing section:", file); continue; }
            const html = await res.text();
            const host = document.createElement("div");
            host.innerHTML = html;
            document.body.insertBefore(host, document.getElementById("end"));
          } catch (e) {
            console.warn("Fetch error for", file, e);
          }
        }
      }
    };
  </script>
  <script src="https://unpkg.com/pagedjs/dist/paged.polyfill.js"></script>
</head>
<body>
  <section class="cover unnumbered">
    <div class="title-section">
      <div class="kicker">[KICKER]</div>
      <h1 id="title">[TITLE]</h1>
      <p class="subtitle">[SUBTITLE]</p>
      <div class="prepared">[PREPARED]</div>
    </div>
  </section>

  <section id="end" class="last-page unnumbered">
    <h1>Teşekkürler</h1>
    <p>Okuduğunuz için teşekkürler.</p>
  </section>
</body>
</html>
"""

SCAFFOLD_CONFIG = """title: Deneme Raporu
subtitle: Modular report with Paged.js
prepared: "Yazar — 2025-08-18"
kicker: Internal Report
# sections:  # boşsa sections/*.html otomatik keşfedilir
#   - sections/01-introduction.html
# theme:
#   general: "https://.../general.css"
#   numbering: "https://.../numbering.css"
#   footer: "https://.../footer.css"
#   cover: "https://.../cover.css"
#   last: "https://.../last-page.css"
"""

SAMPLE_SECTIONS = {
    "01-introduction.html": """<section class="page-break">
  <h1>Introduction</h1>
  <p>Project goals, scope and context.</p>
</section>
""",
    "02-methodology.html": """<section class="page-break">
  <h1>Methodology</h1>
  <p>Approach, data and tools.</p>
</section>
""",
    "03-results.html": """<section class="page-break">
  <h1>Results</h1>
  <p>Key findings and figures.</p>
</section>
"""
}

# ---------------------------
# Komutlar (Click)
# ---------------------------
@click.group()
def cli():
    """Scriptura (single-file): modular Paged.js reports."""
    pass

@cli.command()
@click.argument("name", default="report")
@click.option("--force", is_flag=True, help="Var olan klasörü silip yeniden oluştur.")
@click.option("--git/--no-git", default=True, show_default=True, help="Git deposu başlat.")
def init(name, force, git):
    """Yeni rapor iskeleti oluştur (./<name>)."""
    target = CWD / name
    if target.exists() and not force:
        raise SystemExit(f"'{name}' zaten var. --force ile üzerine yazabilirsiniz.")
    if target.exists() and force:
        shutil.rmtree(target)

    # klasörler
    (target / "sections").mkdir(parents=True, exist_ok=True)
    (target / "style").mkdir(parents=True, exist_ok=True)
    (target / "images").mkdir(exist_ok=True)
    (target / "diagrams").mkdir(exist_ok=True)
    (target / "build").mkdir(exist_ok=True)

    # dosyalar
    write_text(target / "report.html", SCAFFOLD_REPORT_HTML)
    write_text(target / "config.yaml", SCAFFOLD_CONFIG)
    for fname, content in SAMPLE_SECTIONS.items():
        write_text(target / f"sections/{fname}", content)
    write_text(target / ".gitignore", "build/\nnode_modules/\n*.tmp.html\n.DS_Store\n")

    # git
    if git:
        try:
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=target, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
            )
        except subprocess.CalledProcessError:
            subprocess.run(["git", "init"], cwd=target, check=False)

    click.echo(f"✓ Scaffold created at ./{name}")

@cli.command()
@click.option("--config", default="config.yaml", show_default=True, help="config.yaml yolu")
@click.option("--out", default="build/report.pdf", show_default=True, help="PDF çıktı yolu")
@click.option("--html-out", default="build/report.tmp.html", show_default=True, help="Birleşik HTML yolu")
def build(config, out, html_out):
    """Bölümleri birleştir (server-side inline) + PDF üret."""
    base_dir = pathlib.Path(config).resolve().parent

    # 1) config yükle + sections yoksa keşfet
    cfg = load_config(config)
    if not cfg.sections:
        cfg.sections = discover_sections(base_dir / "sections")

    # 2) runtime loader'ı kapat: enjekte edeceğimiz __CONFIG__ içinde sections boş olsun
    cfg_injected = replace(cfg, sections=[])

    # 3) şablonu oku ve __CONFIG__ enjekte et
    assembled = assemble_html(cfg_injected, wrapper_path=base_dir / "report.html")

    # 4) section dosyalarını sunucu tarafında göm (inline)
    sections_abs = []
    for s in (cfg.sections or []):
        p = (base_dir / s).resolve()
        if not p.exists():
            alt = ((base_dir / html_out).resolve().parent / s).resolve()
            if alt.exists():
                p = alt
        if p.exists():
            sections_abs.append(p)
        else:
            click.echo(f"⚠️  Bulunamadı (atlanıyor): {s}", err=True)

    combined = "\n".join(p.read_text(encoding="utf-8") for p in sections_abs)

    # 5) 'id="end"' öncesine yerleştir; yoksa </body> öncesine ekle
    marker = '<section id="end"'
    if marker in assembled:
        assembled = assembled.replace(marker, combined + "\n" + marker, 1)
    else:
        assembled = assembled.replace("</body>", combined + "\n</body>", 1)

    # 6) HTML'i yaz ve PDF üret
    out_html = (base_dir / html_out)
    out_pdf = (base_dir / out)
    write_text(out_html, assembled)
    click.echo(f"✓ Assembled HTML → {out_html.relative_to(base_dir)}")

    export_pdf(out_html, out_pdf)
    if out_pdf.exists():
        click.echo(f"✓ PDF written → {out_pdf.relative_to(base_dir)}")

@cli.command()
@click.option("--config", default="config.yaml", show_default=True)
def lint(config):
    """Basit doğrulamalar: sections var mı, sıralama ve <h1> var mı?"""
    base = pathlib.Path(config).resolve().parent
    sec_dir = base / "sections"
    errors = []

    if not sec_dir.exists():
        errors.append("sections/ klasörü yok.")
    else:
        files = list(sec_dir.glob("*.html"))
        if not files:
            errors.append("sections/ boş görünüyor.")
        # sıralama kontrolü
        ordered = discover_sections(sec_dir)
        if [f"sections/{p.name}" for p in sorted(files)] != ordered:
            # sadece uyarı: özel isimli dosyalar olabilir
            click.echo("⚠️  Uyarı: dosya sıralaması (01-, 02-, …) beklenenden farklı görünüyor.")

        # BeautifulSoup varsa içerik daha iyi doğrulanır
        try:
            from bs4 import BeautifulSoup  # type: ignore
            use_bs4 = True
        except Exception:
            use_bs4 = False

        for p in files:
            txt = p.read_text(encoding="utf-8")
            if use_bs4:
                soup = BeautifulSoup(txt, "html.parser")
                sect = soup.find("section")
                if not sect:
                    errors.append(f"{p.name}: <section> yok.")
                    continue
                if not sect.find("h1"):
                    errors.append(f"{p.name}: <h1> yok.")
                if not sect.get_text(strip=True):
                    errors.append(f"{p.name}: section içeriği boş.")
            else:
                # çok basit kontroller
                if "<section" not in txt:
                    errors.append(f"{p.name}: <section> yok.")
                if "<h1" not in txt:
                    errors.append(f"{p.name}: <h1> yok.")

    if errors:
        for e in errors:
            click.echo("✗ " + e)
        raise SystemExit(1)
    click.echo("✓ Lint passed")

@cli.command()
@click.option("--port", default=8080, show_default=True)
def serve(port):
    """Kök klasörü servis et (önizleme için)."""
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        click.echo(f"Serving at http://localhost:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nServer stopped.")

if __name__ == "__main__":
    cli()
