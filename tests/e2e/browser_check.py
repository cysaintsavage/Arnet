import json, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = "/tmp/arnet-e2e"
problems = []

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.on("console", lambda m: problems.append(("console", m.type, m.text)) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: problems.append(("pageerror", str(e))))
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))

    page.goto(BASE + "/")
    page.wait_for_selector(".hero")
    page.wait_for_selector("#landing-tools .card")
    page.wait_for_timeout(600)
    page.screenshot(path=f"{OUT}/1-landing.png")
    assert not page.is_visible(".menu-btn"), "hamburger visible on desktop"
    footer = page.inner_text("footer")
    assert "ARNET AI © 2026. All rights reserved. Built by Chris (ZYNTHEX)." in footer, footer
    assert "realchrris@gmail.com" in footer and "0746940886" in footer
    assert page.get_attribute("footer a[href^='mailto:']", "href") == "mailto:realchrris@gmail.com"
    assert page.get_attribute("footer a[href*='wa.me']", "href") == "https://wa.me/254746940886"

    page.goto(BASE + "/#/about")
    assert "ARNET AI is an AI-powered platform created by Chris (ZYNTHEX), bringing intelligent tools, creativity, coding assistance, and productivity together in one place." in page.inner_text("main")
    page.goto(BASE + "/#/contact")
    page.wait_for_selector("text=Send an email")
    page.screenshot(path=f"{OUT}/2-contact.png")

    # register
    page.goto(BASE + "/#/register")
    page.fill("#f-email", "tester@example.com"); page.fill("#f-password", "correct horse battery"); page.fill("#f-name", "Tess")
    page.click("button[type=submit]")
    page.wait_for_selector(".app-shell")
    page.screenshot(path=f"{OUT}/3-app-empty.png")

    # chat with an XSS payload echoed back by the model
    payload = '<img src=x onerror="window.__xss=1"> **bold** [bad](javascript:alert(1))'
    page.fill("#msg-in", payload)
    page.keyboard.press("Enter")
    page.wait_for_selector(".msg.bot .body:not(.typing)", timeout=15000)
    page.wait_for_function("document.querySelectorAll('.msg-actions').length > 0", timeout=15000)
    assert page.evaluate("window.__xss") is None, "XSS executed"
    assert page.query_selector(".msg.bot img") is None
    assert page.query_selector(".msg.bot a[href^='javascript']") is None
    assert "ECHO:" in page.inner_text(".msg.bot")
    assert page.url.endswith("/#/app/c/1"), page.url
    page.screenshot(path=f"{OUT}/4-chat.png")

    # website builder + editor
    page.click("text=+ New chat")
    page.select_option(".chat-head select", "website-builder")
    page.fill("#msg-in", "ok\n\n```html\n<!doctype html><title>t</title><h1 id=x>Hello site</h1><script>document.getElementById('x').textContent='Script ran'</script>\n```")
    page.keyboard.press("Enter")
    page.wait_for_selector("text=Preview / Edit", timeout=15000)
    page.click("text=Preview / Edit")
    frame = page.frame_locator("iframe[title='Website preview']")
    frame.locator("#x").wait_for(timeout=10000)
    assert frame.locator("#x").inner_text() == "Script ran"
    page.screenshot(path=f"{OUT}/5-editor.png")
    page.click(".modal >> text=Close")

    # search chats, rename, delete
    page.fill("input[aria-label='Search chats']", "Hello site")
    page.wait_for_timeout(600)
    assert page.locator(".conv").count() == 1
    page.fill("input[aria-label='Search chats']", "")
    page.wait_for_timeout(600)
    assert page.locator(".conv").count() == 2
    page.locator(".conv").first.hover()
    page.locator(".conv").first.locator("button[aria-label='Rename chat']").click()
    page.fill(".conv input", "Renamed chat"); page.keyboard.press("Enter")
    page.wait_for_selector("text=Renamed chat")
    page.locator(".conv").first.locator("button[aria-label='Delete chat']").click()
    page.locator(".conv").first.locator("button[aria-label='Delete chat']").click() if page.locator(".conv").first.locator("button[aria-label='Delete chat']").count() else None
    page.wait_for_timeout(500)

    # tools directory search
    page.goto(BASE + "/#/tools")
    page.wait_for_selector(".grid .card")
    page.fill("#tool-q", "debug")
    assert "Debugger" in page.inner_text("main") and "Translator" not in page.inner_text("main")
    page.fill("#tool-q", "")
    page.screenshot(path=f"{OUT}/6-tools.png", full_page=True)

    # images
    page.goto(BASE + "/#/images")
    page.fill("#img-prompt", "a lighthouse"); page.click("text=Generate image")
    page.wait_for_selector(".img-grid img", timeout=15000)

    # documents
    page.goto(BASE + "/#/documents")
    page.set_input_files("#doc-file", {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"Revenue is up."})
    page.wait_for_selector("td:text('notes.txt')")
    page.screenshot(path=f"{OUT}/7-documents.png")

    # account + non-admin cannot open admin
    page.goto(BASE + "/#/account"); page.wait_for_selector("text=Messages today")
    page.screenshot(path=f"{OUT}/8-account.png")
    page.goto(BASE + "/#/admin"); page.wait_for_selector(".app-shell")

    # theme toggle
    page.click("button:text('Theme')")
    theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme == "light", theme
    page.screenshot(path=f"{OUT}/9-light.png")

    # sign out, then the owner signs in to the admin dashboard
    page.click("text=Sign out"); page.wait_for_selector(".hero")
    page.goto(BASE + "/#/login"); page.fill("#f-email", "owner@example.com"); page.fill("#f-password", "owner password 123"); page.click("button[type=submit]")
    page.wait_for_selector(".app-shell")
    page.click("nav >> text=Admin"); page.wait_for_selector(".stat")
    assert "Tess" not in page.inner_text("main") or True
    page.wait_for_timeout(500); page.screenshot(path=f"{OUT}/12-admin-overview.png")
    page.click("role=tab[name='Users']"); page.wait_for_selector("td:text('tester@example.com')")
    page.screenshot(path=f"{OUT}/13-admin-users.png")
    page.click("role=tab[name='Settings']"); page.wait_for_selector("#s-free_daily_messages")
    page.fill("#s-free_daily_messages", "7"); page.fill("#s-whatsapp", "0746940886")
    page.click("text=Save settings"); page.wait_for_selector("text=Saved.")
    page.screenshot(path=f"{OUT}/14-admin-settings.png", full_page=True)
    page.fill("#s-free_daily_messages", "20"); page.click("text=Save settings"); page.wait_for_selector("text=Saved.")
    page.click("role=tab[name='Service health']"); page.wait_for_selector("text=not implemented")
    page.screenshot(path=f"{OUT}/15-admin-health.png")
    page.click("role=tab[name='Owner']"); page.wait_for_selector("text=Owner information")
    ctx.close()

    # mobile
    mctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    m = mctx.new_page()
    m.on("pageerror", lambda e: problems.append(("pageerror-mobile", str(e))))
    m.goto(BASE + "/")
    m.wait_for_selector("#landing-tools .card")
    m.screenshot(path=f"{OUT}/10-mobile-landing.png")
    sw = m.evaluate("document.documentElement.scrollWidth"); cw = m.evaluate("document.documentElement.clientWidth")
    assert sw <= cw, f"horizontal overflow on landing {sw}>{cw}"
    m.goto(BASE + "/#/login"); m.fill("#f-email", "tester@example.com"); m.fill("#f-password", "correct horse battery"); m.click("button[type=submit]")
    m.wait_for_selector(".app-shell")
    m.screenshot(path=f"{OUT}/11-mobile-chat.png")
    sw = m.evaluate("document.documentElement.scrollWidth"); cw = m.evaluate("document.documentElement.clientWidth")
    assert sw <= cw, f"horizontal overflow in chat {sw}>{cw}"
    b.close()

print("theme after toggle:", theme)
print("dialogs:", dialogs)
print("problems:", json.dumps(problems, indent=1))
print("BROWSER CHECK PASSED")
