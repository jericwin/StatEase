# Brand files

- `statease-mark.svg`: the two-colour mark (normal curve with the upper tail in rust). The same paths are in `frontend/src/components/brand/Mark.tsx` and `frontend/public/favicon.svg`.
- `statease-logo-light.png` and `statease-logo-dark.png`: the mark with the wordmark.
- `statease-comparison.png`: the feature comparison with JASP, Google Forms and Python, for slides and papers. It is **not** used on the website.

## Updating the comparison

Edit the rows in `comparison.html` (the `GROUPS` list), then re-render the PNG at 2× from the `frontend` folder:

```bash
node -e "const{chromium}=require('@playwright/test');(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1200,height:900},deviceScaleFactor:2});await p.goto('file:///'+require('path').resolve('../docs/brand/comparison.html'));await p.evaluate(()=>document.fonts.ready);await p.locator('#figure').screenshot({path:'../docs/brand/statease-comparison.png'});await b.close()})()"
```

Before publishing it anywhere, check the JASP, Google Forms and Python rows against those products' current documentation.
