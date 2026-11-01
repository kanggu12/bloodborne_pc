// Test of gpu/shim/bbport_render_cache.h: a function shaped
// like the cache creation (the allocator called through its vtable, then the site's instructions)
// runs as before until it is detoured; after it, the backing function gets the allocated block and
// the creation record on a 16-byte aligned stack (also when the site's stack is not), its result
// is what the function stores and goes on with, and the callee-saved registers and the stack are
// as before; other bytes, or a stub out of reach, are refused with nothing written. The jobs'
// failure count: a function shaped like a job's allocation check returns the same with the count
// as without it, and the count goes up only for a zero result. The full first tries: a function
// that calls a clean-up when its first try found nothing returns the same through the counting
// stub, and the count is the clean-up's calls; a call elsewhere, other bytes or a stub out of reach
// are refused with nothing written.
#include "gpu/shim/bbport_render_cache.h"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <iterator>

#ifdef _WIN32
#define NOMINMAX // the build compiles the GPU library so too
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <sys/mman.h>
#endif

static int failed = 0;
#define CHECK(c)                                                                                   \
    do {                                                                                           \
        if (!(c)) {                                                                                \
            std::printf("FAIL line %d: %s\n", __LINE__, #c);                                       \
            ++failed;                                                                              \
        }                                                                                          \
    } while (0)

using namespace BbRenderCache;
using u64 = std::uint64_t;

static unsigned char* Executable(std::size_t size) {
#ifdef _WIN32
    return static_cast<unsigned char*>(
        VirtualAlloc(nullptr, size, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE));
#else
    void* p = mmap(nullptr, size, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS,
                   -1, 0);
    return p == MAP_FAILED ? nullptr : static_cast<unsigned char*>(p);
#endif
}

// The game's allocator: Allocate(size, alignment) at vtable + 0x58.
static unsigned char game_block[64];
static std::uint32_t requested_size = 0, requested_alignment = 0;
static void* __attribute__((sysv_abi)) Allocate(void*, std::uint32_t size, std::uint32_t alignment) {
    requested_size = size;
    requested_alignment = alignment;
    return game_block;
}
struct Allocator {
    void* const* vtable;
};

// The backing: records what it got, replaces the block and the record's size when asked to.
static unsigned char port_block[64];
static void* seen_block = nullptr;
static unsigned char* seen_record = nullptr;
static bool aligned = false, replace = true;
static int calls = 0;
static void* __attribute__((sysv_abi)) TestBacking(void* allocated, unsigned char* record) {
    ++calls;
    aligned = reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0;
    seen_block = allocated;
    seen_record = record;
    if (!replace) {
        return allocated;
    }
    const std::uint32_t bytes = 512u << 20;
    std::memcpy(record + 0x54, &bytes, sizeof(bytes));
    return port_block;
}

// u64 Create(object, record, allocator): the allocator call and the site as at 0x216b20e, then
// what the registers hold afterwards into the object: r14 +0x18, r15 +0x20, r13 +0x28, rbx +0x30,
// rbp +0x38, rsp +0x40. `misaligned`: the stack is 8 bytes off around the site.
struct Shape {
    std::size_t site;
    std::size_t size;
};
static Shape Build(unsigned char* at, bool misaligned) {
    std::size_t n = 0;
    const auto put = [&](std::initializer_list<unsigned char> bytes) {
        for (const unsigned char b : bytes) {
            at[n++] = b;
        }
    };
    const auto put64 = [&](u64 v) {
        std::memcpy(at + n, &v, 8);
        n += 8;
    };
    put({0x55, 0x48, 0x89, 0xe5});                         // push rbp; mov rbp, rsp
    put({0x41, 0x57, 0x41, 0x56, 0x41, 0x55, 0x41, 0x54}); // push r15, r14, r13, r12
    put({0x53, 0x48, 0x83, 0xec, 0x08});                   // push rbx; sub rsp, 8
    put({0x49, 0x89, 0xfc});                               // mov r12, rdi (the object)
    put({0x49, 0x89, 0xf6});                               // mov r14, rsi (the record)
    put({0x49, 0xbf});                                     // movabs r15, ..
    put64(0x1515151515151515ull);
    put({0x49, 0xbd}); // movabs r13, ..
    put64(0x1313131313131313ull);
    put({0x48, 0x89, 0xd7});       // mov rdi, rdx (the allocator)
    put({0x48, 0x8b, 0x07});       // mov rax, [rdi]
    put({0x41, 0x8b, 0x76, 0x54}); // mov esi, [r14 + 0x54]
    put({0xba, 0x10, 0, 0, 0});    // mov edx, 16
    put({0x4c, 0x89, 0xe1});       // mov rcx, r12
    put({0x48, 0x89, 0xcb});       // mov rbx, rcx
    put({0xff, 0x50, 0x58});       // call [rax + 0x58]
    if (misaligned) {
        put({0x48, 0x83, 0xec, 0x08}); // sub rsp, 8
    }
    const std::size_t site = n;
    put({0x48, 0x89, 0xd9, 0x48, 0x89, 0x41, 0x10}); // mov rcx, rbx; mov [rcx + 0x10], rax
    put({0x48, 0x85, 0xc0});                         // test rax, rax
    if (misaligned) {
        put({0x48, 0x83, 0xc4, 0x08}); // add rsp, 8
    }
    put({0x4d, 0x89, 0x74, 0x24, 0x18}); // mov [r12 + 0x18], r14
    put({0x4d, 0x89, 0x7c, 0x24, 0x20}); // mov [r12 + 0x20], r15
    put({0x4d, 0x89, 0x6c, 0x24, 0x28}); // mov [r12 + 0x28], r13
    put({0x49, 0x89, 0x5c, 0x24, 0x30}); // mov [r12 + 0x30], rbx
    put({0x49, 0x89, 0x6c, 0x24, 0x38}); // mov [r12 + 0x38], rbp
    put({0x49, 0x89, 0x64, 0x24, 0x40}); // mov [r12 + 0x40], rsp
    put({0x48, 0x83, 0xc4, 0x08, 0x5b}); // add rsp, 8; pop rbx
    put({0x41, 0x5c, 0x41, 0x5d, 0x41, 0x5e, 0x41, 0x5f, 0x5d, 0xc3}); // pop r12-r15, rbp; ret
    return {site, n};
}

using Create = u64 __attribute__((sysv_abi)) (*)(unsigned char* object, unsigned char* record,
                                                 Allocator* allocator);

struct Run {
    u64 result;
    u64 object[9];
};
static Run Call(Create create, unsigned char* record, Allocator* allocator) {
    Run r{};
    unsigned char object[0x48] = {};
    r.result = create(object, record, allocator);
    std::memcpy(r.object, object, sizeof(object));
    return r;
}

// What the function stores and keeps: the block it went on with, the registers as they were.
static bool Kept(const Run& r, const void* block, const unsigned char* record) {
    return r.result == reinterpret_cast<u64>(block) && r.object[2] == reinterpret_cast<u64>(block) &&
           r.object[3] == reinterpret_cast<u64>(record) && r.object[4] == 0x1515151515151515ull &&
           r.object[5] == 0x1313131313131313ull && r.object[7] - r.object[8] == 0x30;
}

int main() {
    unsigned char* x = Executable(0x8000);
    CHECK(x != nullptr);
    if (!x) {
        return 1;
    }
    void* vtable[12] = {};
    vtable[0x58 / 8] = reinterpret_cast<void*>(&Allocate);
    Allocator allocator{vtable};
    const std::uint32_t native = 160u << 20;

    for (const bool misaligned : {false, true}) {
        unsigned char* fn = x + (misaligned ? 0x1000 : 0);
        unsigned char* stub = fn + 0x800;
        const Shape shape = Build(fn, misaligned);
        const Create create = reinterpret_cast<Create>(fn);
        unsigned char record[0x60] = {};
        std::memcpy(record + 0x54, &native, 4);

        // As the game has it.
        Run r = Call(create, record, &allocator);
        CHECK(Kept(r, game_block, record));
        CHECK(requested_size == native && requested_alignment == 16);

        // Detoured: the backing's block, the record's new size, the registers as they were.
        calls = 0;
        replace = true;
        CHECK(DetourAfterAllocate(fn, shape.site, stub, TestBacking));
        r = Call(create, record, &allocator);
        CHECK(calls == 1 && seen_block == game_block && seen_record == record);
        CHECK(aligned);
        CHECK(Kept(r, port_block, record));
        std::uint32_t size = 0;
        std::memcpy(&size, record + 0x54, 4);
        CHECK(size == 512u << 20);

        // A backing that keeps the block: as the game has it.
        replace = false;
        std::memcpy(record + 0x54, &native, 4);
        r = Call(create, record, &allocator);
        CHECK(Kept(r, game_block, record));
        std::memcpy(&size, record + 0x54, 4);
        CHECK(size == native);

        // Many runs: the stack stays balanced.
        replace = true;
        bool same = true;
        for (int i = 0; i < 20000 && same; ++i) {
            r = Call(create, record, &allocator);
            same = Kept(r, port_block, record) && aligned;
        }
        CHECK(same);

        // The jump replaced the site's 7 bytes, nothing after them.
        CHECK(fn[shape.site] == 0xe9 && fn[shape.site + 5] == 0x66 && fn[shape.site + 6] == 0x90);
        CHECK(fn[shape.site + 7] == 0x48 && fn[shape.site + 8] == 0x85 && fn[shape.site + 9] == 0xc0);
    }

    // rbx is the object after the site (mov rcx, rbx: the store goes to the object).
    {
        unsigned char record[0x60] = {};
        std::memcpy(record + 0x54, &native, 4);
        unsigned char object[0x48] = {};
        reinterpret_cast<Create>(x)(object, record, &allocator);
        u64 rbx = 0;
        std::memcpy(&rbx, object + 0x30, 8);
        CHECK(rbx == reinterpret_cast<u64>(object));
    }

    // Other bytes at the site, or a stub out of reach: refused, nothing written.
    unsigned char* other = x + 0x2000;
    const Shape shape = Build(other, false);
    other[shape.site + 2] = 0xda; // mov rdx, rbx: not the expected instruction
    unsigned char before[0x900];
    std::memcpy(before, other, sizeof(before));
    CHECK(!DetourAfterAllocate(other, shape.site, other + 0x800, TestBacking));
    CHECK(std::memcmp(before, other, sizeof(before)) == 0);
    unsigned char* intact = x + 0x3000;
    const Shape s2 = Build(intact, false);
    std::memcpy(before, intact, s2.size);
    unsigned char* distant = reinterpret_cast<unsigned char*>(reinterpret_cast<std::uintptr_t>(intact) +
                                                              (u64(3) << 30));
    CHECK(!DetourAfterAllocate(intact, s2.site, distant, TestBacking)); // (not `far`: a macro in windows.h)
    CHECK(std::memcmp(before, intact, s2.size) == 0);

    // The failure count: `mov eax, 9; test reg, reg; je; xor eax, eax`, the result in rcx or r14.
    using Check = std::uint32_t __attribute__((sysv_abi)) (*)(u64 result);
    struct Shape2 {
        std::initializer_list<unsigned char> code;
        std::size_t site;
        unsigned char test[3];
    };
    const Shape2 shapes[] = {
        {{0x48, 0x89, 0xf9,                   // mov rcx, rdi
          0xb8, 0x09, 0x00, 0x00, 0x00,       // mov eax, 9 (the site)
          0x48, 0x85, 0xc9,                   // test rcx, rcx
          0x74, 0x02, 0x31, 0xc0, 0xc3},      // je ret; xor eax, eax; ret
         3, {0x48, 0x85, 0xc9}},
        {{0x41, 0x56,                         // push r14
          0x49, 0x89, 0xfe,                   // mov r14, rdi
          0xb8, 0x09, 0x00, 0x00, 0x00,       // mov eax, 9 (the site)
          0x4d, 0x85, 0xf6,                   // test r14, r14
          0x74, 0x02, 0x31, 0xc0,             // je pop; xor eax, eax
          0x41, 0x5e, 0xc3},                  // pop r14; ret
         5, {0x4d, 0x85, 0xf6}},
    };
    std::uint32_t* counter = reinterpret_cast<std::uint32_t*>(x + 0x3e00);
    for (const Shape2& sh : shapes) {
        unsigned char* fn = x + 0x3800;
        std::memset(x + 0x3800, 0xcc, 0x600);
        std::copy(sh.code.begin(), sh.code.end(), fn);
        const Check check = reinterpret_cast<Check>(fn);
        CHECK(check(0x1234) == 0 && check(0) == 9);
        *counter = 0;
        CHECK(CountZeroResults(fn, sh.site, sh.test, fn + 0x400, counter));
        bool same = true;
        for (int i = 0; i < 1000 && same; ++i) {
            same = check(u64(i % 4) << 40) == (i % 4 ? 0u : 9u);
        }
        CHECK(same);
        CHECK(*counter == 250);
        CHECK(fn[sh.site] == 0xe9 && fn[sh.site + 8] == 0x74); // the je after the 8 bytes stays
        // Other bytes: refused, nothing written.
        std::copy(sh.code.begin(), sh.code.end(), fn);
        fn[sh.site + 1] = 0x08; // mov eax, 8
        unsigned char kept[0x40];
        std::memcpy(kept, fn, sizeof(kept));
        CHECK(!CountZeroResults(fn, sh.site, sh.test, fn + 0x400, counter));
        CHECK(std::memcmp(kept, fn, sizeof(kept)) == 0);
    }

    // The full first tries: `call clean-up` (e8 rel32) goes through the counting stub.
    using Try = std::uint32_t __attribute__((sysv_abi)) (*)(u64 found);
    unsigned char* job = x + 0x4000;
    std::memset(job, 0xcc, 0x800);
    const unsigned char tries[] = {
        0x48, 0x85, 0xff,             // test rdi, rdi
        0x75, 0x06,                   // jne past the call
        0xe8, 0xf6, 0x00, 0x00, 0x00, // call job + 0x100 (the site)
        0xc3,                         // ret: the clean-up's eax
        0x31, 0xc0, 0xc3,             // xor eax, eax; ret
    };
    const unsigned char cleanup[] = {0xb8, 0x07, 0x00, 0x00, 0x00, 0xc3}; // mov eax, 7; ret
    std::copy(std::begin(tries), std::end(tries), job);
    std::copy(std::begin(cleanup), std::end(cleanup), job + 0x100);
    const Try attempt = reinterpret_cast<Try>(job);
    CHECK(attempt(0) == 7 && attempt(1) == 0);
    std::uint32_t* full = counter + 1;
    *full = 0;
    CHECK(CountCalls(job, 5, 0x100, job + 0x400, full));
    bool same_tries = true;
    for (int i = 0; i < 1000 && same_tries; ++i) {
        same_tries = attempt(u64(i % 4)) == (i % 4 ? 0u : 7u);
    }
    CHECK(same_tries);
    CHECK(*full == 250);
    CHECK(job[5] == 0xe8 && job[10] == 0xc3);
    CHECK(job[0x400] == 0xf0 && job[0x401] == 0xff && job[0x402] == 0x05 && job[0x407] == 0xe9); // lock inc; jmp
    std::copy(std::begin(tries), std::end(tries), job);
    unsigned char kept_tries[0x20];
    std::memcpy(kept_tries, job, sizeof(kept_tries));
    CHECK(!CountCalls(job, 5, 0x104, job + 0x400, full)); // the call goes elsewhere
    CHECK(!CountCalls(job, 4, 0x100, job + 0x400, full)); // not a call there
    job[5] = 0xe9; // a jump with the same displacement
    CHECK(!CountCalls(job, 5, 0x100, job + 0x400, full));
    job[5] = 0xe8;
    unsigned char* beyond = reinterpret_cast<unsigned char*>(reinterpret_cast<std::uintptr_t>(job) + (u64(3) << 30));
    CHECK(!CountCalls(job, 5, 0x100, beyond, full));
    CHECK(std::memcmp(kept_tries, job, sizeof(kept_tries)) == 0);

    std::printf("render cache detour: %s\n", failed ? "FAILED" : "PASS");
    return failed != 0;
}
