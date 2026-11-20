// Windows-only instrumentation for an isolated Orca test build.
#pragma once

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace OrcaBlackbox {

struct TraceHeader {
    char magic[8];
    std::uint32_t header_size, record_size, process_id, complete;
    std::uint64_t frequency, capacity, written, dropped, reserved;
};

struct TraceFrame {
    std::int64_t render_start, submit_start, submit_end;
    std::uint32_t canvas_type, canvas_id, flags, reserved;
};

static_assert(sizeof(TraceHeader) == 64);
static_assert(sizeof(TraceFrame) == 40);

class FrameTrace {
public:
    static FrameTrace* current() noexcept
    {
        static FrameTrace trace;
        return trace.header ? &trace : nullptr;
    }

    static std::int64_t now() noexcept
    {
        LARGE_INTEGER value{};
        QueryPerformanceCounter(&value);
        return value.QuadPart;
    }

    void record(const void* canvas, std::uint32_t type, bool overlay_only, bool swapped,
                std::int64_t begin, std::int64_t before, std::int64_t after) noexcept
    {
        if (GetCurrentThreadId() != owner_thread)
            return;
        if (header->written == capacity) {
            ++header->dropped;
            return;
        }
        std::uint32_t index = 0;
        for (; index < canvas_count && canvases[index] != canvas; ++index) {}
        if (index == canvas_count) {
            if (canvas_count == max_canvases) {
                ++header->dropped;
                return;
            }
            canvases[canvas_count++] = canvas;
        }
        const std::uint32_t flags = (overlay_only ? 1u : 0u) | (swapped ? 0u : 2u);
        frames[header->written] = {begin, before, after, type, index + 1, flags, 0};
        ++header->written;
    }

private:
    static constexpr std::uint64_t capacity = 262144;
    static constexpr DWORD mapped_bytes = sizeof(TraceHeader) + capacity * sizeof(TraceFrame);
    static constexpr std::uint32_t max_canvases = 32;
    HANDLE file = INVALID_HANDLE_VALUE;
    TraceHeader* header = nullptr;
    TraceFrame* frames = nullptr;
    DWORD owner_thread = 0;
    const void* canvases[max_canvases] = {};
    std::uint32_t canvas_count = 0;

    FrameTrace() noexcept
    {
        const wchar_t* path = _wgetenv(L"ORCA_BB_FRAME_TRACE_FILE");
        LARGE_INTEGER frequency{};
        if (!path || !*path || !QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0)
            return;
        file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                           CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE)
            return;
        HANDLE mapping = CreateFileMappingW(file, nullptr, PAGE_READWRITE, 0, mapped_bytes, nullptr);
        if (!mapping)
            return;
        header = static_cast<TraceHeader*>(MapViewOfFile(mapping, FILE_MAP_WRITE, 0, 0, mapped_bytes));
        CloseHandle(mapping);
        if (!header)
            return;
        *header = {};
        std::memcpy(header->magic, "ORCAFRM1", sizeof(header->magic));
        header->header_size = sizeof(TraceHeader);
        header->record_size = sizeof(TraceFrame);
        header->process_id = GetCurrentProcessId();
        header->frequency = static_cast<std::uint64_t>(frequency.QuadPart);
        header->capacity = capacity;
        frames = reinterpret_cast<TraceFrame*>(header + 1);
        owner_thread = GetCurrentThreadId();
    }

    ~FrameTrace()
    {
        if (header) {
            const auto used = sizeof(TraceHeader) + header->written * sizeof(TraceFrame);
            header->complete = 1;
            FlushViewOfFile(header, static_cast<SIZE_T>(used));
            UnmapViewOfFile(header);
            LARGE_INTEGER size{};
            size.QuadPart = static_cast<LONGLONG>(used);
            if (SetFilePointerEx(file, size, nullptr, FILE_BEGIN))
                SetEndOfFile(file);
        }
        if (file != INVALID_HANDLE_VALUE)
            CloseHandle(file);
    }
};

} // namespace OrcaBlackbox
