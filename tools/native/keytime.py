#!/usr/bin/env python3
# license:BSD-3-Clause
"""鍵を押す合図（`0x20e`）の時刻を、firmware の道と native の口で並べる。

native の音が実機より早い／遅いと、値がぜんぶ合っていても波形の相関が
落ちる。どの音が何サンプルずれているかを、ここで直に見る
（doc/native-engine.md の 6.117 はこの道具で見つけた）。

  python tools/native/keytime.py <ROM のディレクトリ> <試験の名前> <秒数> [--pairs] [--usb]

`--pairs` を付けると 1 件ずつ並べる。付けなければずれの分布だけ出す。
`--usb` は USB の口で鳴らす（プラグインの既定。バイトの速さが DIN と違う）。
試験の MIDI は `build/tests/<名前>.mid`（`tools/make_test_midi.py` が作る）。
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build'
# 記録の 1 行。`s=` は鳴っているサンプル番号
LINE = re.compile(r'^(N |W )?00800000 ([0-9a-f]{4}) ([0-9a-f]{4}).*s=(\d+)')
# 押す鍵を並べるレジスタ（64 スロットを 16 本ずつ 4 本で）
MASK = {0x1cf: 0, 0x1ce: 1, 0x18f: 2, 0x18e: 3}
KEYON = 0x20e                       # ここへ 1 を書くと、並べた鍵が鳴り出す


def keyons(roms, mid, out, tag, native, secs, usb=False):
    """1 回鳴らして、(サンプル, [スロット]) の並びを返す"""
    trc = out / ('keytime_%s.txt' % tag)
    cmd = [str(BUILD / 'render'), str(roms), str(mid),
           str(out / ('keytime_%s.wav' % tag)), str(secs),
           '--bootcache', '--trace-swp', str(trc)]
    if usb:
        cmd.append('--usb')
    if native:
        cmd.append('--native-engine')
    env = dict(os.environ)
    env['SMU2000_NO_VOICECACHE'] = '1'   # 毎回まっさらから
    env['SMU2000_CUT_EXACT'] = '1'
    subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True)
    cur = [0, 0, 0, 0]
    out_rows = []
    with open(trc, errors='replace') as f:
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            r, v, s = int(m.group(2), 16), int(m.group(3), 16), int(m.group(4))
            if r in MASK:
                cur[MASK[r]] = v
            elif r == KEYON:
                mk = cur[0] | (cur[1] << 16) | (cur[2] << 32) | (cur[3] << 48)
                if mk:
                    out_rows.append((s, [i for i in range(64) if (mk >> i) & 1]))
                cur = [0, 0, 0, 0]
    return out_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('roms')
    ap.add_argument('name')
    ap.add_argument('secs')
    ap.add_argument('--pairs', action='store_true')
    ap.add_argument('--usb', action='store_true')
    a = ap.parse_args()

    mid = BUILD / 'tests' / (a.name + '.mid')
    if not mid.exists():
        sys.exit('%s が無い。先に python tools/make_test_midi.py' % mid)
    out = BUILD / 'tests'
    fw = keyons(a.roms, mid, out, 'fw', False, a.secs, a.usb)
    nv = keyons(a.roms, mid, out, 'nv', True, a.secs, a.usb)
    print('%s  実機 %d 回 / native %d 回' % (a.name, len(fw), len(nv)))

    if a.pairs:
        print('%-34s %s' % ('実機', 'native'))
        for i in range(max(len(fw), len(nv))):
            sa = '%8d %s' % fw[i] if i < len(fw) else ''
            sb = '%8d %s' % nv[i] if i < len(nv) else ''
            d = '  %+d' % (nv[i][0] - fw[i][0]) if i < len(fw) and i < len(nv) else ''
            print('%-34s %-34s%s' % (sa[:33], sb[:33], d))
        return

    n = min(len(fw), len(nv))
    d = sorted(nv[i][0] - fw[i][0] for i in range(n))
    if not d:
        return
    print('ずれ（サンプル）  最小 %d  中央 %d  最大 %d  平均 %.1f'
          % (d[0], d[n // 2], d[-1], sum(d) / float(n)))
    hist = {}
    for x in d:
        hist[x] = hist.get(x, 0) + 1
    for k in sorted(hist):
        print('  %+5d サンプル : %d 回' % (k, hist[k]))


if __name__ == '__main__':
    main()
