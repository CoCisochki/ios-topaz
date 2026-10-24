import sys
import os
import struct

MAGIC = 0xed26ff3a
RAW, DONT_CARE = 0xcac1, 0xcac3

def main():
    img_path = 'ios16-root.img'
    ranges_path = 'diff_ranges.txt'
    out_simg = 'delta.simg'
    bs = 4096
    
    total_size = os.path.getsize(img_path)
    total_blks = total_size // bs
    
    ranges = []
    with open(ranges_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                s, c = line.split()
                ranges.append((int(s), int(c)))
                
    runs = []
    cur_pos = 0
    for s, c in ranges:
        if s > cur_pos:
            runs.append((False, s - cur_pos))
        runs.append((True, c))
        cur_pos = s + c
    if cur_pos < total_blks:
        runs.append((False, total_blks - cur_pos))
        
    with open(img_path, 'rb') as fn, open(out_simg, 'wb') as out:
        out.write(struct.pack('<IHHHHIIII', MAGIC, 1, 0, 28, 12, bs, total_blks, len(runs), 0))
        pos = 0
        total_raw = 0
        for is_raw, count in runs:
            if is_raw:
                out.write(struct.pack('<HHII', RAW, 0, count, 12 + count * bs))
                fn.seek(pos * bs)
                left = count * bs
                total_raw += left
                while left > 0:
                    chunk = fn.read(min(left, 8 * 1024 * 1024))
                    out.write(chunk)
                    left -= len(chunk)
            else:
                out.write(struct.pack('<HHII', DONT_CARE, 0, count, 12))
            pos += count
            
    print(f'Generated {out_simg}: {total_raw / 1024:.1f} KB in {len(ranges)} RAW runs across {total_blks} blocks')

if __name__ == '__main__':
    main()
