#include "offline_translator/app_settings.hpp"
#include "offline_translator/argos_model_manager.hpp"
#include "offline_translator/autostart.hpp"
#include "offline_translator/clipboard.hpp"
#include "offline_translator/firefox_model_manager.hpp"
#include "offline_translator/hotkey.hpp"
#include "offline_translator/language_store.hpp"
#include "offline_translator/nllb_model_manager.hpp"
#include "offline_translator/selection.hpp"
#include "offline_translator/translation_application.hpp"
#include "offline_translator/window_policy.hpp"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef EM_SETCUEBANNER
#define EM_SETCUEBANNER 0x1501
#endif
#include <windows.h>
#include <shellapi.h>
#include <commctrl.h>
#include <gdiplus.h>

#pragma comment(lib, "gdiplus.lib")

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cwchar>
#include <exception>
#include <filesystem>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <fstream>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace {

constexpr UINT kTranslateMessage = WM_APP + 1;
constexpr UINT kStatusMessage = WM_APP + 2;
constexpr UINT kPackageProgressMessage = WM_APP + 3;
constexpr UINT kPackageDoneMessage = WM_APP + 4;
constexpr UINT kPackageIndexMessage = WM_APP + 5;
constexpr UINT kTrayMessage = WM_APP + 10;
constexpr UINT kSelectionResultMessage = WM_APP + 11;
constexpr UINT kSelectionPollTimer = 1;
constexpr UINT kSelectionButtonHideTimer = 2;
constexpr int kEngineCombo = 1001;
constexpr int kSourceEdit = 1002;
constexpr int kTranslateButton = 1003;
constexpr int kResultEdit = 1004;
constexpr int kSourceLanguageCombo = 1005;
constexpr int kTargetLanguageCombo = 1006;
constexpr int kPackagesButton = 1007;
constexpr int kStatusLabel = 1008;
constexpr int kSettingsButton = 1009;
constexpr int kPackageList = 1101;
constexpr int kPackageInstallButton = 1102;
constexpr int kPackageUninstallButton = 1103;
constexpr int kPackageCloseButton = 1104;
constexpr int kPackageSearchEdit = 1105;
constexpr int kPackageArchCombo = 1106;
constexpr int kSettingsPopupCtrl = 1201;
constexpr int kSettingsDoubleCtrlC = 1202;
constexpr int kSettingsClickToClose = 1203;
constexpr int kSettingsSelectable = 1204;
constexpr int kSettingsAutostart = 1205;
constexpr int kSettingsHotkeyEdit = 1206;
constexpr int kSettingsSave = 1207;
constexpr int kSettingsCancel = 1208;
constexpr int kResultCopyButton = 1302;
constexpr int kResultCloseButton = 1303;
constexpr int kShowWindowHotkey = 2001;
constexpr int kTrayOpen = 3001;
constexpr int kTrayAutostart = 3002;
constexpr int kTrayExit = 3003;
constexpr int kDefaultWindowWidth = 560;
constexpr int kDefaultWindowHeight = 450;
constexpr int kMinWindowWidth = 520;
constexpr int kMinWindowHeight = 400;

HWND g_engine_combo = nullptr;
HWND g_source_edit = nullptr;
HWND g_translate_button = nullptr;
HWND g_result_edit = nullptr;
HWND g_source_language_combo = nullptr;
HWND g_target_language_combo = nullptr;
HWND g_packages_button = nullptr;
HWND g_settings_button = nullptr;
HWND g_status_label = nullptr;
HWND g_package_list = nullptr;
HWND g_package_install = nullptr;
HWND g_package_uninstall = nullptr;
HWND g_package_status = nullptr;
HWND g_package_search = nullptr;
HWND g_package_arch_caption = nullptr;
HWND g_package_arch_combo = nullptr;
HWND g_settings_popup_ctrl = nullptr;
HWND g_settings_double_ctrl_c = nullptr;
HWND g_settings_click_to_close = nullptr;
HWND g_settings_selectable = nullptr;
HWND g_settings_autostart = nullptr;
HWND g_settings_hotkey_edit = nullptr;
HWND g_selection_button = nullptr;
HWND g_result_popup = nullptr;
HWND g_popup_result_edit = nullptr;
HWND g_popup_copy_button = nullptr;
bool g_button_uses_icon = false;
constexpr int kSelectionIconSize = 40;
constexpr COLORREF kPopupBackground = RGB(242, 242, 242);
constexpr COLORREF kPopupBorder = RGB(0, 0, 0);
constexpr COLORREF kPopupHeaderText = RGB(51, 51, 51);
constexpr COLORREF kButtonFace = RGB(222, 222, 222);
constexpr COLORREF kButtonHover = RGB(204, 204, 204);
bool g_smoke_mode = false;bool g_start_minimized = false;
bool g_tray_added = false;
HICON g_tray_icon = nullptr;
NOTIFYICONDATAW g_tray_data{};

struct StatusPayload {
    std::wstring text;
    bool failed{false};
};

void sel_log(const std::string& line);

struct PackageRow {
    bool nllb{false};
    bool firefox{false};
    std::string architecture;
    std::string from_code;
    std::string to_code;
    std::wstring title;
    bool installed{false};
    bool incomplete{false};
};

struct GuiRuntime {
    std::mutex mutex;
    offline_translator::TranslationSession session;
    offline_translator::AppSettings settings;
    std::atomic<bool> busy{false};
    std::atomic<bool> closing{false};
    std::atomic<bool> packages_busy{false};
    std::atomic<bool> selection_busy{false};
    HWND main_window{nullptr};
    HWND packages_window{nullptr};
    HWND settings_window{nullptr};
    std::vector<PackageRow> package_rows;
    std::vector<PackageRow> package_rows_all;
};

struct SelectionMonitor {
    bool press_active{false};
    bool was_pressed{false};
    bool was_c_pressed{false};
    bool press_is_client{false};
    bool gesture_invalid{false};
    int press_x{0};
    int press_y{0};
    int last_up_x{0};
    int last_up_y{0};
    HWND press_hwnd{nullptr};
    HWND last_up_hwnd{nullptr};
    POINT press_origin{};
    double press_time{0};
    double last_up_time{0};
    double last_ctrl_c_time{0};
    std::wstring selected_text;
};

SelectionMonitor g_selection;

std::shared_ptr<GuiRuntime> g_runtime;

std::string to_utf8(const std::wstring& text) {
    if (text.empty()) {
        return {};
    }
    const int size = WideCharToMultiByte(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        nullptr,
        0,
        nullptr,
        nullptr);
    std::string result(size, '\0');
    WideCharToMultiByte(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        result.data(),
        size,
        nullptr,
        nullptr);
    return result;
}

std::wstring from_utf8(const std::string& text) {
    if (text.empty()) {
        return {};
    }
    const int size = MultiByteToWideChar(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        nullptr,
        0);
    std::wstring result(size, L'\0');
    MultiByteToWideChar(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        result.data(),
        size);
    return result;
}

std::wstring control_text(HWND control) {
    const int length = GetWindowTextLengthW(control);
    std::wstring text(length + 1, L'\0');
    GetWindowTextW(control, text.data(), length + 1);
    text.resize(length);
    return text;
}

std::wstring user_profile() {
    wchar_t buffer[MAX_PATH]{};
    const DWORD length = GetEnvironmentVariableW(
        L"USERPROFILE",
        buffer,
        static_cast<DWORD>(std::size(buffer)));
    return length == 0 ? L"." : std::wstring(buffer, length);
}

std::wstring executable_directory() {
    std::array<wchar_t, MAX_PATH> buffer{};
    const DWORD length = GetModuleFileNameW(
        nullptr,
        buffer.data(),
        static_cast<DWORD>(buffer.size()));
    if (length == 0 || length >= buffer.size()) {
        return {};
    }
    std::wstring path(buffer.data(), length);
    const auto separator = path.find_last_of(L"\\/");
    return separator == std::wstring::npos ? L"." : path.substr(0, separator);
}

std::wstring model_root(bool use_nllb) {
    const std::wstring portable_root = executable_directory() + L"\\data\\" +
        (use_nllb ? L"nllb-200" : L"argos-packages");
    if (GetFileAttributesW(portable_root.c_str()) != INVALID_FILE_ATTRIBUTES) {
        return portable_root;
    }
    const std::wstring profile = user_profile();
    return use_nllb
        ? profile + L"\\.local\\share\\offline-translator\\nllb-200"
        : profile + L"\\.local\\share\\argos-translate\\packages";
}

std::filesystem::path model_root_path(bool use_nllb) {
    return std::filesystem::path(model_root(use_nllb));
}

std::wstring firefox_model_root() {
    const std::wstring portable_root =
        executable_directory() + L"\\data\\firefox-models";
    if (GetFileAttributesW(portable_root.c_str()) != INVALID_FILE_ATTRIBUTES) {
        return portable_root;
    }
    const std::wstring profile = user_profile();
    return profile + L"\\.local\\share\\offline-translator\\firefox-models";
}

std::filesystem::path model_root_for_kind(
    offline_translator::EngineKind kind) {
    switch (kind) {
        case offline_translator::EngineKind::nllb:
            return model_root_path(true);
        case offline_translator::EngineKind::firefox:
            return std::filesystem::path(firefox_model_root());
        case offline_translator::EngineKind::argos:
            break;
    }
    return model_root_path(false);
}

std::wstring clipboard_text() {
    offline_translator::Win32Clipboard clipboard;
    return clipboard.get_text();
}

double monotonic_seconds() {
    using clock = std::chrono::steady_clock;
    static const auto epoch = clock::now();
    return std::chrono::duration<double>(clock::now() - epoch).count();
}

bool key_down(int virtual_key) {
    return (GetAsyncKeyState(virtual_key) & 0x8000) != 0;
}

std::size_t language_count() {
    return offline_translator::supported_languages().size();
}

const std::vector<std::wstring>& combo_language_names() {
    static const std::vector<std::wstring> names = [] {
        std::vector<std::wstring> result;
        result.reserve(offline_translator::supported_languages().size());
        for (const auto& entry : offline_translator::supported_languages()) {
            result.push_back(from_utf8(entry.name));
        }
        return result;
    }();
    return names;
}

int language_index(std::string_view code) {
    const auto& languages = offline_translator::supported_languages();
    for (std::size_t index = 0; index < languages.size(); ++index) {
        if (languages[index].code == code) {
            return static_cast<int>(index);
        }
    }
    return -1;
}

std::string selected_language(HWND combo) {
    const LRESULT index = SendMessageW(combo, CB_GETCURSEL, 0, 0);
    if (index < 0 || index >= static_cast<LRESULT>(language_count())) {
        throw std::runtime_error("Не выбран язык");
    }
    return offline_translator::supported_languages()[
        static_cast<std::size_t>(index)].code;
}

offline_translator::EngineKind selected_engine() {
    const LRESULT index = SendMessageW(g_engine_combo, CB_GETCURSEL, 0, 0);
    if (index == 2) {
        return offline_translator::EngineKind::firefox;
    }
    return index == 1 ? offline_translator::EngineKind::nllb
                      : offline_translator::EngineKind::argos;
}

int engine_combo_index(offline_translator::EngineKind kind) {
    switch (kind) {
        case offline_translator::EngineKind::nllb:
            return 1;
        case offline_translator::EngineKind::firefox:
            return 2;
        case offline_translator::EngineKind::argos:
            break;
    }
    return 0;
}

void select_language(HWND combo, const std::string& code, int fallback) {
    const int index = language_index(code);
    SendMessageW(
        combo,
        CB_SETCURSEL,
        index >= 0 ? index : fallback,
        0);
}

void set_status(const std::wstring& text) {
    if (g_status_label) {
        SetWindowTextW(g_status_label, text.c_str());
    }
}

void post_payload(HWND window, UINT message, std::wstring text, bool failed) {
    if (!window || !IsWindow(window) || (g_runtime && g_runtime->closing)) {
        return;
    }
    auto* payload = new StatusPayload{std::move(text), failed};
    if (!PostMessageW(
            window,
            message,
            0,
            reinterpret_cast<LPARAM>(payload))) {
        delete payload;
    }
}

void post_status(HWND window, const std::string& text) {
    post_payload(window, kStatusMessage, from_utf8(text), false);
}

void fill_language_combos() {
    SendMessageW(g_source_language_combo, CB_RESETCONTENT, 0, 0);
    SendMessageW(g_target_language_combo, CB_RESETCONTENT, 0, 0);
    for (const auto& name : combo_language_names()) {
        SendMessageW(
            g_source_language_combo,
            CB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(name.c_str()));
        SendMessageW(
            g_target_language_combo,
            CB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(name.c_str()));
    }
}

