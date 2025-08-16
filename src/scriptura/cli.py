from pathlib import Path
from typing import List, Optional
import http.server, socketserver, os, shutil, subprocess, typer, yaml
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

app = typer.Typer(help="Scriptura: modüler rapor (HTML → PDF via Paged.js)")
ROOT = Path(__file__).resolve().parent
TPL_DIR = ROOT / "templates"

# ---------- yardımcılar ----------
def read_config(path: Path) -> dict:
    if not path.exists(): return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def find_sections(sections_dir: Path, pattern: str) -> List[Path]:
    return sorted(sections_dir.glob(pattern))

def render_report(sections_html: List[str], meta: dict,
                  theme_base_url: Optional[str], href_base: Optional[str],
                  out_html: Path) -> None:
    env = Environment(loader=FileSystemLoader(str(TPL_DIR)),
                      autoescape=select_autoescape(["html","xml"]))
    tpl = env.get_template("report_wrapper.html.j2")
    html = tpl.render(sections=sections_html, meta=meta or {},
                      theme_base_url=theme_base_url, href_base=href_base)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")

def substitute_placeholders(text: str, meta: dict, extra: dict) -> str:
    # Tema/sections içinde [TITLE], [AUTHOR] gibi yer tutucuları doldurmak için basit değiştirme
    mapping = {
        "TITLE": meta.get("title", ""),
        "SUBTITLE": meta.get("subtitle", ""),
        "AUTHOR": meta.get("author", ""),
        "DATE": meta.get("date", ""),
    }
    mapping.update(extra or {})
    for key, val in mapping.items():
        text = text.replace(f"[{key}]", str(val))
    return text

