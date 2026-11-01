// SPDX-License-Identifier: GPL-2.0-or-later
// bbport: the jobs' failed allocations from the render resource cache, and the times it was full
// at a job's first try, are counted; the cache can get up to 512 MiB of the port's direct memory (off
// by default).
//
// The resource cache the game's jobs at 0x26d0d30 allocate from is a 160 MiB range heap made at
// start-up (0x216b0f0). bbport 0.6 (deadinside28/bloodborne_pc, gpu/shim/bbport_guest_hooks.cpp,
// GPL-2.0-or-later) measured it at high frame rates: it fills while a cinematic's geometry is
// prepared, 20-40 KiB allocations fail (the jobs end with error 9) and the draws miss their
// resource tables; 320 MiB still failed on 4 MiB requests in the same load, 512 MiB held. Taken
// from the game's own allocator, the larger backing starved the memory areas load into (map pieces
// missing after a trip to the Hunter's Dream). As there, with BB_RENDER_RESOURCE_CACHE_MB above 160
// (up to 512) and BB_DMEM_EXTRA_MB at least as large, the game allocates its 160 MiB as always and
// right after it the cache gets that much of the port's direct memory past the game's size instead
// (runtime_extra_direct_map_like): the block and the size the range heap is then set up with (the
// creation record's +0x54) are replaced. With BB_RENDER_RESOURCE_CACHE_GUARD_MB (0..16, default 0)
// the port's block has that much more before and after the cache, mapped and unused (a test of
// whether reads just past the cache matter: the port's block is the last mapping in the guest
// address space). Off by default: with 512 MiB there, Yharnam (m24) was covered in a lime-green
// haze, gone with the game's cache (user test, 2026-10-24; cause unknown).
//
// The jobs' failed allocations are counted, the cache's and the other allocator's (the jobs'
// tracking blocks: after the job's own flush and retry, so each is a job that ends with error 9),
// and so are the times the cache was full at a job's first try (0x26d0d92 calls the cache's
// clean-up, 0x26aa860, which frees what was released, before the retry: a full cache makes no
// failure while the clean-up finds room). They are logged when they go up: from the flips and the
// hang check (when frames stop and on its 20 s look), a failure at once from the hang check and at
// most every 5 s from the flips, the full count alone at most once a minute from either. So a run
// shows whether the cache still runs out and how often it fills.

#include "bbport_render_cache.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <iterator>
#include <mutex>
#include <new>

#include "../bbgpu.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#endif

extern "C" int runtime_extra_direct_map_like(uint64_t size, uint64_t alignment, const void* like,
                                             void** out);

