"""Read U1 fixture filament badges from live Add Mix controls at the pinned DPI."""
from collections import Counter

# Digit masks sampled at 100% scale from the harvested Add Mix census.
# Accept a known shape only. An unsupported scale or ambiguous badge stops input.
GLYPHS = {
    1: "011 111 001 001 001 001 001 001 001",
    2: "011100 110110 000010 000010 000110 001100 011000 110000 111111",
    3: "001110 010011 000011 000011 001110 000011 000001 110001 011110",
    4: "0001100 0001100 0011000 0011000 0110110 0100110 1111111 0000110 0000110",
    5: "11111 11000 11000 11110 11111 00011 00001 10011 11110",
}
SLOTS = {glyph: slot for slot, glyph in GLYPHS.items()}
BADGE_SIZE = 20
ROW_HEIGHT = 30


def badge_slot(image):
    if image.size != (BADGE_SIZE, BADGE_SIZE):
        raise ValueError("native_mix_badge_size")
    pixels = tuple(image.convert("RGB").getdata())
    background, count = Counter(pixels).most_common(1)[0]
    if count < 310:
        raise ValueError("native_mix_badge_background")
    marks = {(index % BADGE_SIZE, index // BADGE_SIZE) for index, pixel in enumerate(pixels)
             if max(abs(value - base) for value, base in zip(pixel, background)) >= 85}
    if not marks or any(not 2 <= x < 18 or not 2 <= y < 18 for x, y in marks):
        raise ValueError("native_mix_badge_bounds")
    xs, ys = zip(*marks)
    glyph = " ".join("".join("1" if (x, y) in marks else "0" for x in range(min(xs), max(xs) + 1))
                     for y in range(min(ys), max(ys) + 1))
    if glyph not in SLOTS:
        raise ValueError("native_mix_badge_unknown")
    return SLOTS[glyph]


def popup_slots(image):
    width, height = image.size
    if width < 180 or height % ROW_HEIGHT or not 1 <= height // ROW_HEIGHT <= len(GLYPHS):
        raise ValueError("native_mix_badge_popup_layout")
    slots = [badge_slot(image.crop((26, row + 5, 46, row + 25)))
             for row in range(0, height, ROW_HEIGHT)]
    if len(set(slots)) != len(slots):
        raise ValueError("native_mix_badge_duplicate")
    return slots


def selected_slot(rect, capture):
    left, top, right, bottom = rect
    if bottom - top != ROW_HEIGHT or right - left < 180:
        raise ValueError("native_mix_badge_combo_layout")
    with capture(bbox=(left + 29, top + 5, left + 49, top + 25)) as badge:
        return badge_slot(badge)
