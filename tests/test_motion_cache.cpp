// Test of gpu/shim/bbport_motion_cache.h:
// a motion vertex shader's SPIR-V passes only when it holds this run's params, params + 16 and
// positions addresses as 64-bit constants (other constants beside them do not matter); another
// run's params address, a missing one, a zero address, a 32-bit constant with the right low word,
// other magic and code cut short do not pass. Motion code is told by Output variables at Locations
// 30 and 31; one of them alone, Inputs there, Outputs elsewhere and code cut short are not. The
// compile stall count: no line until the interval has passed since the window began, then one with
// the window's and the run's numbers, after which the window starts again and the run goes on
// adding; object motion counts only for new pipelines; a window with waits is pending until its
// line is written.
//
#include "gpu/shim/bbport_motion_cache.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <utility>
#include <vector>

static int failed = 0;
#define CHECK(c)                                                                                   \
    do {                                                                                           \
        if (!(c)) {                                                                                \
            std::printf("FAIL line %d: %s\n", __LINE__, #c);                                       \
            ++failed;                                                                              \
        }                                                                                          \
    } while (0)

using namespace BbMotionCache;
using u32 = std::uint32_t;
using u64 = std::uint64_t;

constexpr u64 Params = 0x1ae10000, Positions = 0x8c0600000;

// A module shaped like EmitVertexMotion's: a 64-bit and a 32-bit integer type, then constants.
static std::vector<u32> Module(std::initializer_list<u64> wide, std::initializer_list<u32> narrow = {}) {
    std::vector<u32> spv{0x07230203, 0x00010600, 0, 100, 0};
    spv.insert(spv.end(), {4u << 16 | 21, 1, 64, 0}); // OpTypeInt %1 64 0
    spv.insert(spv.end(), {4u << 16 | 21, 2, 32, 0}); // OpTypeInt %2 32 0
    u32 id = 10;
    for (const u64 v : wide) {
        spv.insert(spv.end(), {5u << 16 | 43, 1, id++, u32(v), u32(v >> 32)}); // OpConstant %1
    }
    for (const u32 v : narrow) {
        spv.insert(spv.end(), {4u << 16 | 43, 2, id++, v}); // OpConstant %2
    }
    spv.insert(spv.end(), {1u << 16 | 253}); // OpReturn
    return spv;
}

// A vertex module with variables at `locations` (location, storage class: 1 Input, 3 Output).
static std::vector<u32> Outputs(std::initializer_list<std::pair<u32, u32>> locations) {
    std::vector<u32> spv{0x07230203, 0x00010600, 0, 100, 0};
    u32 id = 20;
    for (const auto& [location, storage] : locations) {
        spv.insert(spv.end(), {4u << 16 | 71, id, 30, location}); // OpDecorate %id Location
        ++id;
    }
    spv.insert(spv.end(), {4u << 16 | 21, 1, 32, 0}); // OpTypeInt %1 32 0
    id = 20;
    for (const auto& [location, storage] : locations) {
        (void)location;
        spv.insert(spv.end(), {4u << 16 | 59, 1, id++, storage}); // OpVariable %1 %id storage
    }
    spv.insert(spv.end(), {1u << 16 | 253});
    return spv;
}

int main() {
    CHECK(HasMotionOutputs(Outputs({{0, 1}, {0, 3}, {30, 3}, {31, 3}})));
    CHECK(!HasMotionOutputs(Outputs({{31, 3}})));
    CHECK(!HasMotionOutputs(Outputs({{30, 3}, {5, 3}})));
    CHECK(!HasMotionOutputs(Outputs({{0, 1}, {1, 1}, {0, 3}, {1, 3}})));
    CHECK(!HasMotionOutputs(Outputs({{30, 1}, {31, 1}}))); // inputs there (a fragment shader's)
    CHECK(!HasMotionOutputs(Outputs({{29, 3}, {32, 3}})));
    auto cut_outputs = Outputs({{30, 3}});
    cut_outputs.resize(cut_outputs.size() - 3); // OpReturn and the variable's last words
    CHECK(!HasMotionOutputs(cut_outputs));
    CHECK(EmbedsAddresses(Module({Params, Params + 16, Positions}), Params, Positions));
    CHECK(EmbedsAddresses(Module({32, Positions, 16, Params + 16, Params}), Params, Positions));
    CHECK(!EmbedsAddresses(Module({0x1ac10000, 0x1ac10010, Positions}), Params, Positions));
    CHECK(!EmbedsAddresses(Module({Params, Positions}), Params, Positions));
    CHECK(!EmbedsAddresses(Module({Params, Params + 16}), Params, Positions));
    CHECK(!EmbedsAddresses(Module({Params, Params + 16}, {u32(Positions)}), Params, Positions));
    CHECK(!EmbedsAddresses(Module({0, 16, Positions}), 0, Positions));
    CHECK(!EmbedsAddresses(Module({Params, Params + 16, 0}), Params, 0));
    auto wrong_magic = Module({Params, Params + 16, Positions});
    wrong_magic[0] = 0x03022307;
    CHECK(!EmbedsAddresses(wrong_magic, Params, Positions));
    auto cut = Module({Params, Params + 16, Positions, 0x123400000000});
    CHECK(EmbedsAddresses(cut, Params, Positions));
    cut.resize(cut.size() - 3); // OpReturn and the last constant's value: it runs past the end
    CHECK(!EmbedsAddresses(cut, Params, Positions));
    auto zero_count = Module({Params, Params + 16, Positions});
    zero_count[5] = 21; // a word count of 0
    CHECK(!EmbedsAddresses(zero_count, Params, Positions));
    CHECK(!EmbedsAddresses(std::vector<u32>{0x07230203, 0x00010600}, Params, Positions));

    constexpr u64 Second = 1'000'000'000ull, Interval = 300 * Second;
    Stalls stalls;
    char line[384];
    CHECK(!stalls.Pending());
    CHECK(!stalls.Note(10 * Second, 41'000'000, true, true, Interval));
    CHECK(stalls.Pending());
    CHECK(!stalls.Note(100 * Second, 5'000'000, false, true, Interval)); // modules only: no pipeline
    CHECK(!stalls.Note(200 * Second, 70'000'000, true, false, Interval));
    CHECK(stalls.Note(310 * Second, 10'000'000, true, true, Interval));
    stalls.Format(line, sizeof(line), 310 * Second);
    CHECK(std::strcmp(line, "Compile stalls in the last 5.0 min: 4 waits, 0.13 s in all (longest 70 ms), "
                            "3 new pipelines (2 object motion); this run 4 waits, 0.13 s, 3 pipelines "
                            "(2 object motion)\n") == 0);
    CHECK(stalls.window.draws == 0 && stalls.window_start_ns == 310 * Second && !stalls.Pending());
    CHECK(!stalls.Note(400 * Second, 30'000'000, true, true, Interval));
    CHECK(stalls.Note(700 * Second, 20'000'000, false, false, Interval));
    stalls.Format(line, sizeof(line), 700 * Second);
    CHECK(std::strcmp(line, "Compile stalls in the last 6.5 min: 2 waits, 0.05 s in all (longest 30 ms), "
                            "1 new pipelines (1 object motion); this run 6 waits, 0.18 s, 4 pipelines "
                            "(3 object motion)\n") == 0);
    CHECK(stalls.run.longest_ns == 70'000'000);
    CHECK(!stalls.Note(760 * Second, 4'000'000, true, false, Interval) && stalls.Pending());
    stalls.Format(line, sizeof(line), 790 * Second); // the window the game ended in
    CHECK(std::strcmp(line, "Compile stalls in the last 1.5 min: 1 waits, 0.00 s in all (longest 4 ms), "
                            "1 new pipelines (0 object motion); this run 7 waits, 0.18 s, 5 pipelines "
                            "(3 object motion)\n") == 0);
    CHECK(!stalls.Pending());

    std::printf("motion cache: %s\n", failed ? "FAILED" : "PASS");
    return failed != 0;
}
