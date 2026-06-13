#!/usr/bin/env python3
"""将 Obsidian [[wikilinks]] 转换为标准 Markdown [text](path.md) 链接"""

import re
import os
from pathlib import Path

DOCS_DIR = Path("docs")
WIKI_RE = re.compile(r'\[\[([^\]]+)\]\]')

def build_index():
    idx = {}
    name_idx = {}
    for f in DOCS_DIR.rglob("*.md"):
        rel = str(f.relative_to(DOCS_DIR))
        stem = rel[:-3] if rel.endswith('.md') else rel
        idx[stem] = rel
        name = os.path.splitext(os.path.basename(rel))[0]
        if name not in name_idx:
            name_idx[name] = rel
    return idx, name_idx

def slugify(text):
    text = text.strip()
    text = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    return text.lower()

def resolve_link(path_part, current_file_rel, stem_idx, name_idx):
    if not path_part:
        return None
    cur_dir = os.path.dirname(current_file_rel) or '.'

    candidates = []
    candidates.append(os.path.normpath(os.path.join(cur_dir, path_part)))
    candidates.append(os.path.normpath(path_part))

    for c in list(candidates):
        alt = c.replace('\\', '/')
        if alt != c:
            candidates.append(alt)

    for c in candidates:
        if c in stem_idx:
            return stem_idx[c]

    name = os.path.splitext(os.path.basename(path_part))[0]
    if name and name in name_idx:
        return name_idx[name]

    for key, val in stem_idx.items():
        if key.endswith('/' + path_part) or key == path_part:
            return val

    return None

def convert_file(filepath, stem_idx, name_idx):
    rel = str(filepath.relative_to(DOCS_DIR))
    content = filepath.read_text(encoding='utf-8')
    changed = False

    def replacer(m):
        nonlocal changed
        full = m.group(1)

        # 处理 Markdown 表格中的 pipe 转义
        # \\| (双重转义) 和 \| (单次转义) → |
        full = full.replace('\\\\|', '|').replace('\\|', '|')

        # 解析: path#anchor|alias
        display = None
        anchor = None
        path = full

        if '|' in path:
            path, display = path.rsplit('|', 1)

        if '#' in path:
            path, anchor = path.rsplit('#', 1)
            if not path:
                path = ''

        # 同页锚点
        if not path:
            text = display if display else anchor
            changed = True
            return f'[{text}](#{slugify(anchor)})'

        # 解析文件路径
        target_rel = resolve_link(path, rel, stem_idx, name_idx)

        if target_rel is None:
            # 无法解析 → 去掉 [[]]，保留纯文本
            text = display if display else path
            changed = True
            return text

        cur_dir = os.path.dirname(rel)
        from_path = '.' if cur_dir == '' else cur_dir
        try:
            link_path = os.path.relpath(target_rel, from_path)
        except ValueError:
            link_path = target_rel
        link_path = link_path.replace('\\', '/')

        text = display if display else os.path.splitext(os.path.basename(target_rel))[0]

        if anchor:
            link = f'{link_path}#{slugify(anchor)}'
        else:
            link = link_path

        changed = True
        return f'[{text}]({link})'

    new_content = WIKI_RE.sub(replacer, content)

    if changed:
        filepath.write_text(new_content, encoding='utf-8')
        print(f"  ✓ {rel}")

    return changed

def main():
    stem_idx, name_idx = build_index()
    print(f"索引 {len(stem_idx)} 个文件")

    total = 0
    changed = 0
    for f in sorted(DOCS_DIR.rglob("*.md")):
        total += 1
        if convert_file(f, stem_idx, name_idx):
            changed += 1

    print(f"\n处理 {total} 个文件，修改 {changed} 个")

if __name__ == '__main__':
    main()