void apply_settings_to_ui(const offline_translator::AppSettings& settings) {
    SendMessageW(
        g_engine_combo,
        CB_SETCURSEL,
        engine_combo_index(
            offline_translator::engine_kind_from_settings(settings.engine)),
        0);
    fill_language_combos();
    select_language(g_source_language_combo, settings.source_language, 0);
    select_language(
        g_target_language_combo,
        settings.target_language,
        language_count() > 1 ? 1 : 0);
}

void collect_window_size(HWND window, offline_translator::AppSettings& settings) {
    RECT bounds{};
    if (GetWindowRect(window, &bounds)) {
        settings.window_width = bounds.right - bounds.left;
        settings.window_height = bounds.bottom - bounds.top;
    }
}

offline_translator::AppSettings current_settings(HWND window) {
    offline_translator::AppSettings settings =
        g_runtime ? g_runtime->settings : offline_translator::AppSettings{};
    settings.engine =
        offline_translator::settings_engine_name(selected_engine());
    settings.source_language = selected_language(g_source_language_combo);
    settings.target_language = selected_language(g_target_language_combo);
    collect_window_size(window, settings);
    return settings;
}

void persist_settings(HWND window) {
    if (g_smoke_mode || !g_engine_combo) {
        return;
    }
    try {
        auto settings = current_settings(window);
        offline_translator::save_settings(settings);
        if (g_runtime) {
            g_runtime->settings = settings;
        }
    } catch (const std::exception&) {
        // Сохранение не должно ронять интерфейс.
    }
}

void set_main_busy(bool busy) {
    EnableWindow(g_translate_button, !busy);
    EnableWindow(g_engine_combo, !busy);
    EnableWindow(g_source_language_combo, !busy);
    EnableWindow(g_target_language_combo, !busy);
    EnableWindow(g_packages_button, !busy);
}

void layout_main(HWND window) {
    RECT client{};
    GetClientRect(window, &client);
    const int width = client.right - client.left;
    const int height = client.bottom - client.top;
    const int content_width = width - 32;
    const int status_top = height - 28;
    const int result_top = 228;
    int result_height = status_top - result_top - 8;
    if (result_height < 60) {
        result_height = 60;
    }
    if (g_packages_button) {
        SetWindowPos(
            g_packages_button,
            nullptr,
            width - 16 - 110,
            12,
            110,
            28,
            SWP_NOZORDER);
    }
    if (g_settings_button) {
        SetWindowPos(
            g_settings_button,
            nullptr,
            width - 16 - 110 - 8 - 110,
            12,
            110,
            28,
            SWP_NOZORDER);
    }
    if (g_source_edit) {
        SetWindowPos(
            g_source_edit,
            nullptr,
            16,
            84,
            content_width,
            90,
            SWP_NOZORDER);
    }
    if (g_result_edit) {
        SetWindowPos(
            g_result_edit,
            nullptr,
            16,
            result_top,
            content_width,
            result_height,
            SWP_NOZORDER);
    }
    if (g_status_label) {
        SetWindowPos(
            g_status_label,
            nullptr,
            16,
            status_top,
            content_width,
            20,
            SWP_NOZORDER);
    }
}

void start_translation(HWND window) {
    if (!g_runtime || g_runtime->busy.exchange(true)) {
        return;
    }
    const std::wstring source_text = control_text(g_source_edit);
    const auto engine_kind = selected_engine();
    const std::string source_language = selected_language(
        g_source_language_combo);
    const std::string target_language = selected_language(
        g_target_language_combo);
    const std::string text = to_utf8(source_text);
    const auto root = model_root_for_kind(engine_kind);
    const std::string engine_variant =
        engine_kind == offline_translator::EngineKind::firefox
            ? (g_runtime ? g_runtime->settings.architecture : std::string{"tiny"})
            : std::string{};
    persist_settings(window);
    set_main_busy(true);
    set_status(L"Подготовка перевода...");
    auto runtime = g_runtime;
    std::thread(
        [window, text, root, engine_kind, engine_variant, source_language, target_language, runtime]() {
            auto result = std::make_unique<StatusPayload>();
            try {
                std::lock_guard lock(runtime->mutex);
                if (runtime->closing) {
                    runtime->busy = false;
                    return;
                }
                auto& application =
                    runtime->session.acquire(engine_kind, root, engine_variant);
                if (!runtime->session.is_loaded()) {
                    post_status(window, "Загрузка модели...");
                } else {
                    post_status(window, "Перевод выполняется...");
                }
                result->text = from_utf8(
                    application.translate(
                        text,
                        source_language,
                        target_language)
                        .text);
                runtime->session.mark_loaded();
                post_status(window, "Готово");
            } catch (const std::exception& error) {
                result->failed = true;
                result->text = from_utf8(error.what());
                post_status(window, "Ошибка перевода");
            }
            runtime->busy = false;
            if (runtime->closing || !IsWindow(window)) {
                return;
            }
            PostMessageW(
                window,
                kTranslateMessage,
                0,
                reinterpret_cast<LPARAM>(result.release()));
        })
        .detach();
}

std::wstring package_status_text(const PackageRow& row) {
    if (row.installed) {
        return L"установлено";
    }
    if (row.incomplete) {
        return L"незавершённая загрузка";
    }
    return L"не установлено";
}

std::vector<PackageRow> collect_package_rows() {
    const auto nllb_root = model_root_path(true);
    const auto argos_root = model_root_path(false);
    const auto store = offline_translator::merge_store_pairs(
        offline_translator::ArgosModelManager::available_packages(),
        offline_translator::ArgosModelManager::installed_packages(argos_root));
    std::vector<PackageRow> rows;
    rows.reserve(store.size());
    for (const auto& entry : store) {
        PackageRow row;
        row.nllb = entry.nllb;
        if (entry.nllb) {
            offline_translator::NllbModelManager manager(nllb_root);
            row.title = L"NLLB-200 Distilled 600M";
            row.installed = manager.is_installed();
            row.incomplete = manager.has_incomplete_package();
        } else {
            row.from_code = entry.from_code;
            row.to_code = entry.to_code;
            offline_translator::ArgosModelManager manager(
                argos_root,
                entry.from_code,
                entry.to_code);
            row.title = L"Argos · " + from_utf8(
                offline_translator::store_pair_label(entry));
            row.installed = manager.is_installed();
            row.incomplete = manager.has_incomplete_package();
        }
        row.installed = row.installed || entry.installed;
        row.incomplete = row.incomplete || entry.incomplete;
        rows.push_back(std::move(row));
    }
    if (!g_runtime ||
        selected_engine() != offline_translator::EngineKind::firefox) {
        return rows;
    }
    // Секция Firefox Translations для выбранного размера модели.
    std::string architecture = g_runtime->settings.architecture;
    if (!offline_translator::FirefoxModelManager::is_architecture(architecture)) {
        architecture = "tiny";
    }
    const auto firefox_root = std::filesystem::path(firefox_model_root());
    const auto catalog = offline_translator::FirefoxModelManager::available_packages(
        firefox_root, architecture);
    const auto installed =
        offline_translator::FirefoxModelManager::installed_packages(firefox_root);
    std::vector<offline_translator::StorePair> firefox_pairs;
    std::set<std::pair<std::string, std::string>> seen;
    for (const auto& item : installed) {
        if (item.architecture.empty() || item.architecture == architecture) {
            offline_translator::StorePair pair;
            pair.from_code = item.from_code;
            pair.to_code = item.to_code;
            pair.installed = true;
            firefox_pairs.push_back(pair);
            seen.emplace(item.from_code, item.to_code);
        }
    }
    for (const auto& item : catalog) {
        if (seen.count({item.from_code, item.to_code}) > 0) {
            continue;
        }
        offline_translator::StorePair pair;
        pair.from_code = item.from_code;
        pair.to_code = item.to_code;
        firefox_pairs.push_back(std::move(pair));
    }
    for (auto& pair : firefox_pairs) {
        offline_translator::FirefoxModelManager manager(
            firefox_root,
            architecture,
            pair.from_code,
            pair.to_code);
        pair.installed = pair.installed || manager.is_installed();
        pair.incomplete = manager.has_incomplete_package();
    }
    offline_translator::sort_store_pairs(firefox_pairs);
    for (const auto& pair : firefox_pairs) {
        PackageRow row;
        row.firefox = true;
        row.architecture = architecture;
        row.from_code = pair.from_code;
        row.to_code = pair.to_code;
        row.title = from_utf8("Firefox (" + architecture + ") · " +
                              offline_translator::store_pair_label(pair));
        row.installed = pair.installed;
        row.incomplete = pair.incomplete;
        rows.push_back(std::move(row));
    }
    return rows;
}

void update_packages_status_count() {
    if (!g_package_status || !g_runtime) {
        return;
    }
    const std::size_t shown = g_runtime->package_rows.size();
    const std::size_t total = g_runtime->package_rows_all.size();
    std::wstring text;
    if (shown == total) {
        text = L"Пакетов в списке: " + std::to_wstring(total);
    } else {
        text = L"Показано " + std::to_wstring(shown) + L" из " +
            std::to_wstring(total) + L" пакетов";
    }
    SetWindowTextW(g_package_status, text.c_str());
}

bool package_row_matches_search(const PackageRow& row, const std::string& query) {
    offline_translator::StorePair pair;
    pair.nllb = row.nllb;
    pair.from_code = row.from_code;
    pair.to_code = row.to_code;
    pair.installed = row.installed;
    pair.incomplete = row.incomplete;
    return offline_translator::store_pair_matches(pair, query);
}

std::wstring package_row_line(const PackageRow& row) {
    std::wstring line = row.title + L" — " + package_status_text(row);
    return line;
}

void apply_package_filter() {
    if (!g_runtime || !g_package_list) {
        return;
    }
    const std::string query =
        g_package_search ? to_utf8(control_text(g_package_search)) : std::string();
    g_runtime->package_rows.clear();
    SendMessageW(g_package_list, LB_RESETCONTENT, 0, 0);
    for (const auto& row : g_runtime->package_rows_all) {
        if (!package_row_matches_search(row, query)) {
            continue;
        }
        const std::wstring line = package_row_line(row);
        SendMessageW(
            g_package_list,
            LB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(line.c_str()));
        g_runtime->package_rows.push_back(row);
    }
    if (!g_runtime->package_rows.empty()) {
        SendMessageW(g_package_list, LB_SETCURSEL, 0, 0);
    }
    update_packages_status_count();
}

void refresh_package_list() {
    if (!g_package_list || !g_runtime) {
        return;
    }
    const bool firefox_mode =
        selected_engine() == offline_translator::EngineKind::firefox;
    if (g_package_arch_caption) {
        ShowWindow(g_package_arch_caption, firefox_mode ? SW_SHOW : SW_HIDE);
    }
    if (g_package_arch_combo) {
        ShowWindow(g_package_arch_combo, firefox_mode ? SW_SHOW : SW_HIDE);
        const std::string architecture =
            g_runtime->settings.architecture == "base" ? "base" : "tiny";
        SendMessageW(
            g_package_arch_combo,
            CB_SETCURSEL,
            architecture == "base" ? 1 : 0,
            0);
    }
    g_runtime->package_rows_all = collect_package_rows();
    apply_package_filter();
}

const PackageRow* selected_package_row() {
    if (!g_runtime || !g_package_list) {
        return nullptr;
    }
    const LRESULT index = SendMessageW(g_package_list, LB_GETCURSEL, 0, 0);
    if (index < 0 ||
        static_cast<std::size_t>(index) >= g_runtime->package_rows.size()) {
        return nullptr;
    }
    return &g_runtime->package_rows[static_cast<std::size_t>(index)];
}

void set_packages_busy(bool busy) {
    EnableWindow(g_package_install, !busy);
    EnableWindow(g_package_uninstall, !busy);
    EnableWindow(g_package_list, !busy);
    EnableWindow(g_package_search, !busy);
    EnableWindow(g_package_arch_combo, !busy);
}

