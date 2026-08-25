#pragma once

#include <set>
#include <string>
#include <string_view>
#include <utility>

namespace offline_translator {

inline constexpr double kDoubleCtrlCSeconds = 0.7;
inline constexpr double kMinDragDurationSeconds = 0.18;
inline constexpr int kDragThresholdPx = 16;

inline constexpr std::string_view kResultWindowClickToClose = "click_to_close";
inline constexpr std::string_view kResultWindowSelectable = "selectable";

bool should_show_selection_button(bool requires_ctrl, bool ctrl_pressed);
bool should_trigger_double_ctrl_c(
    double previous_press_time,
    double current_press_time,
    bool ctrl_pressed,
    bool enabled);
bool should_capture_selection(
    bool press_is_client,
    bool window_moved,
    double drag_distance,
    double drag_duration,
    bool is_double_click);

// Русский текст → en, иначе → ru. Без langdetect: эвристика по письму.
std::string detect_script_language(std::string_view text);
std::pair<std::string, std::string> choose_selection_direction(
    std::string_view text,
    const std::set<std::string>* installed_codes = nullptr);

std::string language_display_name(std::string_view code);

}  // пространство имён offline_translator
