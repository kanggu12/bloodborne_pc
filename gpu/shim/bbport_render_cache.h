// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

// bbport: the render resource cache's backing (bbport_render_cache.cpp).
namespace BbRenderCache {

/// Called with the block the game's allocator returned and the cache's creation record; returns
/// the block the cache gets.
using Backing = void* __attribute__((sysv_abi)) (*)(void* allocated, unsigned char* record);

/// Detours the cache creation in the game's image (after the patches, while it is writable).
void PatchImage(unsigned char* image, std::uint64_t size);
/// VideoOut showed a frame: a line when the jobs' failed allocations went up (a few seconds apart).
void OnFlip();
/// No frame for a while, or the hang check's periodic look: a line when they went up, now.
void OnStall();

/// mov rcx, rbx; mov [rcx + 0x10], rax: the cache creation right after Allocate(size, 16) returns.
inline constexpr unsigned char SiteBytes[] = {0x48, 0x89, 0xd9, 0x48, 0x89, 0x41, 0x10};
inline constexpr std::size_t StubSize = 47;

/// Replaces the instructions at image + site (SiteBytes) with a jump to a stub written at `stub`
/// (within 2 GiB): it calls `backing(rax, r14)` on a 16-byte aligned stack, takes its result as
/// rax, runs the replaced instructions and jumps back after them. rbx, rbp, r12-r15 and the stack
/// are as before (the callee keeps them, the stub restores rsp); the other registers the call may
/// change (rdi, rsi, r11 and the rest) were changed by the allocator call just before the site.
/// Nothing is written and false is returned when the bytes are other ones or the stub is out of
/// reach.
inline bool DetourAfterAllocate(unsigned char* image, std::uint64_t site, unsigned char* stub,
                                Backing backing) {
    unsigned char* at = image + site;
    if (std::memcmp(at, SiteBytes, sizeof(SiteBytes)) != 0) {
        return false;
    }
    const auto rel32 = [](const unsigned char* end, const unsigned char* target, std::int32_t& out) {
        const auto d = std::int64_t(reinterpret_cast<std::uintptr_t>(target) -
                                    reinterpret_cast<std::uintptr_t>(end));
        if (d < INT32_MIN || d > INT32_MAX) {
            return false;
        }
        out = std::int32_t(d);
        return true;
    };
    std::int32_t to_stub = 0, back = 0;
    if (!rel32(at + 5, stub, to_stub) || !rel32(stub + StubSize, at + sizeof(SiteBytes), back)) {
        return false;
    }
    unsigned char code[StubSize] = {
        0x49, 0x89, 0xe3,                   // mov r11, rsp
        0x48, 0x83, 0xe4, 0xf0,             // and rsp, -16
        0x48, 0x83, 0xec, 0x08,             // sub rsp, 8
        0x41, 0x53,                         // push r11: aligned at the call
        0x48, 0x89, 0xc7,                   // mov rdi, rax (the allocated block)
        0x4c, 0x89, 0xf6,                   // mov rsi, r14 (the creation record)
        0x48, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, // movabs rax, backing
        0xff, 0xd0,                         // call rax
        0x48, 0x8b, 0x24, 0x24,             // mov rsp, [rsp]
        0x48, 0x89, 0xd9,                   // mov rcx, rbx (replaced)
        0x48, 0x89, 0x41, 0x10,             // mov [rcx + 0x10], rax (replaced)
        0xe9, 0, 0, 0, 0,                   // jmp back
    };
    const auto function = reinterpret_cast<std::uintptr_t>(backing);
    std::memcpy(code + 21, &function, sizeof(function));
    std::memcpy(code + StubSize - 4, &back, sizeof(back));
    std::memcpy(stub, code, StubSize);
    unsigned char jump[sizeof(SiteBytes)] = {0xe9, 0, 0, 0, 0, 0x66, 0x90}; // jmp stub; nop
    std::memcpy(jump + 1, &to_stub, sizeof(to_stub));
    std::memcpy(at, jump, sizeof(jump));
    return true;
}

/// `mov eax, 9; test reg, reg` at image + site (an allocation's result in reg, error 9 set
/// beforehand; a jump on zero follows): a jump to a 25-byte stub at `stub` that adds one to the
/// 32-bit `counter` (lock inc) when reg is zero, then runs the two instructions and jumps back
/// after them, so the flags are the test's again and eax is 9 as before. `test` is the test's 3
/// bytes; the stub, the counter and the site within 2 GiB of each other. False, and nothing
/// written, for other bytes.
inline constexpr std::size_t CountStubSize = 25;
inline bool CountZeroResults(unsigned char* image, std::uint64_t site, const unsigned char (&test)[3],
                             unsigned char* stub, std::uint32_t* counter) {
    static constexpr unsigned char mov9[] = {0xb8, 0x09, 0x00, 0x00, 0x00};
    unsigned char* at = image + site;
    if (std::memcmp(at, mov9, sizeof(mov9)) != 0 || std::memcmp(at + 5, test, sizeof(test)) != 0) {
        return false;
    }
    const auto rel32 = [](const unsigned char* end, const void* target, std::int32_t& out) {
        const auto d = std::int64_t(reinterpret_cast<std::uintptr_t>(target) -
                                    reinterpret_cast<std::uintptr_t>(end));
        if (d < INT32_MIN || d > INT32_MAX) {
            return false;
        }
        out = std::int32_t(d);
        return true;
    };
    std::int32_t to_counter = 0, back = 0, to_stub = 0;
    if (!rel32(stub + 12, counter, to_counter) || !rel32(stub + CountStubSize, at + 8, back) ||
        !rel32(at + 5, stub, to_stub)) {
        return false;
    }
    unsigned char code[CountStubSize] = {
        test[0], test[1], test[2],    // test reg, reg
        0x75, 0x07,                   // jnz past the count
        0xf0, 0xff, 0x05, 0, 0, 0, 0, // lock inc dword [rip + counter]
        0xb8, 0x09, 0x00, 0x00, 0x00, // mov eax, 9 (replaced)
        test[0], test[1], test[2],    // test reg, reg (replaced)
        0xe9, 0, 0, 0, 0,             // jmp back
    };
    std::memcpy(code + 8, &to_counter, sizeof(to_counter));
    std::memcpy(code + CountStubSize - 4, &back, sizeof(back));
    std::memcpy(stub, code, CountStubSize);
    unsigned char jump[8] = {0xe9, 0, 0, 0, 0, 0x0f, 0x1f, 0x00}; // jmp stub; a 3-byte nop
    std::memcpy(jump + 1, &to_stub, sizeof(to_stub));
    std::memcpy(at, jump, sizeof(jump));
    return true;
}

/// `call target` (e8 rel32) at image + site: the call goes to a 12-byte stub at `stub` that adds one
/// to the 32-bit `counter` (lock inc) and jumps on to `target`, which returns to the caller as
/// before (the flags a call may change anyway). `target` is an offset in the image; the stub, the
/// counter, the site and the target within 2 GiB of each other. False, and nothing written, when the
/// bytes are other ones or the call goes elsewhere.
inline constexpr std::size_t CallCountStubSize = 12;
inline bool CountCalls(unsigned char* image, std::uint64_t site, std::uint64_t target, unsigned char* stub,
                       std::uint32_t* counter) {
    unsigned char* at = image + site;
    std::int32_t now = 0;
    std::memcpy(&now, at + 1, sizeof(now));
    if (at[0] != 0xe8 || at + 5 + now != image + target) {
        return false;
    }
    const auto rel32 = [](const unsigned char* end, const void* to, std::int32_t& out) {
        const auto d = std::int64_t(reinterpret_cast<std::uintptr_t>(to) -
                                    reinterpret_cast<std::uintptr_t>(end));
        if (d < INT32_MIN || d > INT32_MAX) {
            return false;
        }
        out = std::int32_t(d);
        return true;
    };
    std::int32_t to_counter = 0, to_target = 0, to_stub = 0;
    if (!rel32(stub + 7, counter, to_counter) || !rel32(stub + CallCountStubSize, image + target, to_target) ||
        !rel32(at + 5, stub, to_stub)) {
        return false;
    }
    unsigned char code[CallCountStubSize] = {
        0xf0, 0xff, 0x05, 0, 0, 0, 0, // lock inc dword [rip + counter]
        0xe9, 0, 0, 0, 0,             // jmp target
    };
    std::memcpy(code + 3, &to_counter, sizeof(to_counter));
    std::memcpy(code + 8, &to_target, sizeof(to_target));
    std::memcpy(stub, code, CallCountStubSize);
    std::memcpy(at + 1, &to_stub, sizeof(to_stub));
    return true;
}

} // namespace BbRenderCache