void start_package_job(HWND packages_window, bool install) {
    if (!g_runtime) {
        return;
    }
    const PackageRow* selected = selected_package_row();
    if (!selected) {
        MessageBoxW(
            packages_window,
            L"Выберите пакет.",
            L"Пакеты",
            MB_ICONINFORMATION | MB_OK);
        return;
    }
    const PackageRow row = *selected;
    if (install && row.installed) {
        MessageBoxW(
            packages_window,
            L"Этот пакет уже установлен.",
            L"Пакеты",
            MB_ICONINFORMATION | MB_OK);
        return;
    }
    if (!install && !row.installed && !row.incomplete) {
        MessageBoxW(
            packages_window,
            L"Нечего удалять: пакет не установлен.",
            L"Пакеты",
            MB_ICONINFORMATION | MB_OK);
        return;
    }
    if (install && row.nllb) {
        const int answer = MessageBoxW(
            packages_window,
            L"Скачать модель NLLB-200 Distilled 600M (около 622 МБ)?\n"
            L"Это займёт время и место на диске.",
            L"Установка NLLB",
            MB_ICONWARNING | MB_YESNO);
        if (answer != IDYES) {
            return;
        }
    }
    if (install && row.firefox) {
        const int answer = MessageBoxW(
            packages_window,
            (L"Скачать пакет Firefox Translations?\n" + row.title).c_str(),
            L"Установка Firefox",
            MB_ICONINFORMATION | MB_YESNO);
        if (answer != IDYES) {
            return;
        }
    }
    if (!install && row.nllb) {
        const int answer = MessageBoxW(
            packages_window,
            L"Удалить установленную модель NLLB-200?\n"
            L"Это единственная модель NLLB; её придётся качать заново.",
            L"Удаление NLLB",
            MB_ICONWARNING | MB_YESNO);
        if (answer != IDYES) {
            return;
        }
    }
    if (!install && !row.nllb) {
        const std::wstring question =
            L"Удалить пакет " + row.title + L"?";
        const int answer = MessageBoxW(
            packages_window,
            question.c_str(),
            L"Удаление Argos",
            MB_ICONQUESTION | MB_YESNO);
        if (answer != IDYES) {
            return;
        }
    }
    if (g_runtime->packages_busy.exchange(true)) {
        return;
    }
    set_packages_busy(true);
    if (g_package_status) {
        SetWindowTextW(
            g_package_status,
            install ? L"Установка пакета..." : L"Удаление пакета...");
    }
    auto runtime = g_runtime;
    std::thread([packages_window, install, row, runtime]() {
        auto done = std::make_unique<StatusPayload>();
        try {
            std::lock_guard lock(runtime->mutex);
            runtime->session.reset();
            const auto progress =
                [packages_window, runtime](
                    std::uint64_t downloaded,
                    std::uint64_t total,
                    std::string_view message) {
                    if (runtime->closing || !IsWindow(packages_window)) {
                        return;
                    }
                    std::string text(message);
                    if (total > 0) {
                        const int percent = static_cast<int>(
                            (downloaded * 100) / total);
                        text += " (" + std::to_string(percent) + "%)";
                    }
                    post_payload(
                        packages_window,
                        kPackageProgressMessage,
                        from_utf8(text),
                        false);
                };
            if (row.nllb) {
                offline_translator::NllbModelManager manager(
                    model_root_path(true));
                if (install) {
                    manager.download_and_install(progress);
                } else {
                    manager.uninstall();
                }
            } else if (row.firefox) {
                offline_translator::FirefoxModelManager manager(
                    std::filesystem::path(firefox_model_root()),
                    row.architecture.empty() ? std::string{"tiny"}
                                             : row.architecture,
                    row.from_code,
                    row.to_code);
                if (install) {
                    manager.download_and_install(progress);
                } else {
                    manager.uninstall();
                }
            } else {
                offline_translator::ArgosModelManager manager(
                    model_root_path(false),
                    row.from_code,
                    row.to_code);
                if (install) {
                    manager.download_and_install(progress);
                } else {
                    manager.uninstall();
                }
            }
            done->text = install
                ? L"Пакет установлен."
                : L"Пакет удалён.";
        } catch (const std::exception& error) {
            done->failed = true;
            done->text = from_utf8(error.what());
        }
        runtime->packages_busy = false;
        if (runtime->closing || !IsWindow(packages_window)) {
            return;
        }
        PostMessageW(
            packages_window,
            kPackageDoneMessage,
            0,
            reinterpret_cast<LPARAM>(done.release()));
    }).detach();
}

HINSTANCE window_instance(HWND window) {
    return reinterpret_cast<HINSTANCE>(GetWindowLongPtrW(window, GWLP_HINSTANCE));
}

std::wstring find_app_icon_path() {
    const std::wstring exe_dir = executable_directory();
    std::vector<std::wstring> candidates{
        exe_dir + L"\\assets\\app.ico",
        exe_dir + L"\\app.ico",
    };
    std::wstring walk = exe_dir;
    for (int step = 0; step < 8; ++step) {
        candidates.push_back(walk + L"\\assets\\app.ico");
        const auto separator = walk.find_last_of(L"\\/");
        if (separator == std::wstring::npos) {
            break;
        }
        walk = walk.substr(0, separator);
    }
    for (const auto& path : candidates) {
        if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) {
            return path;
        }
    }
    return {};
}

HICON create_generated_icon() {
    HDC screen = GetDC(nullptr);
    HDC memory = CreateCompatibleDC(screen);
    HBITMAP color = CreateCompatibleBitmap(screen, 16, 16);
    HBITMAP mask = CreateBitmap(16, 16, 1, 1, nullptr);
    HGDIOBJ old = SelectObject(memory, color);
    HBRUSH brush = CreateSolidBrush(RGB(45, 106, 227));
    RECT bounds{0, 0, 16, 16};
    FillRect(memory, &bounds, brush);
    DeleteObject(brush);
    SelectObject(memory, old);
    DeleteDC(memory);
    ReleaseDC(nullptr, screen);
    ICONINFO info{};
    info.fIcon = TRUE;
    info.hbmMask = mask;
    info.hbmColor = color;
    HICON icon = CreateIconIndirect(&info);
    DeleteObject(color);
    DeleteObject(mask);
    return icon;
}

HICON load_tray_icon() {
    const std::wstring path = find_app_icon_path();
    if (!path.empty()) {
        HICON icon = static_cast<HICON>(LoadImageW(
            nullptr,
            path.c_str(),
            IMAGE_ICON,
            16,
            16,
            LR_LOADFROMFILE));
        if (icon) {
            return icon;
        }
    }
    return create_generated_icon();
}

std::wstring find_selection_icon_path() {
    const std::wstring exe_dir = executable_directory();
    std::vector<std::wstring> candidates{
        exe_dir + L"\\assets\\icon.png",
        exe_dir + L"\\icon.png",
    };
    std::wstring walk = exe_dir;
    for (int step = 0; step < 8; ++step) {
        candidates.push_back(walk + L"\\assets\\icon.png");
        const auto separator = walk.find_last_of(L"\\/");
        if (separator == std::wstring::npos) {
            break;
        }
        walk = walk.substr(0, separator);
    }
    for (const auto& path : candidates) {
        if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) {
            return path;
        }
    }
    return {};
}

// Повторяет _fill_clickable_disk() из selection_button.py: находит радиус
// знака по непрозрачным пикселям и заливает прозрачные точки внутри круга
// белым, чтобы клик в центр не проваливался сквозь layered-окно.
void fill_clickable_disk(Gdiplus::BitmapData& data, int alpha_limit) {
    const int width = static_cast<int>(data.Width);
    const int height = static_cast<int>(data.Height);
    auto* pixels = static_cast<std::uint32_t*>(data.Scan0);
    const double center_x = (width - 1) / 2.0;
    const double center_y = (height - 1) / 2.0;
    double radius_sq = 0.0;
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const std::uint32_t argb =
                pixels[y * (data.Stride / 4) + x];
            if (((argb >> 24) & 0xFF) < alpha_limit) {
                continue;
            }
            const double dx = x - center_x;
            const double dy = y - center_y;
            radius_sq = std::max(radius_sq, dx * dx + dy * dy);
        }
    }
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            std::uint32_t& argb = pixels[y * (data.Stride / 4) + x];
            if (((argb >> 24) & 0xFF) >= alpha_limit) {
                continue;
            }
            const double dx = x - center_x;
            const double dy = y - center_y;
            if (dx * dx + dy * dy <= radius_sq) {
                argb = 0xFFFFFFFF;
            } else {
                argb = 0;
            }
        }
    }
}

// Готовит 40×40 premultiplied-DIB из assets/icon.png для
// UpdateLayeredWindow. Возвращает true, если иконка загружена.
bool compose_selection_icon_bitmap(HBITMAP* out_bitmap) {
    *out_bitmap = nullptr;
    const std::wstring path = find_selection_icon_path();
    if (path.empty()) {
        sel_log("compose: icon.png не найден");
        return false;
    }
    std::unique_ptr<Gdiplus::Bitmap> source(
        Gdiplus::Bitmap::FromFile(path.c_str()));
    if (!source || source->GetLastStatus() != Gdiplus::Ok) {
        sel_log("compose: Bitmap::FromFile не удался");
        return false;
    }
    std::unique_ptr<Gdiplus::Bitmap> target(
        new Gdiplus::Bitmap(
            kSelectionIconSize,
            kSelectionIconSize,
            PixelFormat32bppPARGB));
    if (!target || target->GetLastStatus() != Gdiplus::Ok) {
        return false;
    }
    Gdiplus::Graphics graphics(target.get());
    if (graphics.GetLastStatus() != Gdiplus::Ok) {
        return false;
    }
    graphics.SetInterpolationMode(
        Gdiplus::InterpolationModeHighQualityBicubic);
    graphics.SetPixelOffsetMode(Gdiplus::PixelOffsetModeHighQuality);
    graphics.DrawImage(
        source.get(),
        Gdiplus::Rect(0, 0, kSelectionIconSize, kSelectionIconSize),
        0,
        0,
        source->GetWidth(),
        source->GetHeight(),
        Gdiplus::UnitPixel);
    Gdiplus::Rect lock_rect(0, 0, kSelectionIconSize, kSelectionIconSize);
    Gdiplus::BitmapData data{};
    if (target->LockBits(
            &lock_rect,
            Gdiplus::ImageLockModeRead | Gdiplus::ImageLockModeWrite,
            PixelFormat32bppPARGB,
            &data) != Gdiplus::Ok) {
        return false;
    }
    fill_clickable_disk(data, 80);

    HDC screen = GetDC(nullptr);
    HDC memory = CreateCompatibleDC(screen);
    BITMAPINFO info{};
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = kSelectionIconSize;
    info.bmiHeader.biHeight = -kSelectionIconSize;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    HBITMAP bitmap = CreateDIBSection(
        memory,
        &info,
        DIB_RGB_COLORS,
        &bits,
        nullptr,
        0);
    bool copied = false;
    if (bitmap && bits) {
        for (int y = 0; y < kSelectionIconSize; ++y) {
            const auto* src = static_cast<const std::uint8_t*>(data.Scan0) +
                y * data.Stride;
            auto* dst = static_cast<std::uint8_t*>(bits) +
                y * kSelectionIconSize * 4;
            memcpy(dst, src, static_cast<std::size_t>(
                kSelectionIconSize) * 4);
        }
        copied = true;
    }
    DeleteDC(memory);
    ReleaseDC(nullptr, screen);
    target->UnlockBits(&data);
    if (!copied) {
        if (bitmap) {
            DeleteObject(bitmap);
        }
        return false;
    }
    // Диагностика: дамп скомпонованной иконки в %TEMP%.
    wchar_t dump_flag[8]{};
    if (GetEnvironmentVariableW(
            L"OT_DUMP_BUTTON",
            dump_flag,
            static_cast<DWORD>(std::size(dump_flag))) > 0) {
        CLSID png_clsid{};
        if (CLSIDFromString(
                L"{557CF406-1A04-11D3-9A73-0000F81EF32E}",
                &png_clsid) == S_OK) {
            wchar_t temp_dir[MAX_PATH]{};
            GetTempPathW(MAX_PATH, temp_dir);
            std::wstring dump = std::wstring(temp_dir) + L"fxbutton.png";
            target->Save(dump.c_str(), &png_clsid, nullptr);
        }
    }
    *out_bitmap = bitmap;
    return true;
}

