# Scriptura

This is the Scriptura project.
This project has been created by Zührenur Internship Project – 2025
Project Start Date: August 7, 2025

Scriptura is a Python-based command-line tool designed to simplify and standardize the creation of professional, paginated PDF reports.
Purpose
The main goal of Scriptura is to:
- Help teams produce high-quality reports with consistent design.
- Reduce merge conflicts in multi-author workflows by keeping sections modular.
- Provide theme-based styling for covers, footers, numbering, and last pages.
- Streamline the workflow from HTML sections → PDF output using Paged.js.

 **Key Features**
   CLI Tool with Commands
  'init': Initialize a new modular report structure.  
  'lint': Validate the structure (missing files, HTML errors, numbering issues).  
  'build': Assemble all sections into one HTML file and export to PDF.  
  'serve': Preview the report locally before exporting.  


Sections are stored as separate .html files ( 01-introduction.html, 02-methodology.html …).  
  -Easy to edit and review collaboratively.  

Scriptura uses CSS themes for consistent design:  

- cover.css – defines the look of the cover page.  
- footer.css – handles page numbers and running headers.  
- general.css – controls typography, tables, images, and code blocks.  
- numbering.css – adds automatic numbering to sections and subsections.  
- last-page.css – defines the final page (e.g., acknowledgments or closing notes).  


    
├── sections/
│   ├── 01-introduction.html
│   ├── 02-methodology.html
│   ├── 03-results.html
│   ├── 04-discussion.html
│   ├── 05-conclusion.html
│   └── 06-appendix.html
|
├── images/
├── diagrams/
├── style/
│   ├──cover.css
│   ├── footer.css
│   ├── general.css
│   ├── numbering.css
│   └── last-page.css. 
├── config.yaml
└── report.html 
├── scriptura.py 

## Installation
1. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Build your first report:
   ```bash
   python scriptura.py build
   ```

Requirements:  
- Python 3.9+  
- Packages: `click`, `pyyaml`, `jinja2`  

---

## Usage Examples

- **Create a new report**
  bash
  python scriptura.py init demo-report
  

- **Validate structure**
  bash
  python scriptura.py lint
  

- **Generate PDF**
  bash
  python scriptura.py build
  ```

- **Preview in browser**
  bash
  python scriptura.py serve
  
