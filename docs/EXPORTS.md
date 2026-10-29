# Exports

## Report exports (main workflow)

The Report page exports exactly what the checklist shows: included items only, in the user's order, with renamed titles, column/row edits, chart edits and edited text. Tables and figures are numbered in document order. Values typed by hand are flagged with † in Word (with a footnote) and with a cell comment in Excel. "Statistical details" off removes test-statistic, df, CI and effect-size columns; "Method notes" adds a short method paragraph after each objective's section. The Word file starts with the report title and the *Objectives of the Study*. The Excel workbook has a **Summary** sheet (metadata, objectives and a list of every component and where it is), **Descriptive Statistics**, **Comparisons**, **Other Analyses**, **Charts** (native, editable Excel column charts for bar and mean charts; images for other chart types), **Interpretations** and an optional **Data** sheet.

When a table's groups or variables are changed in the editor, StatEase re-runs the analysis on the dataset and points the table at the new result; row-level manual edits are dropped at that moment so no outdated value can remain.

## Exporting a list of results (API)

`POST /api/v1/exports` with `options.run_ids` (instead of `report_id`) turns selected results into a Word or Excel file without a saved report. Exports are generated synchronously on the server, then **re-opened with python-docx/openpyxl and size-checked**; only then is a download link returned. Failed exports are recorded with their error and no file is offered.

## What the checklist controls

| Setting | Effect |
|---|---|
| Analyses | Which result runs are included, in workspace order. |
| Charts (per analysis) | Which figures are embedded. Figures that fail to render are counted as failed and not captioned. |
| Report contents | Title, dataset description, research variables, descriptive tables, main results, effect sizes, assumption checks, post hoc tables, interpretation, charts, methodology notes, significance level, references, date, reproducible code. Disabled sections are not written. |
| Inferential statistics | Removes test statistic, df, p, CI or effect-size columns from result tables. |
| Descriptive statistics | Removes columns (mean, SD, skewness…) from descriptive and frequency tables. |
| Style | APA-inspired (Times New Roman 12, italic table titles, p = .032) or clean academic (Calibri 11, p = 0.032). |
| Decimals | 1–4 places for display; values themselves are not rounded in Excel. |
| Interpretation text | Technical, plain, or both; an interpretation edited on the Results page replaces the generated one. |

Presets (Basic, Complete, Thesis-ready, APA-style) set these options; any change switches to "Custom".

## Word (.docx)

- Real Word tables (no screenshots) with APA-style horizontal rules, numbered "Table n" and titles, and notes.
- Charts as 200 dpi PNG images (matplotlib, rendered from the same data as the on-screen charts), numbered "Figure n", with captions.
- Headings per analysis ("Independent-Samples t-Test: Satisfaction by Gender"), assumption checks as a list, warnings, interpretation, optional method notes, references and code.
- Page numbers in the footer; document title and author in the file properties.

## Excel (.xlsx)

- **Overview** sheet: project, dataset, source, α, timestamp, and one row per analysis (variables, N, statistic, p, effect size, sheet).
- Result sheets created only when needed: Descriptive Statistics, T-Test Results, ANOVA Results, Correlations, Regression, Nonparametric Tests, Categorical Tests, Reliability, Post Hoc Comparisons, Assumption Checks, Interpretations, Charts, Variable Dictionary, and optionally Data.
- Numbers are numeric cells with number formats (`#,##0.00`, p-values `[<0.001]"<.001";.000`), so values remain usable in formulas. p-values below α get conditional formatting (bold, shaded).
- Frozen header rows, filters on the Overview, Variable Dictionary and Data sheets, sized columns.
- The raw-data sheet is limited to 1,000,000 rows (Excel's limit is 1,048,576); larger data must be downloaded as CSV.

## File handling

File names are sanitised; files are stored under `storage/exports/` with random names and served only to the project owner. Deleting an export removes the file.