namespace BbRenderCache {
namespace {
using u64 = std::uint64_t;

/// Right after the cache creation's Allocate(size, 16) returns.
constexpr u64 Site = 0x216b21d;
/// mov esi, [r14 + 0x54]; mov edx, 16; mov rbx, rcx; call [rax + 0x58]; (the site) mov rcx, rbx;
/// mov [rcx + 0x10], rax; test rax, rax.
constexpr unsigned char Expected[] = {0x41, 0x8b, 0x76, 0x54, 0xba, 0x10, 0x00, 0x00, 0x00,
                                      0x48, 0x89, 0xcb, 0xff, 0x50, 0x58, 0x48, 0x89, 0xd9,
                                      0x48, 0x89, 0x41, 0x10, 0x48, 0x85, 0xc0};
constexpr u64 ExpectedAt = Site - 15;
constexpr std::uint32_t NativeBytes = 160u << 20;
constexpr std::size_t PageSize = 4096;
constexpr std::size_t BlockSize = 64 * 1024; // the counters' page, then the stubs' page

/// The jobs' allocations (0x26d0d30): `mov eax, 9; test reg, reg` after each, the result in reg.
struct FailureSite {
    u64 site;
    unsigned char test[3];
    int counter; ///< 0: the cache, 1: the tracking blocks
};
constexpr FailureSite FailureSites[] = {
    {0x26d0dac, {0x48, 0x85, 0xc9}, 0}, // the cache's range heap (rcx)
    {0x26d0e82, {0x4d, 0x85, 0xf6}, 1}, // a tracking block (r14)
    {0x26d0ebb, {0x4d, 0x85, 0xf6}, 1}, // a larger tracking block (r14)
};
/// The job's first Allocate from the cache returned null: it calls the cache's clean-up, then retries.
constexpr u64 CleanUpCall = 0x26d0d92;
constexpr u64 CleanUp = 0x26aa860;

/// What the stubs count: on the counters' page.
struct Counters {
    std::uint32_t failed[2] = {};
    std::uint32_t full = 0; ///< the cache full at a job's first try
};
Counters* counters = nullptr;
/// Which counts run: each needs all of its sites to be the expected code.
std::atomic<bool> counting_failures{false}, counting_full{false};
std::mutex report;
/// The counts last logged (failed[0], failed[1], full), and when.
std::uint32_t shown[3] = {};
std::chrono::steady_clock::time_point reported{};

/// A line when the counts went up: a failure from the flips at most every 5 s and from the hang
/// check at once, the full first tries alone at most every 60 s from either.
void Report(bool now) {
    const bool failures_on = counting_failures.load(std::memory_order_acquire);
    const bool full_on = counting_full.load(std::memory_order_acquire);
    if (!failures_on && !full_on) {
        return;
    }
    std::lock_guard lock(report); // read under it: a line never shows counts older than one before it
    const std::uint32_t c[3] = {failures_on ? __atomic_load_n(&counters->failed[0], __ATOMIC_RELAXED) : 0,
                                failures_on ? __atomic_load_n(&counters->failed[1], __ATOMIC_RELAXED) : 0,
                                full_on ? __atomic_load_n(&counters->full, __ATOMIC_RELAXED) : 0};
    const bool failures = c[0] != shown[0] || c[1] != shown[1];
    if (!failures && c[2] == shown[2]) {
        return;
    }
    const auto t = std::chrono::steady_clock::now();
    if (t - reported < std::chrono::seconds(failures ? (now ? 0 : 5) : 60)) {
        return;
    }
    reported = t;
    std::memcpy(shown, c, sizeof(shown));
    if (failures_on && full_on) {
        std::printf("Render resource cache: the jobs' failed allocations so far: %u from the cache, %u "
                    "tracking blocks; the cache full at a first try %u times\n",
                    unsigned(c[0]), unsigned(c[1]), unsigned(c[2]));
    } else if (failures_on) {
        std::printf("Render resource cache: the jobs' failed allocations so far: %u from the cache, %u "
                    "tracking blocks\n",
                    unsigned(c[0]), unsigned(c[1]));
    } else {
        std::printf("Render resource cache: the cache full at a first try %u times so far\n", unsigned(c[2]));
    }
}

std::uint32_t CacheBytes() {
    const char* env = std::getenv("BB_RENDER_RESOURCE_CACHE_MB");
    const long mb = env ? std::strtol(env, nullptr, 10) : 160;
    return std::uint32_t(std::clamp(mb, 160l, 512l)) << 20;
}

/// Mapped and unused before and after the cache in the port's block.
std::uint64_t GuardBytes() {
    const char* env = std::getenv("BB_RENDER_RESOURCE_CACHE_GUARD_MB");
    const long mb = env ? std::strtol(env, nullptr, 10) : 0;
    return std::uint64_t(std::clamp(mb, 0l, 16l)) << 20;
}

void* __attribute__((sysv_abi)) PortBacking(void* allocated, unsigned char* record) {
    std::uint32_t size = 0;
    std::memcpy(&size, record + 0x54, sizeof(size));
    if (!allocated) {
        std::printf("Render resource cache: the game's allocation failed: left as it is\n");
        return allocated;
    }
    if (size != NativeBytes) {
        std::printf("Render resource cache: the game makes it with %u MiB, not 160: left as it is\n",
                    size >> 20);
        return allocated;
    }
    const std::uint32_t bytes = CacheBytes();
    const std::uint64_t guard = GuardBytes();
    void* block = nullptr;
    // The block takes the protection and memory type of the game's mapping that holds its own (only
    // the game's own queries see them: the host maps both of its kinds read-write, the GPU gets the
    // range alone).
    if (const int error = runtime_extra_direct_map_like(bytes + 2 * guard, 64u << 10, allocated, &block);
        error || !block) {
        std::printf("Render resource cache: no port memory for %u MiB (error %#x): the game's "
                    "160 MiB\n",
                    unsigned((bytes + 2 * guard) >> 20), unsigned(error));
        return allocated;
    }
    void* cache = static_cast<unsigned char*>(block) + guard;
    // The record can be a stack object (bbport 0.6): not necessarily in the runtime's map.
    std::memcpy(record + 0x54, &bytes, sizeof(bytes));
    std::printf("Render resource cache: %u MiB of the port's memory at %p (%u MiB unused before and "
                "after it; the game's 160 MiB at %p stays allocated)\n",
                bytes >> 20, cache, unsigned(guard >> 20), allocated);
    return cache;
}

/// A block within 512 MiB below the image (rel32 jumps and RIP-relative operands reach it).
unsigned char* MapNear(unsigned char* image) {
    const auto base = reinterpret_cast<std::uintptr_t>(image);
    for (std::uintptr_t k = 1; k <= 64; ++k) {
        const std::uintptr_t hint = base - k * (8ull << 20);
        if (hint >= base) {
            break;
        }
#ifdef _WIN32
        if (void* p = VirtualAlloc(reinterpret_cast<void*>(hint), BlockSize, MEM_RESERVE | MEM_COMMIT,
                                   PAGE_READWRITE)) {
            return static_cast<unsigned char*>(p);
        }
#else
        void* p = mmap(reinterpret_cast<void*>(hint), BlockSize, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (p != MAP_FAILED) {
            return static_cast<unsigned char*>(p);
        }
#endif
    }
    return nullptr;
}

bool ProtectStubs(unsigned char* stubs) {
#ifdef _WIN32
    DWORD old = 0;
    if (!VirtualProtect(stubs, PageSize, PAGE_EXECUTE_READ, &old)) {
        return false;
    }
    FlushInstructionCache(GetCurrentProcess(), stubs, PageSize);
    return true;
#else
    return mprotect(stubs, PageSize, PROT_READ | PROT_EXEC) == 0;
#endif
}
} // namespace

void PatchImage(unsigned char* image, std::uint64_t size) {
    if (!image || size < FailureSites[2].site + 8) {
        return;
    }
    unsigned char* block = MapNear(image);
    if (!block) {
        std::printf("Render resource cache: no memory next to the game's code: the game's 160 MiB, "
                    "failed allocations not counted\n");
        return;
    }
    counters = new (block) Counters{};
    unsigned char* stubs = block + PageSize;
    // Each change is kept with the bytes it replaced, to be undone if the stubs cannot run.
    struct Undo {
        u64 site;
        unsigned char bytes[8];
        std::size_t length;
    } undo[std::size(FailureSites) + 2];
    std::size_t changes = 0, used = 0;
    int counted = 0;
    bool full = false;
    for (const FailureSite& f : FailureSites) {
        Undo& u = undo[changes];
        u.site = f.site, u.length = 8;
        std::memcpy(u.bytes, image + f.site, u.length);
        if (CountZeroResults(image, f.site, f.test, stubs + used, &counters->failed[f.counter])) {
            ++changes, ++counted, used += CountStubSize;
        }
    }
    {
        Undo& u = undo[changes];
        u.site = CleanUpCall, u.length = 5;
        std::memcpy(u.bytes, image + CleanUpCall, u.length);
        if (CountCalls(image, CleanUpCall, CleanUp, stubs + used, &counters->full)) {
            ++changes, used += CallCountStubSize;
            full = true;
        }
    }
    const bool failures = counted == int(std::size(FailureSites));
    const std::uint32_t bytes = CacheBytes();
    const char* cache = "the game's 160 MiB";
    char port[64];
    if (bytes != NativeBytes) {
        Undo& u = undo[changes];
        u.site = Site, u.length = sizeof(SiteBytes);
        std::memcpy(u.bytes, image + Site, u.length);
        if (std::memcmp(image + ExpectedAt, Expected, sizeof(Expected)) != 0) {
            cache = "the game's 160 MiB (the creation is not the expected code)";
        } else if (DetourAfterAllocate(image, Site, stubs + used, PortBacking)) {
            ++changes, used += StubSize;
            std::snprintf(port, sizeof(port), "%u MiB of the port's memory when the game makes it",
                          bytes >> 20);
            cache = port;
        } else {
            cache = "the game's 160 MiB (the stub is out of reach)";
        }
    }
    if (changes && !ProtectStubs(stubs)) {
        for (std::size_t i = 0; i < changes; ++i) { // nothing has run them yet
            std::memcpy(image + undo[i].site, undo[i].bytes, undo[i].length);
        }
        std::printf("Render resource cache: the stubs' page could not be made executable: the "
                    "game's 160 MiB, failed allocations not counted\n");
        return;
    }
    counting_failures.store(failures, std::memory_order_release);
    counting_full.store(full, std::memory_order_release);
    std::printf("Render resource cache: %s; the jobs' failed allocations %s; the cache's full first "
                "tries %s\n",
                cache, failures ? "are counted" : "are not counted (other code)",
                full ? "are counted" : "are not counted (other code)");
}

void OnFlip() {
    Report(false);
}

void OnStall() {
    Report(true);
}

} // namespace BbRenderCache

extern "C" void bbgpu_render_cache_patch(unsigned char* image, uint64_t size) {
    BbRenderCache::PatchImage(image, size);
}
