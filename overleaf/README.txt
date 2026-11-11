APIGUARD - Deliverable 2: System Model and Description
IEEE conference format (IEEEtran), CSS453 Term Project, SIIT Thammasat University.

HOW TO USE ON OVERLEAF
1. Go to overleaf.com -> New Project -> Upload Project.
2. Upload this ZIP file.
3. Overleaf sets main.tex as the main document automatically.
   If not: Menu -> Main document -> main.tex.
4. Compiler: pdfLaTeX (Menu -> Compiler). Then press Recompile.

FILES
  main.tex          The paper. Everything is in this one file.
  refs.bib          BibTeX version of the references (optional, see below).
  architecture.png  Figure 1, the three-lane system diagram.

BIBLIOGRAPHY
The references are written out inside main.tex with \begin{thebibliography},
so the document compiles in one pdfLaTeX pass and no BibTeX run is needed.
If you would rather use BibTeX:
  - delete the whole \begin{thebibliography} ... \end{thebibliography} block
  - uncomment these two lines just above it:
        \bibliographystyle{IEEEtran}
        \bibliography{refs}

NOTES
- The note under the author block explains that this deliverable replaces the
  Infrastructure-as-Code system from Deliverable 1. Delete that \thanks{...}
  block in main.tex if you would rather explain the change in person.
- To regenerate architecture.png, run tools/make_architecture.py in the project
  folder (it writes architecture.svg; the PNG is produced with cairosvg).
- Length is 7 pages. CSS453 asks for 6-8 pages for the short IEEE report, so
  this is in range.