# ---------- komutlar ----------
@app.command()
def init(report_name: str = typer.Argument("report", help="Oluşturulacak rapor klasörü")):
    r = Path(report_name)
    if r.exists():
        typer.secho(f"[!] {report_name} zaten var.", fg=typer.colors.YELLOW); raise typer.Exit(1)
    (r/"sections").mkdir(parents=True)
    (r/"images").mkdir()
    (r/"diagrams").mkdir()
    (r/"style").mkdir()

    (r/"sections"/"01-introduction.html").write_text(
        "<section><h1>Introduction</h1><p>Start here.</p></section>", encoding="utf-8")

    cfg = {
        "meta": {"title":"New Report","subtitle":"","author":"","date":""},
        "section_glob":"*.html",
        # Yerel tema klasörü kullanıyorsan style/ (senin projende bu var)
        "theme_local_dir":"style",
        # Uzak tema kullanacaksan:
        # "theme_base_url": "https://public-host/theme",
        # İsteğe bağlı özel yer tutucular:
        # "placeholders": {"COMPANY":"Acme Inc"}
    }
    (r/"config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    # içinde çalıştığın klasör zaten bir git reposu değilse yeni rapor klasörü için git init
    try:
        if os.system("git rev-parse --is-inside-work-tree >/dev/null 2>&1") != 0:
            os.system(f"git init {report_name} >/dev/null 2>&1")
    except Exception:
        pass
    typer.secho(f"[✓] ./{report_name} hazır.", fg=typer.colors.GREEN)

@app.command()
def build(report_dir: str = typer.Argument(".", help="Rapor klasörü"),
          out_dir: str = typer.Option("dist", help="Çıktı klasörü"),
          pdf: bool = typer.Option(False, help="PDF üret"),
          generate_diagrams: bool = typer.Option(False, help="diagrams/ içindeki .mmd/.puml dosyalarını işle")):
    rdir = Path(report_dir)
    cfg = read_config(rdir/"config.yaml")
    meta = cfg.get("meta", {})
    placeholders = cfg.get("placeholders", {})

    sections = find_sections(rdir/"sections", cfg.get("section_glob","*.html"))
    if not sections:
        typer.secho("[!] sections boş.", fg=typer.colors.RED); raise typer.Exit(1)

    # Bölümleri oku + yer tutucu doldur
    sections_html = []
    for p in sections:
        html = p.read_text(encoding="utf-8")
        html = substitute_placeholders(html, meta, placeholders)
        sections_html.append(html)

    # dist hazırlığı
    dist = Path(out_dir)
    if dist.exists(): shutil.rmtree(dist)
    dist.mkdir(parents=True, exist_ok=True)

    # images kopyala (varsa)
    if (rdir/"images").exists():
        shutil.copytree(rdir/"images", dist/"images")

    # diagrams üret (opsiyonel)
    if generate_diagrams and (rdir/"diagrams").exists():
        out_d = dist/"images"/"diagrams"; out_d.mkdir(parents=True, exist_ok=True)
        # Mermaid (.mmd)
        mmdc = shutil.which("mmdc")
        for m in sorted((rdir/"diagrams").glob("*.mmd")):
            if mmdc:
                os.system(f'"{mmdc}" -i "{m}" -o "{out_d/m.with_suffix(".svg").name}"')
            else:
                typer.secho(f"[i] Mermaid CLI (mmdc) yok, atlanıyor: {m.name}", fg=typer.colors.YELLOW)
        # PlantUML (.puml)
        plantuml = shutil.which("plantuml")
        for u in sorted((rdir/"diagrams").glob("*.puml")):
            if plantuml:
                os.system(f'"{plantuml}" -tpng -o "{out_d}" "{u}"')
            else:
                typer.secho(f"[i] PlantUML yok, atlanıyor: {u.name}", fg=typer.colors.YELLOW)

    # tema (style/ veya theme/)
    href_base = None
    theme_base_url = cfg.get("theme_base_url")
    theme_local_dir = cfg.get("theme_local_dir")
    if theme_local_dir and (rdir/theme_local_dir).exists():
        shutil.copytree(rdir/theme_local_dir, dist/"theme")
        href_base = "theme"
    elif (rdir/"style").exists():
        shutil.copytree(rdir/"style", dist/"style")
        href_base = "style"

    # HTML'i üret
    out_html = dist/"report.html"
    render_report(sections_html, meta, theme_base_url, href_base, out_html)
    typer.secho(f"[✓] HTML: {out_html}", fg=typer.colors.GREEN)

    # PDF istenirse
    if pdf:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            typer.secho("[!] Playwright yok: pip install -e .[pdf] && python -m playwright install chromium",
                        fg=typer.colors.RED); raise typer.Exit(1)
        out_pdf = dist/"report.pdf"
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(out_html.resolve().as_uri(), wait_until="load")
            # Paged.js hazır olunca
            try:
                page.wait_for_function("() => window.Paged && window.Paged.ready", timeout=10000)
            except Exception:
                pass
            page.pdf(path=str(out_pdf), print_background=True, format="A4",
                     margin={"top":"18mm","right":"18mm","bottom":"20mm","left":"18mm"})
            browser.close()
        typer.secho(f"[✓] PDF: {out_pdf}", fg=typer.colors.GREEN)

@app.command()
def lint(report_dir: str = typer.Argument(".", help="Rapor klasörü")):
    rdir = Path(report_dir)
    sections = find_sections(rdir/"sections", "*.html")
    errors = 0

    # temel dosya varlık kontrolleri
    must_css = ["general.css","numbering.css","footer.css","cover.css","last-page.css"]
    style_dir = rdir/"style"
    for css in must_css:
        if not (style_dir/css).exists():
            typer.secho(f"[!] style/{css} eksik.", fg=typer.colors.YELLOW); errors += 1

    for p in sections:
        html = p.read_text(encoding="utf-8")
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception as e:
            typer.secho(f"[!] Parse hatası {p.name}: {e}", fg=typer.colors.RED); errors += 1; continue

        # en az bir h1
        hs = [h.name for h in soup.find_all(["h1","h2","h3","h4"])]
        if "h1" not in hs:
            typer.secho(f"[!] {p.name}: en az bir <h1> olmalı.", fg=typer.colors.YELLOW); errors += 1

        # hiyerarşi atlaması (h1→h3 gibi)
        level = {"h1":1,"h2":2,"h3":3,"h4":4}; last = 0
        for h in hs:
            cur = level[h]
            if last and cur > last + 1:
                typer.secho(f"[!] {p.name}: başlık hiyerarşisi atlaması (ör. h1→h3).", fg=typer.colors.YELLOW)
                errors += 1; break
            last = cur

    if errors:
        typer.secho(f"[x] Lint {errors} uyarı/hata ile bitti.", fg=typer.colors.RED); raise typer.Exit(1)
    else:
        typer.secho("[✓] Lint geçti.", fg=typer.colors.GREEN)

@app.command()
def serve(directory: str = typer.Option("dist", help="Sunulacak klasör"),
          port: int = typer.Option(8000, help="Port")):
    os.chdir(directory)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        typer.secho(f"[✓] http://localhost:{port}", fg=typer.colors.GREEN)
        try: httpd.serve_forever()
        except KeyboardInterrupt: pass

if __name__ == "__main__":
    app()