// Показывает иконку как layered-окно в точке (x, y).
bool apply_layered_icon(HWND window, HBITMAP bitmap, int x, int y) {
    HDC screen = GetDC(nullptr);
    HDC memory = CreateCompatibleDC(screen);
    HGDIOBJ old = SelectObject(memory, bitmap);
    BLENDFUNCTION blend{AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
    SIZE size{kSelectionIconSize, kSelectionIconSize};
    POINT position{x, y};
    POINT zero{0, 0};
    const BOOL ok = UpdateLayeredWindow(
        window,
        screen,
        &position,
        &size,
        memory,
        &zero,
        0,
        &blend,
        ULW_ALPHA);
    SelectObject(memory, old);
    DeleteDC(memory);
    ReleaseDC(nullptr, screen);
    return ok != FALSE;
}

void add_tray_icon(HWND window) {
    if (g_smoke_mode || g_tray_added) {
        return;
    }
    if (!g_tray_icon) {
        g_tray_icon = load_tray_icon();
    }
    ZeroMemory(&g_tray_data, sizeof(g_tray_data));
    g_tray_data.cbSize = sizeof(g_tray_data);
    g_tray_data.hWnd = window;
    g_tray_data.uID = 1;
    g_tray_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
    g_tray_data.uCallbackMessage = kTrayMessage;
    g_tray_data.hIcon = g_tray_icon;
    wcscpy_s(g_tray_data.szTip, L"Offline Translator");
    if (Shell_NotifyIconW(NIM_ADD, &g_tray_data)) {
        g_tray_added = true;
    }
}

void remove_tray_icon() {
    if (!g_tray_added) {
        return;
    }
    Shell_NotifyIconW(NIM_DELETE, &g_tray_data);
    g_tray_added = false;
}

void restore_from_tray(HWND window) {
    ShowWindow(window, SW_SHOWNORMAL);
    ShowWindow(window, SW_RESTORE);
    SetForegroundWindow(window);
    if (g_source_edit) {
        SetFocus(g_source_edit);
    }
}

void hide_to_tray(HWND window) {
    persist_settings(window);
    ShowWindow(window, SW_HIDE);
    add_tray_icon(window);
}

void destroy_popup_windows() {
    if (g_selection_button) {
        DestroyWindow(g_selection_button);
        g_selection_button = nullptr;
    }
    if (g_result_popup) {
        DestroyWindow(g_result_popup);
        g_result_popup = nullptr;
        g_popup_result_edit = nullptr;
        g_popup_copy_button = nullptr;
    }
}

bool register_translate_hotkey(HWND window, const std::string& spec) {
    UnregisterHotKey(window, kShowWindowHotkey);
    const auto parsed = offline_translator::parse_hotkey(spec);
    if (!parsed) {
        return false;
    }
    return RegisterHotKey(
               window,
               kShowWindowHotkey,
               offline_translator::hotkey_win32_modifiers(*parsed),
               parsed->vk) != FALSE;
}

void show_tray_menu(HWND window) {
    HMENU menu = CreatePopupMenu();
    if (!menu) {
        return;
    }
    AppendMenuW(menu, MF_STRING, kTrayOpen, L"Открыть");
    UINT autostart_flags = MF_STRING;
    try {
        if (offline_translator::is_app_autostart_enabled()) {
            autostart_flags |= MF_CHECKED;
        }
    } catch (const std::exception&) {
    }
    AppendMenuW(
        menu,
        autostart_flags,
        kTrayAutostart,
        L"Запускать вместе с Windows");
    AppendMenuW(menu, MF_STRING, kTrayExit, L"Выход");
    SetMenuDefaultItem(menu, kTrayOpen, FALSE);
    POINT cursor{};
    GetCursorPos(&cursor);
    SetForegroundWindow(window);
    TrackPopupMenu(
        menu,
        TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
        cursor.x,
        cursor.y,
        0,
        window,
        nullptr);
    DestroyMenu(menu);
}

void toggle_app_autostart() {
    try {
        const bool enabled = !offline_translator::is_app_autostart_enabled();
        offline_translator::set_app_autostart(enabled);
        set_status(
            enabled
                ? L"Программа будет запускаться вместе с Windows"
                : L"Программа убрана из автозагрузки");
    } catch (const std::exception& error) {
        set_status(from_utf8(error.what()));
    }
}

bool is_over_our_popup(int x, int y) {
    for (HWND candidate : {g_selection_button, g_result_popup}) {
        if (!candidate || !IsWindow(candidate) || !IsWindowVisible(candidate)) {
            continue;
        }
        RECT bounds{};
        GetWindowRect(candidate, &bounds);
        if (x >= bounds.left && x <= bounds.right && y >= bounds.top &&
            y <= bounds.bottom) {
            return true;
        }
    }
    return false;
}

void sel_log(const std::string& line) {
    wchar_t flag[8]{};
    if (GetEnvironmentVariableW(
            L"OT_SEL_LOG",
            flag,
            static_cast<DWORD>(std::size(flag))) == 0) {
        return;
    }
    char temp_dir[MAX_PATH]{};
    GetTempPathA(MAX_PATH, temp_dir);
    std::ofstream log(std::string(temp_dir) + "ot_sel.log",
                      std::ios::binary | std::ios::app);
    if (log) {
        log << line << "\n";
    }
}

// Ожидание в capture_selected_text_win32 с прокачкой сообщений:
// инжектированный Ctrl+C доставляется очередью нашему же потоку, и без
// прокачки EDIT никогда его не обработает.
void pump_wait(std::uint32_t milliseconds) {
    const ULONGLONG deadline = GetTickCount64() + milliseconds;
    while (GetTickCount64() < deadline) {
        MSG message{};
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        Sleep(10);
    }
}

bool is_client_hit(int x, int y, HWND hwnd) {
    if (!hwnd) {
        return false;
    }
    const LRESULT hit = SendMessageW(
        hwnd,
        WM_NCHITTEST,
        0,
        MAKELPARAM(static_cast<WORD>(x), static_cast<WORD>(y)));
    return hit == HTCLIENT;
}

bool window_being_moved() {
    HWND foreground = GetForegroundWindow();
    if (!foreground) {
        return false;
    }
    const DWORD thread_id = GetWindowThreadProcessId(foreground, nullptr);
    GUITHREADINFO info{};
    info.cbSize = sizeof(info);
    if (!GetGUIThreadInfo(thread_id, &info)) {
        return false;
    }
    return (info.flags & GUI_INMOVESIZE) != 0 || info.hwndMoveSize != nullptr;
}

void hide_selection_button() {
    if (g_runtime && g_runtime->main_window) {
        KillTimer(g_runtime->main_window, kSelectionButtonHideTimer);
    }
    if (g_selection_button) {
        DestroyWindow(g_selection_button);
        g_selection_button = nullptr;
    }
}

void hide_result_popup() {
    if (g_result_popup) {
        DestroyWindow(g_result_popup);
        g_result_popup = nullptr;
        g_popup_result_edit = nullptr;
        g_popup_copy_button = nullptr;
    }
}

LRESULT CALLBACK selection_button_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param);

LRESULT CALLBACK result_popup_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param);

void start_selection_translation(HWND main_window);

HFONT create_popup_font(int point_size) {
    HDC dc = GetDC(nullptr);
    const int height = -MulDiv(
        point_size,
        GetDeviceCaps(dc, LOGPIXELSY),
        72);
    ReleaseDC(nullptr, dc);
    return CreateFontW(
        height,
        0,
        0,
        0,
        FW_NORMAL,
        FALSE,
        FALSE,
        FALSE,
        DEFAULT_CHARSET,
        OUT_DEFAULT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY,
        DEFAULT_PITCH | FF_DONTCARE,
        L"Segoe UI");
}

enum class PopupFont { header, body, button };

HFONT popup_font(PopupFont kind) {
    static HFONT header = create_popup_font(8);
    static HFONT body = create_popup_font(11);
    static HFONT button = create_popup_font(9);
    switch (kind) {
        case PopupFont::header:
            return header;
        case PopupFont::body:
            return body;
        case PopupFont::button:
            return button;
    }
    return body;
}

constexpr wchar_t kHoverPropertyName[] = L"ot_hover";

LRESULT CALLBACK flat_button_subclass(
    HWND handle,
    UINT message,
    WPARAM w_param,
    LPARAM l_param,
    UINT_PTR,
    DWORD_PTR) {
    if (message == WM_MOUSEMOVE) {
        TRACKMOUSEEVENT track{sizeof(TRACKMOUSEEVENT), TME_LEAVE, handle, 0};
        TrackMouseEvent(&track);
        if (!GetPropW(handle, kHoverPropertyName)) {
            SetPropW(handle, kHoverPropertyName, reinterpret_cast<HANDLE>(1));
            InvalidateRect(handle, nullptr, TRUE);
        }
    } else if (message == WM_MOUSELEAVE) {
        RemovePropW(handle, kHoverPropertyName);
        InvalidateRect(handle, nullptr, TRUE);
    } else if (message == WM_NCDESTROY) {
        RemovePropW(handle, kHoverPropertyName);
    }
    return DefSubclassProc(handle, message, w_param, l_param);
}

LRESULT CALLBACK popup_edit_subclass(
    HWND handle,
    UINT message,
    WPARAM w_param,
    LPARAM l_param,
    UINT_PTR,
    DWORD_PTR) {
    if (message == WM_KEYDOWN && w_param == VK_ESCAPE && g_result_popup) {
        hide_result_popup();
        return 0;
    }
    return DefSubclassProc(handle, message, w_param, l_param);
}

int popup_line_height() {
    HDC dc = GetDC(nullptr);
    HGDIOBJ old = SelectObject(dc, popup_font(PopupFont::body));
    RECT bounds{0, 0, 1000, 0};
    DrawTextW(dc, L"Ag", -1, &bounds, DT_CALCRECT | DT_SINGLELINE);
    SelectObject(dc, old);
    ReleaseDC(nullptr, dc);
    return static_cast<int>(std::max(bounds.bottom, 12L));
}

// Высота многострочного текста при переносе по ширине edit-поля.
int measure_text_height(const std::wstring& text, int width_px) {
    HDC dc = GetDC(nullptr);
    HGDIOBJ old = SelectObject(dc, popup_font(PopupFont::body));
    RECT bounds{0, 0, width_px, 0};
    DrawTextW(
        dc,
        text.c_str(),
        -1,
        &bounds,
        DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX | DT_EDITCONTROL);
    SelectObject(dc, old);
    ReleaseDC(nullptr, dc);
    return bounds.bottom;
}

void clamp_point_to_work_area(int width, int height, int& x, int& y) {
    POINT origin{x < 0 ? 0 : x, y < 0 ? 0 : y};
    const HMONITOR monitor = MonitorFromPoint(origin, MONITOR_DEFAULTTONEAREST);
    MONITORINFO info{sizeof(MONITORINFO)};
    if (!GetMonitorInfoW(monitor, &info)) {
        return;
    }
    const RECT& area = info.rcWork;
    if (x + width > area.right) {
        x = area.right - width - 8;
    }
    if (y + height > area.bottom) {
        y = area.bottom - height - 8;
    }
    if (x < area.left) {
        x = area.left;
    }
    if (y < area.top) {
        y = area.top;
    }
}

void show_selection_button(int cursor_x, int cursor_y, HWND main_window) {
    hide_result_popup();
    hide_selection_button();
    g_button_uses_icon = false;
    HBITMAP icon_bitmap = nullptr;
    const bool have_icon = compose_selection_icon_bitmap(&icon_bitmap);
    g_selection_button = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW |
            (have_icon ? WS_EX_LAYERED : 0),
        L"OfflineTranslatorSelectionButton",
        L"Aa",
        WS_POPUP | WS_VISIBLE,
        cursor_x - kSelectionIconSize / 2,
        cursor_y - kSelectionIconSize / 2,
        kSelectionIconSize,
        kSelectionIconSize,
        main_window,
        nullptr,
        window_instance(main_window),
        nullptr);
    if (!g_selection_button) {
        if (icon_bitmap) {
            DeleteObject(icon_bitmap);
        }
        return;
    }
    if (have_icon &&
        apply_layered_icon(
            g_selection_button,
            icon_bitmap,
            cursor_x - kSelectionIconSize / 2,
            cursor_y - kSelectionIconSize / 2)) {
        g_button_uses_icon = true;
    } else {
        // Фолбэк без иконки: обычное окно с рамкой и текстом «Aa».
        SetWindowLongPtrW(
            g_selection_button,
            GWL_EXSTYLE,
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW);
        SetWindowLongPtrW(
            g_selection_button,
            GWL_STYLE,
            WS_POPUP | WS_BORDER | WS_VISIBLE);
    }
    if (icon_bitmap) {
        DeleteObject(icon_bitmap);
    }
    SetTimer(main_window, kSelectionButtonHideTimer, 8000, nullptr);
}

