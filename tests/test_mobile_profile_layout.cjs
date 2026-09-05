const puppeteer = require('puppeteer');
const assert = require('node:assert/strict');
const path = require('node:path');

async function runTest() {
    console.log("Launching Puppeteer for layout regression test...");
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    try {
        const page = await browser.newPage();
        
        // Mobile viewport
        await page.setViewport({width: 320, height: 600});
        
        // Since we want to test the raw HTML with CSS, we can start a mini static server,
        // or just load the template directly, replacing Jinja logic with mock data.
        // Easiest is to load it through file:// protocol but Jinja won't parse.
        // Wait, since we are testing the built UI, let's load a mock HTML containing the exact CSS and HTML structures.
        // Actually, we can fetch from the local flask app if it's running!
        // The user says "Add a regression test". I will just load the exact HTML snippets and the real static CSS files.
        
        const fs = require('fs');
        const root = path.resolve(__dirname, '..');
        
        const styleCss = fs.readFileSync(path.join(root, 'static', 'css', 'style.css'), 'utf8');
        const tailwindCss = fs.readFileSync(path.join(root, 'static', 'css', 'tailwind.css'), 'utf8');
        
        const html = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>${tailwindCss}</style>
            <style>${styleCss}</style>
        </head>
        <body class="bg-gray-200" style="width: 320px; margin: 0; padding: 10px;">
            <div id="password-security-note" class="rounded-2xl sm:rounded-3xl border border-slate-200 bg-slate-50 p-3 sm:p-3.5">
                <div class="security-action-row">
                    <div class="security-text-container" id="text-container-note">
                        <p class="text-[11px] sm:text-xs font-bold text-slate-800 leading-tight">No password is connected yet.</p>
                        <p class="mt-0.5 sm:mt-1 text-[10px] sm:text-[11px] leading-snug sm:leading-relaxed text-slate-500">A password is optional for Google/phone accounts. Add one only if you also want email/password sign-in.</p>
                    </div>
                    <a class="inline-flex items-center justify-center gap-1.5 px-3 sm:px-3.5 py-2 sm:py-2.5 rounded-lg sm:rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-[11px] sm:text-xs font-bold transition flex-shrink-0 w-full sm:w-auto text-center" id="action-btn-note">
                        Set password
                    </a>
                </div>
            </div>

            <section id="sessions-security-card" class="mt-4 rounded-2xl sm:rounded-3xl border border-slate-200 bg-white p-3 sm:p-3.5 shadow-sm security-action-row">
                <div class="flex items-center gap-2.5 sm:gap-3 security-text-container" id="text-container-sessions">
                    <div class="w-8 h-8 sm:w-9 sm:h-9 rounded-lg sm:rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center flex-shrink-0"></div>
                    <div class="security-text-container" id="inner-text-container-sessions">
                        <h4 class="text-[11px] sm:text-xs font-black text-slate-900 leading-tight">Other sessions</h4>
                        <p class="text-[10px] sm:text-[11px] text-slate-500 leading-snug sm:leading-relaxed">Sign out CatRank on your other browsers and devices.</p>
                    </div>
                </div>
                <button id="action-btn-sessions" class="w-full sm:w-auto px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg sm:rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-[11px] sm:text-xs font-bold text-slate-700 transition flex-shrink-0">Sign out other sessions</button>
            </section>
        </body>
        </html>
        `;
        
        await page.setContent(html, {waitUntil: 'load'});
        
        const evalBounds = selector => page.$eval(selector, el => {
            const rect = el.getBoundingClientRect();
            return {width: rect.width, height: rect.height, top: rect.top, left: rect.left};
        });
        
        const noteText = await evalBounds('#text-container-note');
        const noteBtn = await evalBounds('#action-btn-note');
        
        console.log("Password Note Text bounds:", noteText);
        console.log("Password Note Btn bounds:", noteBtn);
        
        const sessText = await evalBounds('#inner-text-container-sessions');
        const sessBtn = await evalBounds('#action-btn-sessions');
        
        console.log("Sessions Text bounds:", sessText);
        console.log("Sessions Btn bounds:", sessBtn);
        
        // Assertions: Ensure they stack and text doesn't collapse horizontally to single word (<100px)
        assert.ok(noteText.width > 200, `Password note text is too narrow! width: ${noteText.width}px. Expected full width stack.`);
        assert.ok(sessText.width > 180, `Sessions note text is too narrow! width: ${sessText.width}px. Expected full width stack.`);
        
        // Ensure buttons are stacked BELOW the text (top of button should be >= bottom of text approx)
        assert.ok(noteBtn.top >= noteText.top + noteText.height, "Button should be stacked below text on mobile");
        assert.ok(sessBtn.top >= sessText.top + sessText.height, "Button should be stacked below text on mobile");
        
        console.log("Regression test passed! Layout is correct on mobile.");
        
    } finally {
        await browser.close();
    }
}

runTest().catch(err => {
    console.error("Test Failed:", err);
    process.exit(1);
});
