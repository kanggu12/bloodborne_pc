// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// bbport: the pipeline cache kept no object motion pipeline from one run to the next. Their
// vertex shader embeds the motion buffers' device addresses (EmitVertexMotion: params, params + 16
// and positions as 64-bit constants), so the loader refused all of them, and a run built nearly all
// of its new pipelines for object motion while the game was played (96 of 97 on 2026-10-25). The
// addresses stay the same from run to run while the build and the settings that allocate before
// the motion buffers do. EmbedsAddresses tells a cached motion vertex shader that holds this run's
// addresses; HasMotionOutputs tells motion code from plain code by the code itself (a binary can
// outlive its metadata: the cache's writes are not drained at exit).
// Stalls counts the draws and dispatches that waited for a compile, for one log line every few
// minutes.

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <span>
#include <vector>

namespace BbMotionCache {

/// Whether the SPIR-V holds `params`, `params + 16` and `positions` as 64-bit OpConstants. False
/// for a zero address and for code that is cut short.
inline bool EmbedsAddresses(std::span<const std::uint32_t> spv, std::uint64_t params,
                            std::uint64_t positions) {
    constexpr std::uint32_t Magic = 0x07230203, OpConstant = 43;
    if (!params || !positions || spv.size() < 5 || spv[0] != Magic) {
        return false;
    }
    bool found_params = false, found_second = false, found_positions = false;
    for (std::size_t i = 5; i < spv.size();) {
        const std::uint32_t count = spv[i] >> 16, opcode = spv[i] & 0xffff;
        if (count == 0 || count > spv.size() - i) {
            return false;
        }
        if (opcode == OpConstant && count == 5) { // type, id, then the value's two words, low first
            const std::uint64_t value = spv[i + 3] | std::uint64_t(spv[i + 4]) << 32;
            found_params |= value == params;
            found_second |= value == params + 16;
            found_positions |= value == positions;
        }
        i += count;
    }
    return found_params && found_second && found_positions;
}

/// Whether the SPIR-V declares Output variables at Locations 30 and 31, where a motion vertex
/// shader writes its current and previous clip positions (MotionVectors::CurrentLocation and
/// PreviousLocation). On the 2026-10-25 cache exactly the 281 vertex shaders with the motion buffer
/// addresses did, and none of the 1022 others. False for code that is cut short.
inline bool HasMotionOutputs(std::span<const std::uint32_t> spv) {
    constexpr std::uint32_t Magic = 0x07230203, OpDecorate = 71, OpVariable = 59;
    constexpr std::uint32_t Location = 30, Output = 3, Current = 30, Previous = 31;
    if (spv.size() < 5 || spv[0] != Magic) {
        return false;
    }
    // ids decorated at the two locations, and the Output variables
    std::vector<std::uint32_t> current, previous, outputs;
    for (std::size_t i = 5; i < spv.size();) {
        const std::uint32_t count = spv[i] >> 16, opcode = spv[i] & 0xffff;
        if (count == 0 || count > spv.size() - i) {
            return false;
        }
        if (opcode == OpDecorate && count >= 4 && spv[i + 2] == Location) {
            if (spv[i + 3] == Current) {
                current.push_back(spv[i + 1]);
            } else if (spv[i + 3] == Previous) {
                previous.push_back(spv[i + 1]);
            }
        } else if (opcode == OpVariable && count >= 4 && spv[i + 3] == Output) {
            outputs.push_back(spv[i + 2]);
        }
        i += count;
    }
    const auto output = [&](const std::vector<std::uint32_t>& ids) {
        return std::any_of(ids.begin(), ids.end(), [&](std::uint32_t id) {
            return std::find(outputs.begin(), outputs.end(), id) != outputs.end();
        });
    };
    return output(current) && output(previous);
}

/// Draws and dispatches that waited for a shader or pipeline compile: the current window and the
/// whole run. A window's line is written at the first wait after it ends; the window the game ends
/// in is written when its window closes (Pending, FlushCompileStalls).
struct Stalls {
    struct Count {
        std::uint32_t draws = 0, pipelines = 0, motion = 0;
        std::uint64_t ns = 0, longest_ns = 0;

        void Add(std::uint64_t waited_ns, bool pipeline, bool is_motion) {
            ++draws;
            pipelines += pipeline ? 1 : 0;
            motion += pipeline && is_motion ? 1 : 0;
            ns += waited_ns;
            longest_ns = std::max(longest_ns, waited_ns);
        }
    };
    Count window, run;
    std::uint64_t window_start_ns = 0;
    bool started = false;

    /// A draw at `now_ns` waited `waited_ns` (`pipeline`: it created one). Whether a line is due:
    /// `interval_ns` or more since the window began (Format writes it and starts the next window).
    bool Note(std::uint64_t now_ns, std::uint64_t waited_ns, bool pipeline, bool motion,
              std::uint64_t interval_ns) {
        if (!started) {
            started = true;
            window_start_ns = now_ns;
        }
        window.Add(waited_ns, pipeline, motion);
        run.Add(waited_ns, pipeline, motion);
        return now_ns - window_start_ns >= interval_ns;
    }

    /// The line for the window that ends at `now_ns`; the next window starts there.
    int Format(char* out, std::size_t size, std::uint64_t now_ns) {
        const int n = std::snprintf(
            out, size,
            "Compile stalls in the last %.1f min: %u waits, %.2f s in all (longest %.0f ms), %u new "
            "pipelines (%u object motion); this run %u waits, %.2f s, %u pipelines (%u object "
            "motion)\n",
            double(now_ns - window_start_ns) / 60e9, window.draws, double(window.ns) / 1e9,
            double(window.longest_ns) / 1e6, window.pipelines, window.motion, run.draws,
            double(run.ns) / 1e9, run.pipelines, run.motion);
        window = {};
        window_start_ns = now_ns;
        return n;
    }

    /// Whether the current window has waits no line holds yet.
    bool Pending() const {
        return window.draws != 0;
    }
};

} // namespace BbMotionCache
