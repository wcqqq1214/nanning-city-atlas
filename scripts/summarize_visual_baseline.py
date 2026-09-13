#!/usr/bin/env python3
"""Package local browser and Blender evidence into small reviewable contact sheets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--inspection', type=Path, required=True)
    parser.add_argument('--scales', type=Path, required=True)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', type=Path, default=Path('/System/Library/Fonts/Hiragino Sans GB.ttc'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(args.font), 19)
    titlefont = ImageFont.truetype(str(args.font), 25)

    def sheet(rows, width, height, headings, title, filename):
        result = Image.new('RGB', (width*2+36, (height+39)*len(rows)+93), '#f3f5f0')
        draw = ImageDraw.Draw(result)
        draw.text((12, 10), title, font=titlefont, fill='#203d33')
        for i, heading in enumerate(headings): draw.text((12+i*(width+12), 53), heading, font=font, fill='#52695b')
        for row, (label, left, right) in enumerate(rows):
            top = 88+row*(height+39)
            for col, path in enumerate((left, right)):
                with Image.open(path) as source:
                    result.paste(source.convert('RGB').resize((width, height), Image.Resampling.LANCZOS), (12+col*(width+12), top))
            draw.text((12, top+height+5), label, font=font, fill='#203d33')
        result.save(args.output/filename, quality=88, optimize=True)

    views = [('residential-top', '住宅街区 · 俯视'), ('waterfront', '畅游阁—邕江大桥 · 北岸'),
             ('qingxiu', '青秀山 · 山脊与山脚'), ('arts', '艺术中心 · 场地')]
    sheet([(label, args.inspection/f'{view}-detail-clay-h14.png', args.inspection/f'{view}-detail-lit-h14.png')
           for view, label in views], 500, 313, ['中性照明灰模', '日间完整材质'], 'P0 / 当前城市视觉基线', 'city-contact.jpg')
    samples = [('residential', '住宅补楼：仅比较高度 ×1.55'), ('arts', '艺术中心：三个轴均 ×1.2'),
               ('zhenning', '镇宁炮台：水平 ×2.4，高度 ×3.72'), ('terrain', '山体显示高差：×1.35')]
    sheet([(label, args.scales/f'{name}-current.png', args.scales/f'{name}-neutral.png')
           for name, label in samples], 500, 375, ['当前生成倍率', '取消已知倍率（形体仍为近似）'], 'P0 / 同镜头独立比例样本', 'scale-contact.jpg')
    for source, name in [(args.baseline/'manifest.json', 'assets.json'),
                         (args.inspection/'report.json', 'browser.json'),
                         (args.deployment/'report.json', 'deployment.json'),
                         (args.scales/'manifest.json', 'scales.json')]:
        shutil.copy2(source, args.output/name)
    files = [ROOT/'lib/city/scene.ts', ROOT/'lib/city/inspection.ts', ROOT/'lib/city/inspection-materials.ts',
             ROOT/'app/inspect/page.tsx', ROOT/'scripts/check-inspection.mjs', ROOT/'blender/render_scale_baseline.py']
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (args.output/'tool-hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
    print(f'Visual baseline packaged: {args.output}')


if __name__ == '__main__': main()
