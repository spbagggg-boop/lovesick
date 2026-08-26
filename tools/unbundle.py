"""Turn an exported single-file bundle into the fast multi-file site.

The authoring tool exports one self-contained HTML with every font, the cover
image and the runtime inlined as base64 (~25MB). A browser must download and
decode all of it before it can paint anything, and on a phone the fixed 720px
artboard renders wider than the screen. This script unpacks that export into
ordinary files, subsets the fonts to the glyphs the page actually uses, drops
the redundant woff copies, recompresses the cover, and fixes the viewport.

Usage:  python tools/unbundle.py <exported-bundle.html> <output-dir>

Requires: fonttools[woff] (brotli), pillow.
"""
import base64
import gzip
import io
import json
import os
import re
import sys

from fontTools import subset
from PIL import Image

UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

# The runtime resolves these CDN ids through window.__resources; without the map
# it falls back to unpkg and additionally re-fetches the page looking for bundle
# data, so the map is what keeps the page self-hosted.
CDN = {
    'https://unpkg.com/react@18.3.1/umd/react.production.min.js': 'js/react.js',
    'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js': 'js/react-dom.js',
}

TITLE = 'LOVESICK — 도화살롱'
DESCRIPTION = '나를 사랑해본 사람의 눈으로 보는 나. LOVESICK — 도화살롱'
CTA_URL = 'https://dohwasalon.com/surl/O/28'
ARTBOARD_WIDTH = 720


def block(doc, name):
    tag = '<script type="__bundler/%s">' % name
    s = doc.index(tag) + len(tag)
    return doc[s:doc.index('</script>', s)].strip()


def main(src, out):
    with io.open(src, encoding='utf-8') as f:
        doc = f.read()

    manifest = json.loads(block(doc, 'manifest'))
    tpl = json.loads(block(doc, 'template'))

    for sub in ('fonts', 'img', 'js'):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    assets = {}
    for uuid, entry in manifest.items():
        raw = base64.b64decode(entry['data'])
        if entry.get('compressed'):
            raw = gzip.decompress(raw)
        assets[uuid] = (entry['mime'], raw)

    # ── fonts ────────────────────────────────────────────────────────────────
    # Pretendard carries ~11k glyphs per weight; this page uses a few hundred
    # characters, so a subset is ~50KB instead of ~780KB.
    text = re.sub(r'<style>.*?</style>', ' ', tpl, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    chars = set(text) | set(chr(c) for c in range(0x20, 0x7F)) | set('—–…·“”‘’「」『』€₩©®™✓×')
    unicodes = sorted(ord(c) for c in chars if ord(c) > 0x1F)

    faces = re.findall(r'@font-face\s*\{[^}]*\}', tpl, re.S)
    assert faces, 'no @font-face blocks found'
    for face in faces:
        weight = re.search(r'font-weight:\s*(\d+)', face).group(1)
        local = re.search(r"local\('Pretendard ([^']+)'\)", face).group(1)
        woff2 = re.search(r'url\("(%s)"\) format\(\'woff2\'\)' % UUID, face).group(1)

        raw_path = os.path.join(out, 'fonts', '_full-%s.woff2' % weight)
        with open(raw_path, 'wb') as f:
            f.write(assets[woff2][1])
        name = 'pretendard-%s.woff2' % weight
        subset.main([
            raw_path,
            '--flavor=woff2',
            '--unicodes=%s' % ','.join('U+%04X' % u for u in unicodes),
            '--layout-features=*',
            '--output-file=%s' % os.path.join(out, 'fonts', name),
        ])
        os.remove(raw_path)

        # The woff fallback is dropped: anything that can run this page has
        # supported woff2 for years, and it was 10MB of the export.
        new_face = re.sub(
            r'src:[^;]*;',
            "src: local('Pretendard %s'), url(\"fonts/%s\") format('woff2');" % (local, name),
            face, flags=re.S)
        tpl = tpl.replace(face, new_face)

    # ── cover image ──────────────────────────────────────────────────────────
    png_uuid = next(u for u, (mime, _) in assets.items() if mime.startswith('image/'))
    png_path = os.path.join(out, 'img', '_cover.png')
    with open(png_path, 'wb') as f:
        f.write(assets[png_uuid][1])
    im = Image.open(png_path)
    im.save(os.path.join(out, 'img', 'cover.webp'), 'WEBP', quality=88, method=6)
    os.remove(png_path)
    tpl = re.sub(
        r'<img src="%s" alt="([^"]*)" style="([^"]*)">' % png_uuid,
        r'<img src="img/cover.webp" alt="\1" width="%d" height="%d" decoding="async" style="\2">'
        % im.size,
        tpl)

    # ── scripts ──────────────────────────────────────────────────────────────
    js = [(u, raw) for u, (mime, raw) in assets.items() if mime == 'text/javascript']
    runtime = next(u for u, _ in js if u in tpl)
    react = min((u for u, _ in js if u != runtime), key=lambda u: len(assets[u][1]))
    react_dom = next(u for u, _ in js if u not in (runtime, react))
    for uuid, name in ((runtime, 'dc-runtime.js'), (react, 'react.js'), (react_dom, 'react-dom.js')):
        with open(os.path.join(out, 'js', name), 'wb') as f:
            f.write(assets[uuid][1])

    tpl = tpl.replace(
        '<script src="%s"></script>' % runtime,
        '<script>window.__resources = %s;</script>\n<script src="js/dc-runtime.js"></script>'
        % json.dumps(CDN))

    # ── viewport / head ──────────────────────────────────────────────────────
    # The design is a fixed 720px artboard. Under width=device-width a phone
    # lays it out at 720 CSS px inside a ~390px window, so it has to be pinched
    # to fit; declaring the artboard width makes the browser scale it instead.
    old_viewport = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    assert old_viewport in tpl, 'viewport meta not found — export format changed?'
    tpl = tpl.replace(old_viewport,
                      '<meta name="viewport" content="width=%d">\n'
                      '<title>%s</title>\n'
                      '<meta name="description" content="%s">'
                      % (ARTBOARD_WIDTH, TITLE, DESCRIPTION))

    # ── bottom CTA ───────────────────────────────────────────────────────────
    # The export renders the button as a bare div; wrap it so it links out.
    label = '\U0001F525 X시점 데이터 열어보기'
    if label in tpl and 'href="%s"' % CTA_URL not in tpl:
        i = tpl.index(label)
        start = tpl.rindex('<div style="background:#6e1414', 0, i)
        end = tpl.index('</div>', i) + len('</div>')
        tpl = (tpl[:start] +
               '<a href="%s" target="_blank" rel="noopener" '
               'style="display:block;text-decoration:none;color:inherit;cursor:pointer;">' % CTA_URL +
               tpl[start:end] + '</a>' + tpl[end:])

    leftover = set(re.findall(UUID, tpl))
    assert not leftover, 'unresolved resource ids: %s' % leftover

    with io.open(os.path.join(out, 'index.html'), 'w', encoding='utf-8', newline='') as f:
        f.write(tpl)
    open(os.path.join(out, '.nojekyll'), 'w').close()

    total = sum(os.path.getsize(os.path.join(r, n))
                for r, _, ns in os.walk(out) for n in ns)
    print('source bundle: %s bytes' % format(os.path.getsize(src), ','))
    print('built site:    %s bytes' % format(total, ','))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