void show_result_popup(
    HWND main_window,
    const std::wstring& text,
    const std::string& source_code,
    const std::string& target_code) {
    hide_selection_button();
    hide_result_popup();
    POINT cursor{};
    GetCursorPos(&cursor);
    const bool selectable = g_runtime &&
        g_runtime->settings.result_window_mode ==
            offline_translator::kResultWindowSelectable;
    constexpr int border = 1;
    constexpr int pad_x = 16;
    constexpr int pad_y = 14;
    const int width = 420;
    const int content_width = width - 2 * border - 2 * pad_x;

    // Высота текстового поля: 2..12 строк с переносом, как в Python.
    const int line_height = popup_line_height();
    const int text_height = std::max(measure_text_height(text, content_width), line_height);
    int visual_lines = text_height / line_height;
    if (text_height % line_height > line_height / 3) {
        ++visual_lines;
    }
    visual_lines = std::clamp(visual_lines, 2, 12);
    const int edit_height = visual_lines * line_height + 4;

    const int header_height = line_height * 8 / 10 + 6;
    const int button_height = 28;
    const int buttons_y = border + pad_y + header_height + 4 +
        edit_height + 10;
    const int client_height =
        buttons_y + button_height + pad_y + border;

    int x = cursor.x + 12;
    int y = cursor.y + 12;
    clamp_point_to_work_area(width, client_height, x, y);

    g_result_popup = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED,
        L"OfflineTranslatorResultPopup",
        L"Перевод",
        WS_POPUP | WS_VISIBLE,
        x,
        y,
        width,
        client_height,
        main_window,
        nullptr,
        window_instance(main_window),
        nullptr);
    if (!g_result_popup) {
        return;
    }
    // Полупрозрачность 0.97, как в Python (_style_overlay_window).
    SetLayeredWindowAttributes(g_result_popup, 0, 247, LWA_ALPHA);

    const std::wstring header = from_utf8(
        offline_translator::language_display_name(source_code) + " → " +
        offline_translator::language_display_name(target_code));
    const HWND header_label = CreateWindowW(
        L"STATIC",
        header.c_str(),
        WS_VISIBLE | WS_CHILD,
        border + pad_x,
        border + pad_y,
        content_width,
        header_height,
        g_result_popup,
        nullptr,
        nullptr,
        nullptr);
    SendMessageW(
        header_label,
        WM_SETFONT,
        reinterpret_cast<WPARAM>(popup_font(PopupFont::header)),
        TRUE);
    DWORD edit_style = WS_VISIBLE | WS_CHILD | ES_MULTILINE |
        ES_AUTOVSCROLL | WS_VSCROLL | ES_READONLY;
    g_popup_result_edit = CreateWindowW(
        L"EDIT",
        text.c_str(),
        edit_style,
        border + pad_x,
        border + pad_y + header_height + 4,
        content_width,
        edit_height,
        g_result_popup,
        nullptr,
        nullptr,
        nullptr);
    SendMessageW(
        g_popup_result_edit,
        WM_SETFONT,
        reinterpret_cast<WPARAM>(popup_font(PopupFont::body)),
        TRUE);
    SetWindowSubclass(
        g_popup_result_edit,
        popup_edit_subclass,
        1,
        0);
    const int copy_x = width - border - pad_x - 104;
    g_popup_copy_button = CreateWindowW(
        L"BUTTON",
        L"Копировать",
        WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
        copy_x,
        buttons_y,
        104,
        button_height,
        g_result_popup,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kResultCopyButton)),
        nullptr,
        nullptr);
    SendMessageW(
        g_popup_copy_button,
        WM_SETFONT,
        reinterpret_cast<WPARAM>(popup_font(PopupFont::button)),
        TRUE);
    SetWindowSubclass(
        g_popup_copy_button,
        flat_button_subclass,
        1,
        0);
    if (selectable) {
        const int close_x = copy_x - 84 - 8;
        const HWND close_button = CreateWindowW(
            L"BUTTON",
            L"Закрыть",
            WS_VISIBLE | WS_CHILD | BS_OWNERDRAW,
            close_x,
            buttons_y,
            84,
            button_height,
            g_result_popup,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kResultCloseButton)),
            nullptr,
            nullptr);
        SendMessageW(
            close_button,
            WM_SETFONT,
            reinterpret_cast<WPARAM>(popup_font(PopupFont::button)),
            TRUE);
        SetWindowSubclass(
            close_button,
            flat_button_subclass,
            1,
            0);
    }
    SetFocus(g_popup_result_edit);
}

void start_selection_translation(HWND main_window) {
    if (!g_runtime || g_runtime->selection_busy.exchange(true)) {
        return;
    }
    std::wstring selected = g_selection.selected_text;
    while (!selected.empty() &&
           (selected.back() == L' ' || selected.back() == L'\n')) {
        selected.pop_back();
    }
    if (selected.size() < 2) {
        g_runtime->selection_busy = false;
        return;
    }
    const std::string text = to_utf8(selected);
    const auto direction = offline_translator::choose_selection_direction(text);
    const auto engine_kind = selected_engine();
    const auto root = model_root_for_kind(engine_kind);
    const std::string engine_variant =
        engine_kind == offline_translator::EngineKind::firefox
            ? (g_runtime ? g_runtime->settings.architecture : std::string{"tiny"})
            : std::string{};
    auto runtime = g_runtime;
    std::thread([main_window, text, direction, engine_kind, engine_variant, root, runtime]() {
        auto result = std::make_unique<StatusPayload>();
        try {
            std::lock_guard lock(runtime->mutex);
            if (runtime->closing) {
                runtime->selection_busy = false;
                return;
            }
            auto& application =
                runtime->session.acquire(engine_kind, root, engine_variant);
            result->text = from_utf8(
                application.translate(text, direction.first, direction.second)
                    .text);
            runtime->session.mark_loaded();
        } catch (const std::exception& error) {
            result->failed = true;
            result->text = from_utf8(std::string("Ошибка: ") + error.what());
        }
        runtime->selection_busy = false;
        if (runtime->closing || !IsWindow(main_window)) {
            return;
        }
        PostMessageW(
            main_window,
            kSelectionResultMessage,
            0,
            reinterpret_cast<LPARAM>(result.release()));
    }).detach();
}

void capture_and_show_button(HWND main_window, int cursor_x, int cursor_y) {
    // Захват идёт в GUI-потоке; повторный вход через прокачанные сообщения
    // должен быть невозможен.
    static std::atomic<bool> capturing{false};
    if (capturing.exchange(true)) {
        return;
    }
    struct CaptureGuard {
        std::atomic<bool>& flag;
        ~CaptureGuard() {
            flag = false;
        }
    } guard{capturing};
    try {
        const std::wstring selected =
            offline_translator::capture_selected_text_win32(main_window);
        sel_log("captured: size=" + std::to_string(selected.size()));
        if (selected.size() < 2) {
            return;
        }
        g_selection.selected_text = selected;
        show_selection_button(cursor_x, cursor_y, main_window);
        sel_log("button shown");
    } catch (const std::exception& error) {
        sel_log(std::string("capture error: ") + error.what());
    }
}

void poll_double_ctrl_c(HWND main_window) {
    if (!g_runtime || !g_runtime->settings.double_ctrl_c_translation) {
        g_selection.last_ctrl_c_time = 0;
        g_selection.was_c_pressed = key_down('C');
        return;
    }
    const bool ctrl_pressed = key_down(VK_CONTROL);
    const bool c_pressed = key_down('C');
    if (!ctrl_pressed) {
        g_selection.last_ctrl_c_time = 0;
    }
    if (c_pressed && !g_selection.was_c_pressed && ctrl_pressed) {
        const double now = monotonic_seconds();
        if (offline_translator::should_trigger_double_ctrl_c(
                g_selection.last_ctrl_c_time,
                now,
                ctrl_pressed,
                true)) {
            g_selection.last_ctrl_c_time = 0;
            try {
                const std::wstring selected = clipboard_text();
                if (selected.size() >= 2) {
                    g_selection.selected_text = selected;
                    hide_selection_button();
                    start_selection_translation(main_window);
                }
            } catch (const std::exception&) {
            }
        } else {
            g_selection.last_ctrl_c_time = now;
        }
    }
    g_selection.was_c_pressed = c_pressed;
}

void poll_selection(HWND main_window) {
    if (g_smoke_mode || !g_runtime) {
        return;
    }
    POINT cursor{};
    GetCursorPos(&cursor);
    poll_double_ctrl_c(main_window);
    const bool pressed = key_down(VK_LBUTTON);
    if (pressed && !g_selection.was_pressed) {
        if (is_over_our_popup(cursor.x, cursor.y)) {
            g_selection.press_active = false;
        } else {
            HWND hwnd = WindowFromPoint(cursor);
            g_selection.press_x = cursor.x;
            g_selection.press_y = cursor.y;
            g_selection.press_time = monotonic_seconds();
            g_selection.press_hwnd = hwnd ? GetAncestor(hwnd, GA_ROOT) : nullptr;
            RECT origin{};
            if (g_selection.press_hwnd &&
                GetWindowRect(g_selection.press_hwnd, &origin)) {
                g_selection.press_origin.x = origin.left;
                g_selection.press_origin.y = origin.top;
            } else {
                g_selection.press_origin = cursor;
            }
            g_selection.press_is_client = is_client_hit(cursor.x, cursor.y, hwnd);
            g_selection.gesture_invalid = !g_selection.press_is_client;
            g_selection.press_active = true;
            sel_log("press: hwnd=" +
                    std::to_string(reinterpret_cast<uintptr_t>(
                        g_selection.press_hwnd)) +
                    " client=" + std::to_string(g_selection.press_is_client));
        }
    } else if (pressed && g_selection.was_pressed && g_selection.press_active) {
        if (!g_selection.gesture_invalid) {
            if (window_being_moved()) {
                g_selection.gesture_invalid = true;
            } else if (g_selection.press_hwnd) {
                RECT origin{};
                if (GetWindowRect(g_selection.press_hwnd, &origin)) {
                    if (std::abs(origin.left - g_selection.press_origin.x) >= 4 ||
                        std::abs(origin.top - g_selection.press_origin.y) >= 4) {
                        g_selection.gesture_invalid = true;
                    }
                }
            }
        }
    } else if (!pressed && g_selection.was_pressed && g_selection.press_active) {
        const double now = monotonic_seconds();
        const int drag_distance = std::max(
            std::abs(cursor.x - g_selection.press_x),
            std::abs(cursor.y - g_selection.press_y));
        const double drag_duration = now - g_selection.press_time;
        bool window_moved = false;
        if (g_selection.press_hwnd) {
            RECT origin{};
            if (GetWindowRect(g_selection.press_hwnd, &origin)) {
                window_moved =
                    std::abs(origin.left - g_selection.press_origin.x) >= 4 ||
                    std::abs(origin.top - g_selection.press_origin.y) >= 4;
            }
        }
        const bool is_double_click =
            (now - g_selection.last_up_time) < 0.35 &&
            g_selection.press_hwnd != nullptr &&
            g_selection.press_hwnd == g_selection.last_up_hwnd &&
            std::abs(cursor.x - g_selection.last_up_x) <= 6 &&
            std::abs(cursor.y - g_selection.last_up_y) <= 6 &&
            g_selection.press_is_client;
        g_selection.last_up_time = now;
        g_selection.last_up_hwnd = g_selection.press_hwnd;
        g_selection.last_up_x = cursor.x;
        g_selection.last_up_y = cursor.y;
        const bool ctrl_now = key_down(VK_CONTROL);
        const bool gate = !g_selection.gesture_invalid &&
            !is_over_our_popup(cursor.x, cursor.y) &&
            offline_translator::should_capture_selection(
                g_selection.press_is_client,
                window_moved,
                drag_distance,
                drag_duration,
                is_double_click) &&
            offline_translator::should_show_selection_button(
                g_runtime->settings.popup_requires_ctrl,
                ctrl_now);
        sel_log(
            "release: dist=" + std::to_string(drag_distance) + " dur=" +
            std::to_string(drag_duration) + " dbl=" +
            std::to_string(is_double_click) + " moved=" +
            std::to_string(window_moved) + " invalid=" +
            std::to_string(g_selection.gesture_invalid) + " ctrl=" +
            std::to_string(ctrl_now) + " requires_ctrl=" +
            std::to_string(g_runtime->settings.popup_requires_ctrl) +
            " gate=" + std::to_string(gate));
        if (gate) {
            capture_and_show_button(main_window, cursor.x, cursor.y);
        }
        g_selection.press_active = false;
    }
    g_selection.was_pressed = pressed;
}

void handle_translate_hotkey(HWND window) {
    for (int step = 0; step < 25; ++step) {
        if (!key_down(VK_CONTROL) && !key_down(VK_SHIFT) &&
            !key_down(VK_MENU) && !key_down(VK_LWIN) && !key_down(VK_RWIN)) {
            break;
        }
        Sleep(20);
    }
    std::wstring previous;
    try {
        previous = clipboard_text();
    } catch (const std::exception&) {
    }
    std::wstring selected;
    try {
        selected = offline_translator::capture_selected_text_win32(window);
    } catch (const std::exception&) {
    }
    if (selected.size() < 2) {
        selected = previous;
    }
    if (selected.size() < 2) {
        set_status(L"Нет выделенного текста");
        return;
    }
    g_selection.selected_text = selected;
    if (IsWindowVisible(window) && g_source_edit) {
        SetWindowTextW(g_source_edit, selected.c_str());
    }
    start_selection_translation(window);
}

void close_settings_window();

