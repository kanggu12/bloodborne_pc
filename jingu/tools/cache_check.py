#!/usr/bin/env python3
"""Count what bbport's pipeline cache (user/cache/<serial>) holds, against the loader of
bbport 1.9.2, 1.9.4 or 1.9.7 (video_core/renderer_vulkan/vk_pipeline_serialization.cpp). Read only.

PipelineCache::LoadGraphicsPipeline loads a pipeline's stages in SwStage order (Fragment first,
Vertex fourth) and returns as soon as one stage fails (a missing or old-version shader meta, a
motion vertex shader, a missing .spv, a permutation index conflict). 1.9.2 and 1.9.4 keep the stages
they already loaded, and the next cached pipeline uses them for any stage it lacks (bbport PR #97,
striped shadows, in the port itself since 1.9.5): "leaky" keys fail after an earlier stage loaded.
Since 1.9.5 a cache another build wrote is cleared at the start (build.bin, BB_SHADER_BUILD), so
another build's files do not stay.

Only the file-level failures are counted (meta missing or old, key version). Versions per build
(--build): 1.9.2 meta 8, binary 11, key 6; 1.9.4 meta 9, binary 12, key 7; 1.9.7 meta 9, binary 13,
key 7. Files of other builds count as old.

Object motion keys (key_kinds) are never preloaded by the official builds. The self-build with
the object motion pipeline commit sets them aside and loads them once the motion buffers exist, only with stages of
the kind the key asks for and a vertex shader that holds the run's buffer addresses (the log line
"Pipeline cache: N of M object motion pipelines preloaded"); the counts above do not model that.

  cache_check.py CACHE_DIR [--build 1.9.7]
"""
import argparse
import concurrent.futures
import struct
import sys
from pathlib import Path

# shader meta, shader binary, pipeline key
VERSIONS = {'1.9.2': (8, 11, 6), '1.9.4': (9, 12, 7), '1.9.7': (9, 13, 7)}
# Where a graphics key file holds GraphicsPipelineKey::motion_vectors (vk_graphics_pipeline.h): the
# 8-byte header (version, compute), then the key as it is in memory, the field at 336. On the
# 2026-10-25 cache it is 0 or 1, and 1 exactly where the key has 8 color attachments (object motion).
MOTION_FLAG = {'1.9.4': 344, '1.9.7': 344}
SHADER_META_VERSION, SHADER_BINARY_VERSION, PIPELINE_KEY_VERSION = VERSIONS['1.9.7']
STAGES = ('fragment', 'tess_control', 'tess_eval', 'vertex', 'geometry', 'compute')


def meta_state(cache, name):
    path = cache / f'{name}.meta'
    if not path.is_file():
        return 'missing'
    data = path.read_bytes()
    if len(data) < 8:
        return 'old'
    meta_version, binary_version = struct.unpack_from('<II', data)
    if binary_version != SHADER_BINARY_VERSION:
        return 'old'
    return 'ok' if meta_version == SHADER_META_VERSION else 'old'


def key_kinds(cache, build='1.9.7'):
    """{'keys', 'old', 'compute', 'motion', 'plain'}: the pipeline key files by what the build's loader
    does with them. 'old': another key version, never read (keys of older bbport builds stay in the
    folder); 'motion': object motion graphics keys (the object motion pipeline commit preloads those whose vertex
    shader holds the run's motion buffer addresses); 'plain': the other graphics keys. Keys cut short
    count as old. Without a known motion field (another build) object motion keys count as plain."""
    key_version = VERSIONS[build][2]
    flag = MOTION_FLAG.get(build)
    head = max(8, (flag or 0) + 4)

    def read(path):
        with open(path, 'rb') as f:
            return f.read(head)

    kinds = {'keys': 0, 'old': 0, 'compute': 0, 'motion': 0, 'plain': 0}
    # Thousands of small files on a Windows drive (drvfs): read side by side, about 5 ms each.
    with concurrent.futures.ThreadPoolExecutor(16) as pool:
        heads = list(pool.map(read, cache.glob('*.key')))
    for data in heads:
        kinds['keys'] += 1
        if len(data) < 8 or struct.unpack_from('<I', data, 0)[0] != key_version:
            kinds['old'] += 1
        elif struct.unpack_from('<I', data, 4)[0]:
            kinds['compute'] += 1
        elif len(data) < head:  # a graphics key cut short
            kinds['old'] += 1
        elif flag is not None and struct.unpack_from('<I', data, flag)[0]:
            kinds['motion'] += 1
        else:
            kinds['plain'] += 1
    return kinds


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cache', type=Path)
    p.add_argument('--build', choices=sorted(VERSIONS), default='1.9.7')
    a = p.parse_args()
    global SHADER_META_VERSION, SHADER_BINARY_VERSION, PIPELINE_KEY_VERSION
    SHADER_META_VERSION, SHADER_BINARY_VERSION, PIPELINE_KEY_VERSION = VERSIONS[a.build]
    cache = a.cache
    metas = sorted(cache.glob('*.meta'))
    old_metas = [m for m in metas if meta_state(cache, m.stem) == 'old']
    counts = {'graphics_full': 0, 'graphics_leaky': 0, 'graphics_fail_first': 0,
              'compute_full': 0, 'compute_fail': 0, 'old_key_version': 0, 'short_key': 0}
    for key in sorted(cache.glob('*.key')):
        data = key.read_bytes()
        if len(data) < 8:  # cut short (the game stopped while writing it)
            counts['short_key'] += 1
            continue
        version, is_compute = struct.unpack_from('<II', data, 0)
        if len(data) < (16 if is_compute else 56):  # a compute key holds one hash, a graphics key six
            counts['short_key'] += 1
            continue
        if version != PIPELINE_KEY_VERSION:
            counts['old_key_version'] += 1
            continue
        if is_compute:
            value, = struct.unpack_from('<Q', data, 8)
            ok = meta_state(cache, f'{value:#018x}') == 'ok'
            counts['compute_full' if ok else 'compute_fail'] += 1
            continue
        hashes = struct.unpack_from('<6Q', data, 8)
        loaded_before = False
        state = 'full'
        for stage, h in zip(STAGES, hashes):
            if not h:
                continue
            if meta_state(cache, f'{h:#018x}') == 'ok':
                loaded_before = True
                continue
            state = 'leaky' if loaded_before else 'fail_first'
            break
        counts[f'graphics_{state}'] += 1
    print(f'cache {cache}')
    print(f'  shader metas {len(metas)}, old version {len(old_metas)}')
    for k, v in counts.items():
        print(f'  {k:22s} {v}')
    kinds = key_kinds(cache, a.build)
    print(f'  object motion keys     {kinds["motion"]} (of the graphics keys above)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
