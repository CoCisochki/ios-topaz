import sys
import os
import struct
import time

simg_path = 'ios16-root.simg'
img_path = 'ios16-root.img'

MAGIC = 0xed26ff3a
RAW, FILL, DONT_CARE = 0xcac1, 0xcac2, 0xcac3

def main():
    t0 = time.time()
    with open(simg_path, 'rb') as fs, open(img_path, 'rb') as fr:
        hdr = fs.read(28)
        magic, major, minor, file_hdr_sz, chunk_hdr_sz, blk_sz, total_blks, total_chunks, crc = struct.unpack('<IHHHHIIII', hdr)
        print(f'simg blk_sz={blk_sz}, total_blks={total_blks}, total_chunks={total_chunks}')
        
        cur_block = 0
        diff_ranges = []
        cur_diff_start = None
        cur_diff_count = 0
        total_diff_blocks = 0
        last_print = t0
        
        for ch_idx in range(total_chunks):
            ch_hdr = fs.read(12)
            chunk_type, reserved, chunk_sz, total_sz = struct.unpack('<HHII', ch_hdr)
            data_sz = total_sz - 12
            
            blocks_left = chunk_sz
            chunk_base = cur_block
            
            if chunk_type == RAW:
                step_blks = (8 * 1024 * 1024) // blk_sz
                while blocks_left > 0:
                    blks_to_read = min(blocks_left, step_blks)
                    bytes_to_read = blks_to_read * blk_sz
                    simg_bytes = fs.read(bytes_to_read)
                    fr.seek(cur_block * blk_sz)
                    img_bytes = fr.read(bytes_to_read)
                    if simg_bytes != img_bytes:
                        for b in range(blks_to_read):
                            if simg_bytes[b*blk_sz:(b+1)*blk_sz] != img_bytes[b*blk_sz:(b+1)*blk_sz]:
                                blk_idx = cur_block + b
                                if cur_diff_start is not None and blk_idx == cur_diff_start + cur_diff_count:
                                    cur_diff_count += 1
                                else:
                                    if cur_diff_start is not None:
                                        diff_ranges.append((cur_diff_start, cur_diff_count))
                                    cur_diff_start = blk_idx
                                    cur_diff_count = 1
                                total_diff_blocks += 1
                    cur_block += blks_to_read
                    blocks_left -= blks_to_read
            elif chunk_type == FILL:
                fill_val = fs.read(4)
                step_blks = (8 * 1024 * 1024) // blk_sz
                while blocks_left > 0:
                    blks_to_read = min(blocks_left, step_blks)
                    expected = fill_val * (blk_sz // 4) * blks_to_read
                    fr.seek(cur_block * blk_sz)
                    img_bytes = fr.read(blks_to_read * blk_sz)
                    if expected != img_bytes:
                        for b in range(blks_to_read):
                            exp_blk = fill_val * (blk_sz // 4)
                            if img_bytes[b*blk_sz:(b+1)*blk_sz] != exp_blk:
                                blk_idx = cur_block + b
                                if cur_diff_start is not None and blk_idx == cur_diff_start + cur_diff_count:
                                    cur_diff_count += 1
                                else:
                                    if cur_diff_start is not None:
                                        diff_ranges.append((cur_diff_start, cur_diff_count))
                                    cur_diff_start = blk_idx
                                    cur_diff_count = 1
                                total_diff_blocks += 1
                    cur_block += blks_to_read
                    blocks_left -= blks_to_read
            elif chunk_type == DONT_CARE:
                step_blks = (8 * 1024 * 1024) // blk_sz
                zero_blk = b'\x00' * blk_sz
                while blocks_left > 0:
                    blks_to_read = min(blocks_left, step_blks)
                    fr.seek(cur_block * blk_sz)
                    img_bytes = fr.read(blks_to_read * blk_sz)
                    if any(img_bytes):
                        for b in range(blks_to_read):
                            if img_bytes[b*blk_sz:(b+1)*blk_sz] != zero_blk:
                                blk_idx = cur_block + b
                                if cur_diff_start is not None and blk_idx == cur_diff_start + cur_diff_count:
                                    cur_diff_count += 1
                                else:
                                    if cur_diff_start is not None:
                                        diff_ranges.append((cur_diff_start, cur_diff_count))
                                    cur_diff_start = blk_idx
                                    cur_diff_count = 1
                                total_diff_blocks += 1
                    cur_block += blks_to_read
                    blocks_left -= blks_to_read
            
            now = time.time()
            if now - last_print >= 2.0 or ch_idx == total_chunks - 1:
                pct = cur_block / total_blks * 100.0
                print(f'\rScanning: {pct:.1f}% ({ch_idx+1}/{total_chunks} chunks, diff: {total_diff_blocks * blk_sz / (1024*1024):.2f} MB)', end='', flush=True)
                last_print = now

        if cur_diff_start is not None:
            diff_ranges.append((cur_diff_start, cur_diff_count))

        print()
        dt = time.time() - t0
        diff_bytes = total_diff_blocks * blk_sz
        print(f'Diff scan finished in {dt:.1f}s: {len(diff_ranges)} range(s), {total_diff_blocks} blocks ({diff_bytes / (1024*1024):.2f} MB)')
        
        with open('diff_ranges.txt', 'w') as out:
            for s, c in diff_ranges:
                out.write(f'{s} {c}\n')
        print(f'Saved diff ranges to diff_ranges.txt')

if __name__ == '__main__':
    main()