LRESULT CALLBACK selection_button_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    if (message == WM_LBUTTONUP) {
        if (g_runtime) {
            start_selection_translation(g_runtime->main_window);
        }
        return 0;
    }
    if (message == WM_PAINT) {
        PAINTSTRUCT paint{};
        HDC dc = BeginPaint(window, &paint);
        RECT client{};
        GetClientRect(window, &client);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, RGB(20, 20, 20));
        DrawTextW(dc, L"Aa", -1, &client, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        EndPaint(window, &paint);
        return 0;
    }
    if (message == WM_DESTROY) {
        if (g_selection_button == window) {
            g_selection_button = nullptr;
        }
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

LRESULT CALLBACK result_popup_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    const bool click_to_close = !g_runtime ||
        g_runtime->settings.result_window_mode !=
            offline_translator::kResultWindowSelectable;
    if (message == WM_COMMAND) {
        const int id = LOWORD(w_param);
        if (id == kResultCopyButton) {
            // Как в Python: копирует выделение, если оно есть,
            // иначе весь перевод.
            DWORD selection_start = 0;
            DWORD selection_end = 0;
            SendMessageW(
                g_popup_result_edit,
                EM_GETSEL,
                reinterpret_cast<WPARAM>(&selection_start),
                reinterpret_cast<LPARAM>(&selection_end));
            const std::wstring text = g_popup_result_edit
                ? control_text(g_popup_result_edit)
                : std::wstring{};
            std::wstring copy = text;
            if (selection_end > selection_start &&
                selection_end <= text.size()) {
                copy = text.substr(selection_start, selection_end - selection_start);
            }
            try {
                offline_translator::Win32Clipboard clipboard(window);
                clipboard.set_text(copy);
            } catch (const std::exception&) {
            }
            return 0;
        }
        if (id == kResultCloseButton) {
            hide_result_popup();
            return 0;
        }
    }
    if (message == WM_DRAWITEM) {
        auto* draw = reinterpret_cast<DRAWITEMSTRUCT*>(l_param);
        if (draw && draw->CtlType == ODT_BUTTON) {
            const bool hovered =
                GetPropW(draw->hwndItem, kHoverPropertyName) != nullptr;
            HBRUSH brush = CreateSolidBrush(
                hovered ? kButtonHover : kButtonFace);
            FillRect(draw->hDC, &draw->rcItem, brush);
            DeleteObject(brush);
            SetBkMode(draw->hDC, TRANSPARENT);
            SetTextColor(draw->hDC, RGB(0, 0, 0));
            SelectObject(draw->hDC, popup_font(PopupFont::button));
            wchar_t label[64]{};
            GetWindowTextW(draw->hwndItem, label, 64);
            DrawTextW(
                draw->hDC,
                label,
                -1,
                &draw->rcItem,
                DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            return TRUE;
        }
    }
    if (message == WM_ERASEBKGND) {
        RECT client{};
        GetClientRect(window, &client);
        HDC dc = reinterpret_cast<HDC>(w_param);
        // Рамка 1px + панель #f2f2f2, как трюк Python с чёрной подложкой.
        HBRUSH border_brush = CreateSolidBrush(kPopupBorder);
        FillRect(dc, &client, border_brush);
        DeleteObject(border_brush);
        RECT inner = client;
        InflateRect(&inner, -1, -1);
        HBRUSH panel_brush = CreateSolidBrush(kPopupBackground);
        FillRect(dc, &inner, panel_brush);
        DeleteObject(panel_brush);
        return 1;
    }
    if (message == WM_CTLCOLORSTATIC) {
        const HDC dc = reinterpret_cast<HDC>(w_param);
        SetBkColor(dc, kPopupBackground);
        // Заголовок приглушённый #333333, текст перевода чёрный.
        if (reinterpret_cast<HWND>(l_param) == g_popup_result_edit) {
            SetTextColor(dc, RGB(0, 0, 0));
        } else {
            SetTextColor(dc, kPopupHeaderText);
        }
        static HBRUSH background =
            CreateSolidBrush(kPopupBackground);
        return reinterpret_cast<LRESULT>(background);
    }
    if (message == WM_KEYDOWN && w_param == VK_ESCAPE) {
        hide_result_popup();
        return 0;
    }
    if (message == WM_LBUTTONUP && click_to_close) {
        hide_result_popup();
        return 0;
    }
    if (message == WM_PARENTNOTIFY && click_to_close &&
        LOWORD(w_param) == WM_LBUTTONDOWN) {
        const HWND child = reinterpret_cast<HWND>(l_param);
        if (child != g_popup_copy_button) {
            hide_result_popup();
        }
        return 0;
    }
    if (message == WM_DESTROY) {
        if (g_result_popup == window) {
            g_result_popup = nullptr;
            g_popup_result_edit = nullptr;
            g_popup_copy_button = nullptr;
        }
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

void apply_settings_dialog(HWND settings_window) {
    if (!g_runtime) {
        return;
    }
    auto settings = g_runtime->settings;
    settings.popup_requires_ctrl =
        SendMessageW(g_settings_popup_ctrl, BM_GETCHECK, 0, 0) == BST_CHECKED;
    settings.double_ctrl_c_translation =
        SendMessageW(g_settings_double_ctrl_c, BM_GETCHECK, 0, 0) == BST_CHECKED;
    settings.result_window_mode =
        SendMessageW(g_settings_click_to_close, BM_GETCHECK, 0, 0) == BST_CHECKED
            ? std::string{offline_translator::kResultWindowClickToClose}
            : std::string{offline_translator::kResultWindowSelectable};
    const std::string hotkey = to_utf8(control_text(g_settings_hotkey_edit));
    if (!offline_translator::parse_hotkey(hotkey)) {
        MessageBoxW(
            settings_window,
            L"Некорректная горячая клавиша. Пример: Ctrl+Shift+T",
            L"Настройки",
            MB_ICONWARNING | MB_OK);
        return;
    }
    settings.translate_hotkey =
        offline_translator::format_hotkey(*offline_translator::parse_hotkey(hotkey));
    if (g_runtime->main_window && g_engine_combo) {
        settings.engine =
            offline_translator::settings_engine_name(selected_engine());
        settings.source_language = selected_language(g_source_language_combo);
        settings.target_language = selected_language(g_target_language_combo);
        collect_window_size(g_runtime->main_window, settings);
    }
    try {
        if (!g_smoke_mode) {
            offline_translator::save_settings(settings);
            const bool autostart =
                SendMessageW(g_settings_autostart, BM_GETCHECK, 0, 0) ==
                BST_CHECKED;
            offline_translator::set_app_autostart(autostart);
            if (g_runtime->main_window &&
                !register_translate_hotkey(
                    g_runtime->main_window,
                    settings.translate_hotkey)) {
                MessageBoxW(
                    settings_window,
                    L"Не удалось зарегистрировать горячую клавишу.",
                    L"Настройки",
                    MB_ICONWARNING | MB_OK);
            }
        }
        g_runtime->settings = settings;
        close_settings_window();
        set_status(L"Настройки сохранены");
    } catch (const std::exception& error) {
        MessageBoxW(
            settings_window,
            from_utf8(error.what()).c_str(),
            L"Настройки",
            MB_ICONERROR | MB_OK);
    }
}

void close_settings_window() {
    if (!g_runtime || !g_runtime->settings_window) {
        return;
    }
    HWND settings = g_runtime->settings_window;
    HWND main = g_runtime->main_window;
    g_runtime->settings_window = nullptr;
    g_settings_popup_ctrl = nullptr;
    g_settings_double_ctrl_c = nullptr;
    g_settings_click_to_close = nullptr;
    g_settings_selectable = nullptr;
    g_settings_autostart = nullptr;
    g_settings_hotkey_edit = nullptr;
    DestroyWindow(settings);
    if (main) {
        EnableWindow(main, TRUE);
        SetForegroundWindow(main);
    }
}

LRESULT CALLBACK settings_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    if (message == WM_CREATE) {
        const auto settings = g_runtime ? g_runtime->settings
                                        : offline_translator::AppSettings{};
        g_settings_popup_ctrl = CreateWindowW(
            L"BUTTON",
            L"Показывать кнопку выделения только при удержании Ctrl",
            WS_VISIBLE | WS_CHILD | BS_AUTOCHECKBOX,
            16,
            16,
            450,
            24,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsPopupCtrl)),
            nullptr,
            nullptr);
        SendMessageW(
            g_settings_popup_ctrl,
            BM_SETCHECK,
            settings.popup_requires_ctrl ? BST_CHECKED : BST_UNCHECKED,
            0);
        g_settings_double_ctrl_c = CreateWindowW(
            L"BUTTON",
            L"Переводить выделенный текст по Ctrl+C+C",
            WS_VISIBLE | WS_CHILD | BS_AUTOCHECKBOX,
            16,
            48,
            450,
            24,
            window,
            reinterpret_cast<HMENU>(
                static_cast<INT_PTR>(kSettingsDoubleCtrlC)),
            nullptr,
            nullptr);
        SendMessageW(
            g_settings_double_ctrl_c,
            BM_SETCHECK,
            settings.double_ctrl_c_translation ? BST_CHECKED : BST_UNCHECKED,
            0);
        CreateWindowW(
            L"STATIC",
            L"Окно результата:",
            WS_VISIBLE | WS_CHILD,
            16,
            88,
            200,
            20,
            window,
            nullptr,
            nullptr,
            nullptr);
        g_settings_click_to_close = CreateWindowW(
            L"BUTTON",
            L"Закрывать нажатием по окну",
            WS_VISIBLE | WS_CHILD | BS_AUTORADIOBUTTON | WS_GROUP,
            16,
            112,
            300,
            22,
            window,
            reinterpret_cast<HMENU>(
                static_cast<INT_PTR>(kSettingsClickToClose)),
            nullptr,
            nullptr);
        g_settings_selectable = CreateWindowW(
            L"BUTTON",
            L"Выделять текст; закрывать кнопкой «Закрыть»",
            WS_VISIBLE | WS_CHILD | BS_AUTORADIOBUTTON,
            16,
            136,
            420,
            22,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsSelectable)),
            nullptr,
            nullptr);
        const bool click_to_close = settings.result_window_mode !=
            offline_translator::kResultWindowSelectable;
        SendMessageW(
            g_settings_click_to_close,
            BM_SETCHECK,
            click_to_close ? BST_CHECKED : BST_UNCHECKED,
            0);
        SendMessageW(
            g_settings_selectable,
            BM_SETCHECK,
            click_to_close ? BST_UNCHECKED : BST_CHECKED,
            0);
        CreateWindowW(
            L"STATIC",
            L"Горячая клавиша перевода выделения:",
            WS_VISIBLE | WS_CHILD,
            16,
            176,
            300,
            20,
            window,
            nullptr,
            nullptr,
            nullptr);
        g_settings_hotkey_edit = CreateWindowW(
            L"EDIT",
            from_utf8(settings.translate_hotkey).c_str(),
            WS_VISIBLE | WS_CHILD | WS_BORDER | ES_AUTOHSCROLL,
            16,
            200,
            240,
            24,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsHotkeyEdit)),
            nullptr,
            nullptr);
        g_settings_autostart = CreateWindowW(
            L"BUTTON",
            L"Запускать вместе с Windows",
            WS_VISIBLE | WS_CHILD | BS_AUTOCHECKBOX,
            16,
            240,
            400,
            24,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsAutostart)),
            nullptr,
            nullptr);
        bool autostart = false;
        try {
            autostart = offline_translator::is_app_autostart_enabled();
        } catch (const std::exception&) {
        }
        SendMessageW(
            g_settings_autostart,
            BM_SETCHECK,
            autostart ? BST_CHECKED : BST_UNCHECKED,
            0);
        CreateWindowW(
            L"BUTTON",
            L"Сохранить",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            16,
            284,
            120,
            30,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsSave)),
            nullptr,
            nullptr);
        CreateWindowW(
            L"BUTTON",
            L"Отмена",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            148,
            284,
            120,
            30,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsCancel)),
            nullptr,
            nullptr);
        return 0;
    }
    if (message == WM_COMMAND) {
        const int id = LOWORD(w_param);
        if (id == kSettingsSave) {
            apply_settings_dialog(window);
            return 0;
        }
        if (id == kSettingsCancel) {
            close_settings_window();
            return 0;
        }
    }
    if (message == WM_CLOSE) {
        close_settings_window();
        return 0;
    }
    if (message == WM_DESTROY) {
        if (g_runtime && g_runtime->settings_window == window) {
            g_runtime->settings_window = nullptr;
        }
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

void open_settings_window(HWND parent, HINSTANCE instance) {
    if (g_runtime && g_runtime->settings_window) {
        SetForegroundWindow(g_runtime->settings_window);
        return;
    }
    HWND settings = CreateWindowW(
        L"OfflineTranslatorSettings",
        L"Настройки",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        520,
        370,
        parent,
        nullptr,
        instance,
        nullptr);
    if (!settings) {
        throw std::runtime_error("Не удалось открыть настройки");
    }
    if (g_runtime) {
        g_runtime->settings_window = settings;
    }
    EnableWindow(parent, FALSE);
    ShowWindow(settings, SW_SHOW);
    UpdateWindow(settings);
}

void create_main_controls(HWND window) {
    CreateWindowW(
        L"STATIC",
        L"Движок:",
        WS_VISIBLE | WS_CHILD,
        16,
        16,
        70,
        24,
        window,
        nullptr,
        nullptr,
        nullptr);
    g_engine_combo = CreateWindowW(
        L"COMBOBOX",
        nullptr,
        WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_TABSTOP,
        90,
        12,
        140,
        160,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kEngineCombo)),
        nullptr,
        nullptr);
    SendMessageW(
        g_engine_combo,
        CB_ADDSTRING,
        0,
        reinterpret_cast<LPARAM>(L"Argos"));
    SendMessageW(
        g_engine_combo,
        CB_ADDSTRING,
        0,
        reinterpret_cast<LPARAM>(L"NLLB-200"));
    SendMessageW(
        g_engine_combo,
        CB_ADDSTRING,
        0,
        reinterpret_cast<LPARAM>(L"Firefox"));
    SendMessageW(g_engine_combo, CB_SETCURSEL, 0, 0);
    g_packages_button = CreateWindowW(
        L"BUTTON",
        L"Пакеты",
        WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
        390,
        12,
        110,
        28,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kPackagesButton)),
        nullptr,
        nullptr);
    g_settings_button = CreateWindowW(
        L"BUTTON",
        L"Настройки",
        WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
        272,
        12,
        110,
        28,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsButton)),
        nullptr,
        nullptr);
    CreateWindowW(
        L"STATIC",
        L"С языка:",
        WS_VISIBLE | WS_CHILD,
        16,
        52,
        70,
        24,
        window,
        nullptr,
        nullptr,
        nullptr);
    g_source_language_combo = CreateWindowW(
        L"COMBOBOX",
        nullptr,
        WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_TABSTOP,
        90,
        48,
        150,
        140,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSourceLanguageCombo)),
        nullptr,
        nullptr);
    CreateWindowW(
        L"STATIC",
        L"На язык:",
        WS_VISIBLE | WS_CHILD,
        270,
        52,
        60,
        24,
        window,
        nullptr,
        nullptr,
        nullptr);
    g_target_language_combo = CreateWindowW(
        L"COMBOBOX",
        nullptr,
        WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_TABSTOP,
        335,
        48,
        130,
        140,
        window,
        reinterpret_cast<HMENU>(
            static_cast<INT_PTR>(kTargetLanguageCombo)),
        nullptr,
        nullptr);
    g_source_edit = CreateWindowW(
        L"EDIT",
        L"Hello world",
        WS_VISIBLE | WS_CHILD | WS_BORDER | ES_MULTILINE | ES_AUTOVSCROLL |
            WS_VSCROLL | WS_TABSTOP,
        16,
        84,
        470,
        90,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSourceEdit)),
        nullptr,
        nullptr);
    g_translate_button = CreateWindowW(
        L"BUTTON",
        L"Перевести",
        WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
        16,
        186,
        120,
        30,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kTranslateButton)),
        nullptr,
        nullptr);
    g_result_edit = CreateWindowW(
        L"EDIT",
        nullptr,
        WS_VISIBLE | WS_CHILD | WS_BORDER | ES_MULTILINE | ES_READONLY |
            ES_AUTOVSCROLL | WS_VSCROLL,
        16,
        228,
        470,
        140,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kResultEdit)),
        nullptr,
        nullptr);
    g_status_label = CreateWindowW(
        L"STATIC",
        L"Готово",
        WS_VISIBLE | WS_CHILD | SS_LEFT,
        16,
        378,
        470,
        20,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kStatusLabel)),
        nullptr,
        nullptr);
    const auto settings = offline_translator::load_settings();
    if (g_runtime) {
        g_runtime->settings = settings;
    }
    apply_settings_to_ui(settings);
    layout_main(window);
}

void close_packages_window() {
    if (!g_runtime || !g_runtime->packages_window) {
        return;
    }
    HWND packages = g_runtime->packages_window;
    HWND main = g_runtime->main_window;
    g_runtime->packages_window = nullptr;
    g_package_list = nullptr;
    g_package_install = nullptr;
    g_package_uninstall = nullptr;
    g_package_status = nullptr;
    DestroyWindow(packages);
    if (main) {
        EnableWindow(main, TRUE);
        SetForegroundWindow(main);
    }
}

LRESULT CALLBACK packages_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    try {
        if (message == WM_CREATE) {
            CreateWindowW(
                L"STATIC",
                L"Установленные и доступные пакеты Argos/NLLB:",
                WS_VISIBLE | WS_CHILD,
                16,
                12,
                430,
                20,
                window,
                nullptr,
                nullptr,
                nullptr);
            CreateWindowW(
                L"STATIC",
                L"Поиск:",
                WS_VISIBLE | WS_CHILD,
                16,
                40,
                48,
                20,
                window,
                nullptr,
                nullptr,
                nullptr);
            g_package_search = CreateWindowW(
                L"EDIT",
                nullptr,
                WS_VISIBLE | WS_CHILD | WS_BORDER | WS_TABSTOP |
                    ES_AUTOHSCROLL,
                68,
                36,
                398,
                24,
                window,
                reinterpret_cast<HMENU>(static_cast<INT_PTR>(
                    kPackageSearchEdit)),
                nullptr,
                nullptr);
            SendMessageW(
                g_package_search,
                WM_SETFONT,
                reinterpret_cast<WPARAM>(
                    GetStockObject(DEFAULT_GUI_FONT)),
                TRUE);
            SendMessageW(
                g_package_search,
                EM_SETCUEBANNER,
                TRUE,
                reinterpret_cast<LPARAM>(L"код или язык: ru, немецкий..."));
            g_package_arch_caption = CreateWindowW(
                L"STATIC",
                L"Размер моделей:",
                WS_CHILD,  // показывается только для движка Firefox
                250,
                15,
                110,
                20,
                window,
                nullptr,
                nullptr,
                nullptr);
            g_package_arch_combo = CreateWindowW(
                L"COMBOBOX",
                nullptr,
                WS_CHILD | CBS_DROPDOWNLIST | WS_TABSTOP,
                364,
                11,
                120,
                160,
                window,
                reinterpret_cast<HMENU>(static_cast<INT_PTR>(
                    kPackageArchCombo)),
                nullptr,
                nullptr);
            SendMessageW(g_package_arch_combo, CB_ADDSTRING, 0,
                         reinterpret_cast<LPARAM>(L"tiny"));
            SendMessageW(g_package_arch_combo, CB_ADDSTRING, 0,
                         reinterpret_cast<LPARAM>(L"base"));
            g_package_list = CreateWindowW(
                L"LISTBOX",
                nullptr,
                WS_VISIBLE | WS_CHILD | WS_BORDER | WS_VSCROLL | LBS_NOTIFY |
                    WS_TABSTOP | LBS_NOINTEGRALHEIGHT,
                16,
                66,
                450,
                206,
                window,
                reinterpret_cast<HMENU>(static_cast<INT_PTR>(kPackageList)),
                nullptr,
                nullptr);
            g_package_status = CreateWindowW(
                L"STATIC",
                L"",
                WS_VISIBLE | WS_CHILD | SS_LEFT,
                16,
                276,
                450,
                22,
                window,
                nullptr,
                nullptr,
                nullptr);
            g_package_install = CreateWindowW(
                L"BUTTON",
                L"Установить",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
                16,
                306,
                120,
                30,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kPackageInstallButton)),
                nullptr,
                nullptr);
            g_package_uninstall = CreateWindowW(
                L"BUTTON",
                L"Удалить",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
                148,
                306,
                120,
                30,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kPackageUninstallButton)),
                nullptr,
                nullptr);
            CreateWindowW(
                L"BUTTON",
                L"Закрыть",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
                346,
                306,
                120,
                30,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kPackageCloseButton)),
                nullptr,
                nullptr);
            refresh_package_list();
            std::thread([window]() {
                offline_translator::ArgosModelManager::update_remote_index();
                post_payload(
                    window,
                    kPackageIndexMessage,
                    L"Каталог Argos обновлён",
                    false);
            }).detach();
            return 0;
        }
        if (message == kPackageIndexMessage) {
            std::unique_ptr<StatusPayload> payload(
                reinterpret_cast<StatusPayload*>(l_param));
            if (!g_runtime || g_runtime->packages_busy) {
                return 0;
            }
            refresh_package_list();
            if (g_package_status && !g_runtime->packages_busy) {
                update_packages_status_count();
            }
            static_cast<void>(payload);
            return 0;
        }
        if (message == WM_COMMAND) {
            const int id = LOWORD(w_param);
            const int notification = HIWORD(w_param);
            if (id == kPackageCloseButton) {
                close_packages_window();
                return 0;
            }
            if (id == kPackageInstallButton) {
                start_package_job(window, true);
                return 0;
            }
            if (id == kPackageUninstallButton) {
                start_package_job(window, false);
                return 0;
            }
            if (id == kPackageSearchEdit &&
                notification == EN_CHANGE &&
                !g_runtime->packages_busy) {
                apply_package_filter();
            }
            if (id == kPackageArchCombo &&
                notification == CBN_SELCHANGE && g_runtime) {
                const LRESULT arch =
                    SendMessageW(g_package_arch_combo, CB_GETCURSEL, 0, 0);
                g_runtime->settings.architecture = arch == 1 ? "base" : "tiny";
                try {
                    if (!g_smoke_mode) {
                        offline_translator::save_settings(g_runtime->settings);
                    }
                } catch (const std::exception&) {
                }
                refresh_package_list();
            }
        }
        if (message == kPackageProgressMessage) {
            std::unique_ptr<StatusPayload> payload(
                reinterpret_cast<StatusPayload*>(l_param));
            if (g_package_status) {
                SetWindowTextW(g_package_status, payload->text.c_str());
            }
            return 0;
        }
        if (message == kPackageDoneMessage) {
            std::unique_ptr<StatusPayload> payload(
                reinterpret_cast<StatusPayload*>(l_param));
            set_packages_busy(false);
            refresh_package_list();
            if (g_package_status) {
                SetWindowTextW(g_package_status, payload->text.c_str());
            }
            if (payload->failed) {
                MessageBoxW(
                    window,
                    payload->text.c_str(),
                    L"Ошибка пакета",
                    MB_ICONERROR | MB_OK);
            }
            return 0;
        }
        if (message == WM_CLOSE) {
            if (g_runtime && g_runtime->packages_busy) {
                MessageBoxW(
                    window,
                    L"Дождитесь окончания установки или удаления.",
                    L"Пакеты",
                    MB_ICONINFORMATION | MB_OK);
                return 0;
            }
            close_packages_window();
            return 0;
        }
        if (message == WM_DESTROY) {
            g_package_list = nullptr;
            g_package_install = nullptr;
            g_package_uninstall = nullptr;
            g_package_status = nullptr;
            g_package_search = nullptr;
            g_package_arch_caption = nullptr;
            g_package_arch_combo = nullptr;
            if (g_runtime && g_runtime->packages_window == window) {
                g_runtime->packages_window = nullptr;
            }
            return 0;
        }
    } catch (const std::exception& error) {
        MessageBoxW(
            window,
            from_utf8(error.what()).c_str(),
            L"Ошибка",
            MB_ICONERROR | MB_OK);
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

void open_packages_window(HWND parent, HINSTANCE instance) {
    if (g_runtime && g_runtime->packages_window) {
        SetForegroundWindow(g_runtime->packages_window);
        return;
    }
    HWND packages = CreateWindowW(
        L"OfflineTranslatorPackages",
        L"Пакеты моделей",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        500,
        400,
        parent,
        nullptr,
        instance,
        nullptr);
    if (!packages) {
        throw std::runtime_error("Не удалось открыть окно пакетов");
    }
    if (g_runtime) {
        g_runtime->packages_window = packages;
    }
    EnableWindow(parent, FALSE);
    ShowWindow(packages, SW_SHOW);
    UpdateWindow(packages);
}

LRESULT CALLBACK window_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    try {
        if (message == WM_CREATE) {
            create_main_controls(window);
            if (!g_smoke_mode) {
                SetTimer(window, kSelectionPollTimer, 40, nullptr);
            }
            return 0;
        }
        if (message == WM_SIZE) {
            layout_main(window);
            return 0;
        }
        if (message == WM_GETMINMAXINFO) {
            auto* info = reinterpret_cast<MINMAXINFO*>(l_param);
            info->ptMinTrackSize.x = kMinWindowWidth;
            info->ptMinTrackSize.y = kMinWindowHeight;
            return 0;
        }
        if (message == WM_EXITSIZEMOVE) {
            persist_settings(window);
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kTranslateButton &&
            HIWORD(w_param) == BN_CLICKED) {
            start_translation(window);
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kPackagesButton &&
            HIWORD(w_param) == BN_CLICKED) {
            open_packages_window(
                window,
                window_instance(window));
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kSettingsButton &&
            HIWORD(w_param) == BN_CLICKED) {
            open_settings_window(window, window_instance(window));
            return 0;
        }
        if (message == WM_COMMAND && LOWORD(w_param) == kTrayOpen) {
            restore_from_tray(window);
            return 0;
        }
        if (message == WM_COMMAND && LOWORD(w_param) == kTrayExit) {
            using offline_translator::UiCommand;
            using offline_translator::effect_for;
            using offline_translator::UiEffect;
            if (effect_for(UiCommand::tray_exit) == UiEffect::destroy_and_quit) {
                DestroyWindow(window);
            }
            return 0;
        }
        if (message == WM_COMMAND && LOWORD(w_param) == kTrayAutostart) {
            if (!g_smoke_mode) {
                toggle_app_autostart();
            }
            return 0;
        }
        if (message == WM_COMMAND &&
            (LOWORD(w_param) == kEngineCombo ||
             LOWORD(w_param) == kSourceLanguageCombo ||
             LOWORD(w_param) == kTargetLanguageCombo) &&
            HIWORD(w_param) == CBN_SELCHANGE) {
            persist_settings(window);
            if (LOWORD(w_param) == kEngineCombo) {
                set_status(
                    selected_engine() == offline_translator::EngineKind::nllb
                        ? L"Выбран NLLB-200. Модель загрузится при переводе."
                        : L"Выбран Argos. Пакет загрузится при переводе.");
            }
            return 0;
        }
        if (message == kStatusMessage) {
            std::unique_ptr<StatusPayload> payload(
                reinterpret_cast<StatusPayload*>(l_param));
            set_status(payload->text);
            return 0;
        }
        if (message == kTranslateMessage) {
            std::unique_ptr<StatusPayload> result(
                reinterpret_cast<StatusPayload*>(l_param));
            SetWindowTextW(g_result_edit, result->text.c_str());
            set_main_busy(false);
            if (result->failed) {
                set_status(L"Ошибка. Можно повторить перевод.");
            }
            return 0;
        }
        if (message == kSelectionResultMessage) {
            std::unique_ptr<StatusPayload> result(
                reinterpret_cast<StatusPayload*>(l_param));
            const auto direction = offline_translator::choose_selection_direction(
                to_utf8(g_selection.selected_text));
            show_result_popup(
                window,
                result->text,
                direction.first,
                direction.second);
            if (result->failed) {
                set_status(L"Ошибка перевода выделения");
            }
            return 0;
        }
        if (message == kTrayMessage) {
            if (l_param == WM_LBUTTONDBLCLK || l_param == WM_LBUTTONUP) {
                restore_from_tray(window);
                return 0;
            }
            if (l_param == WM_RBUTTONUP || l_param == WM_CONTEXTMENU) {
                show_tray_menu(window);
                return 0;
            }
            return 0;
        }
        if (message == WM_TIMER && w_param == kSelectionPollTimer) {
            poll_selection(window);
            return 0;
        }
        if (message == WM_TIMER && w_param == kSelectionButtonHideTimer) {
            hide_selection_button();
            return 0;
        }
        if (message == WM_HOTKEY &&
            w_param == static_cast<WPARAM>(kShowWindowHotkey)) {
            handle_translate_hotkey(window);
            return 0;
        }
        if (message == WM_CLOSE) {
            using offline_translator::UiCommand;
            using offline_translator::effect_for;
            using offline_translator::UiEffect;
            if (effect_for(UiCommand::window_close) == UiEffect::hide_to_tray) {
                hide_to_tray(window);
                return 0;
            }
            DestroyWindow(window);
            return 0;
        }
        if (message == WM_DESTROY) {
            persist_settings(window);
            KillTimer(window, kSelectionPollTimer);
            KillTimer(window, kSelectionButtonHideTimer);
            destroy_popup_windows();
            remove_tray_icon();
            if (g_tray_icon) {
                DestroyIcon(g_tray_icon);
                g_tray_icon = nullptr;
            }
            if (g_runtime) {
                g_runtime->closing = true;
                if (g_runtime->packages_window) {
                    DestroyWindow(g_runtime->packages_window);
                    g_runtime->packages_window = nullptr;
                }
                if (g_runtime->settings_window) {
                    DestroyWindow(g_runtime->settings_window);
                    g_runtime->settings_window = nullptr;
                }
            }
            UnregisterHotKey(window, kShowWindowHotkey);
            PostQuitMessage(0);
            return 0;
        }
    } catch (const std::exception& error) {
        MessageBoxW(
            window,
            from_utf8(error.what()).c_str(),
            L"Ошибка",
            MB_ICONERROR | MB_OK);
        if (g_runtime) {
            g_runtime->busy = false;
        }
        set_main_busy(false);
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

bool command_has_flag(const wchar_t* command_line, const wchar_t* flag) {
    return command_line != nullptr && wcsstr(command_line, flag) != nullptr;
}

int run_smoke_loop(HWND window) {
    using offline_translator::smoke_hides_forever;
    using offline_translator::smoke_may_enable_autostart;
    if (smoke_may_enable_autostart() || smoke_hides_forever()) {
        return 1;
    }
    ShowWindow(window, SW_SHOWNA);
    MSG message{};
    SendMessageW(window, WM_CLOSE, 0, 0);
    if (!IsWindow(window)) {
        return 1;
    }
    if (IsWindowVisible(window)) {
        return 1;
    }
    for (int step = 0; step < 30; ++step) {
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
            if (message.message == WM_QUIT) {
                return static_cast<int>(message.wParam);
            }
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        Sleep(10);
    }
    if (!g_engine_combo || !g_source_language_combo ||
        !g_target_language_combo || !g_translate_button ||
        !g_packages_button || !g_settings_button) {
        return 1;
    }
    DestroyWindow(window);
    while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    if (IsWindow(window)) {
        return 1;
    }
    return 0;
}

// Smoke-проверка попапов выделения: кнопка с иконкой и окно результата
// в обоих режимах. Не трогает автозагрузку и треи.
int run_popup_smoke_loop(HWND window) {
    MSG message{};
    auto pump = [&message](int iterations) {
        for (int step = 0; step < iterations; ++step) {
            while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
                if (message.message == WM_QUIT) {
                    return false;
                }
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
            Sleep(10);
        }
        return true;
    };

    show_selection_button(120, 120, window);
    if (!IsWindow(g_selection_button)) {
        return 1;
    }
    if (!pump(10)) {
        return static_cast<int>(message.wParam);
    }
    // Кнопка обязана быть видимой на экране: в квадрате 40×40 должно
    // найтись несколько разных пикселей (иконка), а не сплошной фон.
    {
        RECT button_rect{};
        GetWindowRect(g_selection_button, &button_rect);
        HDC screen = GetDC(nullptr);
        COLORREF reference = GetPixel(
            screen,
            (button_rect.left + button_rect.right) / 2 - 18,
            (button_rect.top + button_rect.bottom) / 2 - 18);
        int distinct = 0;
        for (int step_y = 4; step_y < 40; step_y += 8) {
            for (int step_x = 4; step_x < 40; step_x += 8) {
                const COLORREF pixel = GetPixel(
                    screen,
                    button_rect.left + step_x,
                    button_rect.top + step_y);
                if (pixel != reference) {
                    ++distinct;
                }
            }
        }
        ReleaseDC(nullptr, screen);
        if (distinct < 3) {
            return 1;
        }
    }
    hide_selection_button();

    g_runtime->settings.result_window_mode =
        offline_translator::kResultWindowSelectable;
    show_result_popup(window, L"Проверка перевода", "ru", "en");
    if (!IsWindow(g_result_popup) || !g_popup_result_edit ||
        !g_popup_copy_button) {
        return 1;
    }
    RECT popup_bounds{};
    GetWindowRect(g_result_popup, &popup_bounds);
    // Высота должна подстраиваться под короткий текст (2 строки минимум).
    const int selectable_height = popup_bounds.bottom - popup_bounds.top;
    if (selectable_height <= 60 || selectable_height > 400) {
        return 1;
    }
    if (!pump(10)) {
        return static_cast<int>(message.wParam);
    }
    hide_result_popup();

    g_runtime->settings.result_window_mode =
        offline_translator::kResultWindowClickToClose;
    show_result_popup(window, L"Второй режим", "en", "ru");
    if (!IsWindow(g_result_popup) || !g_popup_copy_button) {
        return 1;
    }
    pump(10);
    hide_result_popup();
    if (IsWindow(g_result_popup) || IsWindow(g_selection_button)) {
        return 1;
    }
    DestroyWindow(window);
    return 0;
}

}  // анонимное пространство имён

int WINAPI wWinMain(
    HINSTANCE instance,
    HINSTANCE,
    PWSTR command_line,
    int show_command) {
    g_smoke_mode = command_has_flag(command_line, L"--smoke-start") ||
        command_has_flag(GetCommandLineW(), L"--smoke-start");
    g_start_minimized =
        !g_smoke_mode &&
        (command_has_flag(command_line, L"--minimized") ||
         command_has_flag(GetCommandLineW(), L"--minimized"));
    g_runtime = std::make_shared<GuiRuntime>();
    offline_translator::set_capture_wait_hook(&pump_wait);

    const wchar_t class_name[] = L"OfflineTranslatorWindow";
    WNDCLASSW window_class{};
    window_class.hInstance = instance;
    window_class.lpfnWndProc = window_proc;
    window_class.lpszClassName = class_name;
    window_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    window_class.hbrBackground = reinterpret_cast<HBRUSH>(
        COLOR_WINDOW + 1);
    if (!RegisterClassW(&window_class)) {
        return 1;
    }

    WNDCLASSW packages_class{};
    packages_class.hInstance = instance;
    packages_class.lpfnWndProc = packages_proc;
    packages_class.lpszClassName = L"OfflineTranslatorPackages";
    packages_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    packages_class.hbrBackground = reinterpret_cast<HBRUSH>(
        COLOR_WINDOW + 1);
    if (!RegisterClassW(&packages_class)) {
        return 1;
    }

    WNDCLASSW settings_class{};
    settings_class.hInstance = instance;
    settings_class.lpfnWndProc = settings_proc;
    settings_class.lpszClassName = L"OfflineTranslatorSettings";
    settings_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    settings_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&settings_class)) {
        return 1;
    }

    WNDCLASSW selection_class{};
    selection_class.hInstance = instance;
    selection_class.lpfnWndProc = selection_button_proc;
    selection_class.lpszClassName = L"OfflineTranslatorSelectionButton";
    selection_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_HAND));
    selection_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&selection_class)) {
        return 1;
    }

    WNDCLASSW result_class{};
    result_class.hInstance = instance;
    result_class.lpfnWndProc = result_popup_proc;
    result_class.lpszClassName = L"OfflineTranslatorResultPopup";
    result_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    result_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&result_class)) {
        return 1;
    }

    const auto settings = offline_translator::load_settings();
    const int width = settings.window_width >= kMinWindowWidth
        ? settings.window_width
        : kDefaultWindowWidth;
    const int height = settings.window_height >= kMinWindowHeight
        ? settings.window_height
        : kDefaultWindowHeight;

    HWND window = CreateWindowW(
        class_name,
        L"Offline Translator C++",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        width,
        height,
        nullptr,
        nullptr,
        instance,
        nullptr);
    if (!window) {
        return 1;
    }
    g_runtime->main_window = window;
    g_runtime->settings = settings;
    if (!g_smoke_mode &&
        !register_translate_hotkey(window, settings.translate_hotkey)) {
        const std::wstring warning =
            L"Не удалось зарегистрировать горячую клавишу " +
            from_utf8(settings.translate_hotkey) + L".";
        MessageBoxW(
            window,
            warning.c_str(),
            L"Предупреждение",
            MB_ICONWARNING | MB_OK);
    }
    Gdiplus::GdiplusStartupInput gdiplus_input{};
    ULONG_PTR gdiplus_token = 0;
    const bool gdiplus_ready =
        Gdiplus::GdiplusStartup(&gdiplus_token, &gdiplus_input, nullptr) ==
        Gdiplus::Ok;
    if (command_has_flag(command_line, L"--smoke-popup") ||
        command_has_flag(GetCommandLineW(), L"--smoke-popup")) {
        const int result = run_popup_smoke_loop(window);
        if (gdiplus_ready) {
            Gdiplus::GdiplusShutdown(gdiplus_token);
        }
        return result;
    }
    if (g_smoke_mode) {
        if (gdiplus_ready) {
            Gdiplus::GdiplusShutdown(gdiplus_token);
        }
        return run_smoke_loop(window);
    }
    add_tray_icon(window);
    if (g_start_minimized) {
        hide_to_tray(window);
    } else {
        // Запуск через CreateProcess может прийти с nCmdShow=0 (SW_HIDE):
        // окно обязано появиться, как при обычном двойном клике.
        ShowWindow(window, show_command == 0 ? SW_SHOWNORMAL : show_command);
        UpdateWindow(window);
    }

    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    if (gdiplus_ready) {
        Gdiplus::GdiplusShutdown(gdiplus_token);
    }
    return static_cast<int>(message.wParam);
}
